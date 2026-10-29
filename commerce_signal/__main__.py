"""CLI.

  python -m commerce_signal daily                 # 수집 → 매칭 → 비교 → 슬랙 (매일 돌리는 명령)
  python -m commerce_signal collect [--only todaysales,baemin,foodspring]
  python -m commerce_signal import-csv FILE --platform baemin
  python -m commerce_signal match
  python -m commerce_signal compare [--date YYYY-MM-DD]
  python -m commerce_signal report  [--date YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys

from . import compare, matching, report
from .collectors import baemin, csv_import, foodspring, todaysales
from .config import dashboard_url, load_config, slack_webhook_url, today_kst
from .db import connect, replace_snapshots

COLLECTORS = {"todaysales": todaysales, "baemin": baemin, "foodspring": foodspring}


def cmd_collect(cfg, conn, day, only=None) -> dict[str, int]:
    results = {}
    for name, mod in COLLECTORS.items():
        if only and name not in only:
            continue
        section = cfg[name]
        if name != "todaysales" and not section.get("enabled", True):
            continue
        try:
            rows = mod.collect(section)
        except Exception as e:
            print(f"[{name}] 수집 실패: {type(e).__name__}: {e}", file=sys.stderr)
            results[name] = -1
            continue
        if rows:  # 0건이면 기존 데이터를 지우지 않음 (차단·장애 시 보호)
            replace_snapshots(conn, day, name, rows)
        results[name] = len(rows)
    print(f"수집 결과({day}): {results}")
    return results


def cmd_match(cfg, conn, day) -> dict:
    def latest(platform_clause: str) -> list[dict]:
        sql = f"""SELECT s.* FROM snapshots s JOIN (
                    SELECT platform, MAX(crawl_date) d FROM snapshots WHERE crawl_date <= ? GROUP BY platform
                  ) l ON s.platform = l.platform AND s.crawl_date = l.d WHERE s.platform {platform_clause}"""
        return [dict(r) for r in conn.execute(sql, (day,))]

    ours, comps = latest("= 'todaysales'"), latest("!= 'todaysales'")
    counts = matching.save_suggestions(conn, matching.suggest(ours, comps, cfg["matching"]))
    print(f"매칭: 우리 {len(ours)}개 × 경쟁 {len(comps)}개 → {counts}")
    return counts


def cmd_report(cfg, conn, day, dry_run=False) -> None:
    summary = report.gather(conn, day, cfg["report"])
    blocks = report.build_blocks(summary, dashboard_url())
    webhook = slack_webhook_url()
    if dry_run or not webhook:
        if not webhook and not dry_run:
            print("SLACK_WEBHOOK_URL 미설정 → 슬랙 대신 화면에 출력합니다.\n")
        print(report.to_text(blocks))
        return
    report.send(blocks, webhook, f"카페/베이커리 가격 비교 {day}")
    print("슬랙 전송 완료")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="commerce_signal")
    p.add_argument("command", choices=["daily", "collect", "import-csv", "match", "compare", "report"])
    p.add_argument("file", nargs="?")
    p.add_argument("--date", default=None)
    p.add_argument("--only", default="")
    p.add_argument("--platform", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--config", default=None)
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    day = a.date or today_kst()
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    with connect(cfg["storage"]["db_path"]) as conn:
        if a.command == "collect":
            cmd_collect(cfg, conn, day, only)
        elif a.command == "import-csv":
            if not a.file or not a.platform:
                p.error("import-csv FILE --platform NAME")
            n = replace_snapshots(conn, day, a.platform, csv_import.collect(a.file, a.platform))
            print(f"{a.platform} {n}건 업로드 ({day})")
        elif a.command == "match":
            cmd_match(cfg, conn, day)
        elif a.command == "compare":
            print(f"비교 {compare.build(conn, day, cfg['report'])}건 ({day})")
        elif a.command == "report":
            cmd_report(cfg, conn, day, a.dry_run)
        elif a.command == "daily":
            results = cmd_collect(cfg, conn, day, only)
            if results.get("todaysales", 0) <= 0:
                print("오늘얼마 수집 실패 — 중단", file=sys.stderr)
                return 1
            cmd_match(cfg, conn, day)
            print(f"비교 {compare.build(conn, day, cfg['report'])}건")
            conn.commit()
            cmd_report(cfg, conn, day, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
