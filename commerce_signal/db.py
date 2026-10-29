"""SQLite 저장소.

- snapshots:        매일 수집한 원본 가격 (로우데이터, 날짜별 누적)
- mappings:         우리 상품 ↔ 경쟁 상품 매핑 (auto / suggested / confirmed / rejected)
- daily_comparison: 일자 × 우리 상품 단위 비교 결과 (리포트·대시보드의 원천)
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  crawl_date       TEXT NOT NULL,
  platform         TEXT NOT NULL,          -- todaysales | baemin | foodspring | (csv 업로드 시 임의)
  seller_id        TEXT,
  seller_name      TEXT,
  product_key      TEXT NOT NULL,          -- platform_seller_product 형태로 전 플랫폼 유일
  product_no       TEXT,
  product_name     TEXT,
  spec             TEXT,
  category         TEXT,
  price_original   REAL,
  price_sale       REAL,                   -- 비교에 쓰는 가격 (즉시할인 반영)
  delivery_type    TEXT,
  delivery_summary TEXT,
  is_free_delivery INTEGER,
  stock            INTEGER,
  measure_value    REAL,
  measure_unit     TEXT,                   -- g | ml | ea
  unit_price       REAL,                   -- 100g / 100ml / 1개 당 가격
  PRIMARY KEY (crawl_date, product_key)
);
CREATE INDEX IF NOT EXISTS idx_snap_platform ON snapshots (platform, crawl_date);

CREATE TABLE IF NOT EXISTS mappings (
  our_key     TEXT NOT NULL,
  comp_key    TEXT NOT NULL,
  status      TEXT NOT NULL,               -- auto | suggested | confirmed | rejected
  score       REAL,
  updated_at  TEXT,
  updated_by  TEXT,
  PRIMARY KEY (our_key, comp_key)
);

CREATE TABLE IF NOT EXISTS daily_comparison (
  report_date         TEXT NOT NULL,
  our_key             TEXT NOT NULL,
  our_name            TEXT,
  our_seller          TEXT,
  our_price           REAL,
  our_unit_price      REAL,
  measure_unit        TEXT,
  comp_min_unit_price REAL,
  comp_min_price      REAL,
  comp_min_key        TEXT,
  comp_min_platform   TEXT,
  comp_min_seller     TEXT,
  comp_min_name       TEXT,
  n_competitors       INTEGER,
  gap_pct             REAL,                -- (우리 - 경쟁최저) / 경쟁최저 * 100. 음수 = 우리가 더 쌈
  grade               TEXT,                -- lowest | competitive | weak | very_weak
  match_status        TEXT,                -- confirmed | auto (가장 신뢰도 높은 매핑 기준)
  PRIMARY KEY (report_date, our_key)
);
"""

SNAPSHOT_COLS = [
    "crawl_date", "platform", "seller_id", "seller_name", "product_key", "product_no",
    "product_name", "spec", "category", "price_original", "price_sale", "delivery_type",
    "delivery_summary", "is_free_delivery", "stock", "measure_value", "measure_unit", "unit_price",
]


@contextmanager
def connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def replace_snapshots(conn: sqlite3.Connection, crawl_date: str, platform: str, rows: list[dict]) -> int:
    """해당 날짜·플랫폼 스냅샷을 통째로 교체 (같은 날 재수집해도 중복되지 않게)."""
    conn.execute("DELETE FROM snapshots WHERE crawl_date = ? AND platform = ?", (crawl_date, platform))
    placeholders = ",".join("?" for _ in SNAPSHOT_COLS)
    conn.executemany(
        f"INSERT OR REPLACE INTO snapshots ({','.join(SNAPSHOT_COLS)}) VALUES ({placeholders})",
        [[{**r, "crawl_date": crawl_date}.get(c) for c in SNAPSHOT_COLS] for r in rows],
    )
    return len(rows)


def latest_crawl_date(conn: sqlite3.Connection, platform: str, on_or_before: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(crawl_date) FROM snapshots WHERE platform = ? AND crawl_date <= ?",
        (platform, on_or_before),
    ).fetchone()
    return row[0] if row else None
