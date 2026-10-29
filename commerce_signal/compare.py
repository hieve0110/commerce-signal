"""일자별 비교표(daily_comparison) 생성."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .db import latest_crawl_date

COMPETITOR_PLATFORMS_SQL = "SELECT DISTINCT platform FROM snapshots WHERE platform != 'todaysales'"
# 경쟁사 수집이 하루 이틀 실패해도 직전 데이터로 비교 (그 이상 오래된 건 제외)
MAX_STALE_DAYS = 2


def grade(gap_pct: float, cfg: dict) -> str:
    if gap_pct <= 0:
        return "lowest"
    if gap_pct <= cfg["competitive_pct"]:
        return "competitive"
    if gap_pct <= cfg["weak_pct"]:
        return "weak"
    return "very_weak"


def _snapshot(conn, platform: str, report_date: str) -> dict[str, sqlite3.Row]:
    d = latest_crawl_date(conn, platform, report_date)
    if not d or date.fromisoformat(report_date) - date.fromisoformat(d) > timedelta(days=MAX_STALE_DAYS):
        return {}
    rows = conn.execute("SELECT * FROM snapshots WHERE platform = ? AND crawl_date = ?", (platform, d))
    return {r["product_key"]: r for r in rows}


def build(conn: sqlite3.Connection, report_date: str, cfg: dict) -> int:
    ours = _snapshot(conn, "todaysales", report_date)
    comps: dict[str, sqlite3.Row] = {}
    for (platform,) in conn.execute(COMPETITOR_PLATFORMS_SQL).fetchall():
        comps.update(_snapshot(conn, platform, report_date))

    pairs: dict[str, list[tuple[sqlite3.Row, str]]] = {}
    for m in conn.execute("SELECT our_key, comp_key, status FROM mappings WHERE status IN ('confirmed', 'auto')"):
        if m["our_key"] in ours and m["comp_key"] in comps:
            pairs.setdefault(m["our_key"], []).append((comps[m["comp_key"]], m["status"]))

    out = []
    for our_key, matched in pairs.items():
        o = ours[our_key]
        # 단위가격 비교가 기본. 용량을 못 읽은 경우엔 사람이 확정한 매핑만 판매가로 비교
        if o["unit_price"]:
            cands = [(c["unit_price"], c, s) for c, s in matched
                     if c["unit_price"] and c["measure_unit"] == o["measure_unit"]]
            our_value, unit = o["unit_price"], o["measure_unit"]
        else:
            cands, our_value, unit = [], None, None
        if not cands:
            cands = [(c["price_sale"], c, s) for c, s in matched if s == "confirmed" and c["price_sale"]]
            our_value, unit = o["price_sale"], "price"
        if not cands or not our_value:
            continue
        best_value, best, _ = min(cands, key=lambda t: t[0])
        gap = round((our_value - best_value) / best_value * 100, 1)
        out.append({
            "report_date": report_date, "our_key": our_key, "our_name": o["product_name"],
            "our_seller": o["seller_name"], "our_price": o["price_sale"], "our_unit_price": our_value,
            "measure_unit": unit, "comp_min_unit_price": best_value, "comp_min_price": best["price_sale"],
            "comp_min_key": best["product_key"], "comp_min_platform": best["platform"],
            "comp_min_seller": best["seller_name"], "comp_min_name": best["product_name"],
            "n_competitors": len(cands), "gap_pct": gap, "grade": grade(gap, cfg),
            "match_status": "confirmed" if any(s == "confirmed" for _, _, s in cands) else "auto",
        })

    conn.execute("DELETE FROM daily_comparison WHERE report_date = ?", (report_date,))
    if out:
        cols = list(out[0])
        conn.executemany(
            f"INSERT INTO daily_comparison ({','.join(cols)}) VALUES ({','.join(':' + c for c in cols)})", out)
    return len(out)
