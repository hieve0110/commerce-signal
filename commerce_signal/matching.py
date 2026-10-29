"""우리 상품 ↔ 경쟁 상품 매칭 후보 생성.

점수 = 글자 bigram 유사도(띄어쓰기 차이 흡수) 와 단어 겹침의 평균.
- auto:      점수 ≥ auto_threshold 이고 용량 단위(g/ml/개)가 같고 크기 차이가 허용범위 → 리포트 반영
- suggested: 점수 ≥ suggest_threshold → 대시보드 '매핑 검수'에서 사람이 확정/거절
사람이 confirmed / rejected 로 바꾼 매핑은 다시 덮어쓰지 않는다.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from .normalize import bigrams, normalize_name, tokens


def similarity(a_norm: str, b_norm: str) -> float:
    ba, bb = bigrams(a_norm), bigrams(b_norm)
    if not ba or not bb:
        return 0.0
    dice = 2 * len(ba & bb) / (len(ba) + len(bb))
    ta, tb = tokens(a_norm), tokens(b_norm)
    overlap = len(ta & tb) / min(len(ta), len(tb)) if ta and tb else dice
    return round((dice + overlap) / 2, 4)


def _size_ok(a: dict, b: dict, max_ratio: float) -> bool:
    if not a["measure_unit"] or a["measure_unit"] != b["measure_unit"]:
        return False
    lo, hi = sorted([a["measure_value"], b["measure_value"]])
    return lo > 0 and hi / lo <= max_ratio


def suggest(ours: list[dict], competitors: list[dict], cfg: dict) -> list[dict]:
    """반환: [{our_key, comp_key, score, status}]"""
    comp_norm = [normalize_name(c["product_name"], c.get("seller_name", "")) for c in competitors]
    index: dict[str, list[int]] = defaultdict(list)
    for i, n in enumerate(comp_norm):
        for g in bigrams(n):
            index[g].append(i)

    out = []
    for o in ours:
        o_norm = normalize_name(o["product_name"], o.get("seller_name", ""))
        o_grams = bigrams(o_norm)
        if len(o_grams) < 2:
            continue
        hits: dict[int, int] = defaultdict(int)
        for g in o_grams:
            for i in index.get(g, ()):
                hits[i] += 1
        # bigram 많이 겹치는 상위 50개만 정밀 채점
        pool = sorted(hits, key=hits.get, reverse=True)[:50]
        scored = sorted(((similarity(o_norm, comp_norm[i]), i) for i in pool), reverse=True)
        for score, i in scored[: cfg["max_candidates"]]:
            if score < cfg["suggest_threshold"]:
                break
            c = competitors[i]
            auto = score >= cfg["auto_threshold"] and _size_ok(o, c, cfg["max_size_ratio"])
            out.append({"our_key": o["product_key"], "comp_key": c["product_key"],
                        "score": score, "status": "auto" if auto else "suggested"})
    return out


def save_suggestions(conn: sqlite3.Connection, suggestions: list[dict]) -> dict:
    """auto/suggested 만 갱신. 사람이 정한 confirmed/rejected 는 유지."""
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("DELETE FROM mappings WHERE status IN ('auto', 'suggested')")
    conn.executemany(
        """INSERT INTO mappings (our_key, comp_key, status, score, updated_at, updated_by)
           VALUES (:our_key, :comp_key, :status, :score, :now, 'matcher')
           ON CONFLICT(our_key, comp_key) DO NOTHING""",
        [{**s, "now": now} for s in suggestions],
    )
    counts = dict(conn.execute("SELECT status, COUNT(*) FROM mappings GROUP BY status").fetchall())
    return counts


def set_status(conn: sqlite3.Connection, our_key: str, comp_key: str, status: str, user: str = "") -> None:
    assert status in ("confirmed", "rejected", "auto", "suggested")
    conn.execute(
        """INSERT INTO mappings (our_key, comp_key, status, score, updated_at, updated_by)
           VALUES (?, ?, ?, NULL, ?, ?)
           ON CONFLICT(our_key, comp_key) DO UPDATE SET status = excluded.status,
             updated_at = excluded.updated_at, updated_by = excluded.updated_by""",
        (our_key, comp_key, status, datetime.now().isoformat(timespec="seconds"), user),
    )
