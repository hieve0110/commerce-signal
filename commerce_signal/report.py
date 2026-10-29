"""일일 슬랙 리포트 (Incoming Webhook, Block Kit)."""
from __future__ import annotations

import sqlite3

import requests

from .normalize import UNIT_LABEL

GRADE_LABEL = {"lowest": "🟢 최저가", "competitive": "🟡 경쟁", "weak": "🟠 열위", "very_weak": "🔴 크게 열위"}
PLATFORM_LABEL = {"baemin": "배민상회", "foodspring": "식봄", "todaysales": "오늘얼마"}


def _won(v) -> str:
    return f"{v:,.0f}원" if v is not None else "-"


def _unit(r) -> str:
    return "판매가" if r["measure_unit"] == "price" else UNIT_LABEL.get(r["measure_unit"], "")


def _line(r) -> str:
    comp = f"{PLATFORM_LABEL.get(r['comp_min_platform'], r['comp_min_platform'])}·{r['comp_min_seller']}"
    return (f"• *{r['our_name'][:40]}*  {_won(r['our_price'])}\n"
            f"   {_unit(r)} {_won(r['our_unit_price'])} vs {comp} {_won(r['comp_min_unit_price'])}"
            f"  (*{r['gap_pct']:+.1f}%*)")


def gather(conn: sqlite3.Connection, report_date: str, cfg: dict) -> dict:
    rows = conn.execute("SELECT * FROM daily_comparison WHERE report_date = ?", (report_date,)).fetchall()
    prev_date = conn.execute(
        "SELECT MAX(report_date) FROM daily_comparison WHERE report_date < ?", (report_date,)).fetchone()[0]
    prev = {r["our_key"]: r for r in conn.execute(
        "SELECT * FROM daily_comparison WHERE report_date = ?", (prev_date,))} if prev_date else {}
    n_ours = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE platform='todaysales' AND crawl_date = ?", (report_date,)).fetchone()[0]
    comp_counts = dict(conn.execute(
        "SELECT platform, COUNT(*) FROM snapshots WHERE platform != 'todaysales' AND crawl_date = ? GROUP BY platform",
        (report_date,)).fetchall())

    top = cfg["top_n"]
    by_grade = {g: sum(1 for r in rows if r["grade"] == g) for g in GRADE_LABEL}
    lowest = sorted((r for r in rows if r["grade"] == "lowest"), key=lambda r: r["gap_pct"])[:top]
    weakest = sorted((r for r in rows if r["grade"] == "very_weak"), key=lambda r: -r["gap_pct"])[:top]
    new_lowest = [r for r in rows if r["grade"] == "lowest" and r["our_key"] in prev and prev[r["our_key"]]["grade"] != "lowest"]
    lost_lowest = [r for r in rows if r["grade"] != "lowest" and r["our_key"] in prev and prev[r["our_key"]]["grade"] == "lowest"]
    comp_drops = [r for r in rows if r["our_key"] in prev and prev[r["our_key"]]["comp_min_unit_price"]
                  and r["measure_unit"] == prev[r["our_key"]]["measure_unit"]
                  and (prev[r["our_key"]]["comp_min_unit_price"] - r["comp_min_unit_price"])
                  / prev[r["our_key"]]["comp_min_unit_price"] * 100 >= cfg["competitor_drop_alert_pct"]]
    return {"date": report_date, "prev_date": prev_date, "rows": rows, "n_ours": n_ours,
            "comp_counts": comp_counts, "by_grade": by_grade, "lowest": lowest, "weakest": weakest,
            "new_lowest": new_lowest[:top], "lost_lowest": lost_lowest[:top], "comp_drops": comp_drops[:top]}


def build_blocks(s: dict, dashboard_url: str = "") -> list[dict]:
    def section(text: str) -> dict:
        return {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}

    n = len(s["rows"])
    coverage = f"{n}/{s['n_ours']}개 비교 ({n / s['n_ours'] * 100:.0f}%)" if s["n_ours"] else "우리 상품 수집 0건"
    comp = " · ".join(f"{PLATFORM_LABEL.get(p, p)} {c:,}개" for p, c in s["comp_counts"].items()) or "⚠️ 경쟁사 수집 0건"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"☕ 카페/베이커리 가격 비교 · {s['date']}"}},
        section(f"*비교 커버리지* {coverage}\n*수집* 오늘얼마 {s['n_ours']:,}개 · {comp}"),
        section("  ".join(f"{GRADE_LABEL[g]} *{c}*" for g, c in s["by_grade"].items())),
        {"type": "divider"},
    ]
    if s["lowest"]:
        blocks.append(section("*🟢 오늘 우리가 최저가 — 최저가 앱푸시 후보*\n" + "\n".join(map(_line, s["lowest"]))))
    if s["weakest"]:
        blocks.append(section("*🔴 크게 비싼 상품 — 가격 검토 필요*\n" + "\n".join(map(_line, s["weakest"]))))
    changes = []
    if s["new_lowest"]:
        changes.append("*새로 최저가가 된 상품*\n" + "\n".join(map(_line, s["new_lowest"])))
    if s["lost_lowest"]:
        changes.append("*최저가를 뺏긴 상품*\n" + "\n".join(map(_line, s["lost_lowest"])))
    if s["comp_drops"]:
        changes.append("*경쟁사가 가격을 내린 상품*\n" + "\n".join(map(_line, s["comp_drops"])))
    if changes:
        blocks.append({"type": "divider"})
        blocks.append(section(f"*📈 전일({s['prev_date']}) 대비 변동*"))
        blocks.extend(section(c) for c in changes)
    if not n:
        blocks.append(section("비교 가능한 상품이 없어요. 경쟁사 수집 상태와 매핑 검수 화면을 확인해 주세요."))
    footer = "단위가격(100g·100ml·1개당) 기준, 즉시할인 반영·배송비 미포함 · 매칭: 자동+검수확정"
    if dashboard_url:
        footer += f" · <{dashboard_url}|대시보드 열기>"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
    return blocks


def send(blocks: list[dict], webhook_url: str, fallback_text: str) -> None:
    resp = requests.post(webhook_url, json={"text": fallback_text, "blocks": blocks}, timeout=20)
    resp.raise_for_status()


def to_text(blocks: list[dict]) -> str:
    parts = []
    for b in blocks:
        if b["type"] in ("header", "section"):
            parts.append(b["text"]["text"])
        elif b["type"] == "context":
            parts.append(b["elements"][0]["text"])
        elif b["type"] == "divider":
            parts.append("─" * 40)
    return "\n".join(parts)
