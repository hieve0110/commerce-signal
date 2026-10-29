"""카페/베이커리 가격 비교 대시보드 (Streamlit).

실행:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from commerce_signal.config import load_config  # noqa: E402
from commerce_signal.db import SCHEMA  # noqa: E402
from commerce_signal.matching import set_status  # noqa: E402
from commerce_signal.report import GRADE_LABEL, PLATFORM_LABEL  # noqa: E402

st.set_page_config(page_title="커머스 시그널 · 카페/베이커리", page_icon="☕", layout="wide")
CFG = load_config()
DB = CFG["storage"]["db_path"]
GRADE_COLOR = {"lowest": "#2e9e5b", "competitive": "#d9a400", "weak": "#e8711a", "very_weak": "#d33a2c"}
REVIEW = {"확정": "confirmed", "거절": "rejected"}


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


@st.cache_data(ttl=300)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params)


def csv_button(df: pd.DataFrame, name: str) -> None:
    st.download_button("CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"), f"{name}.csv", "text/csv")


st.title("☕ 카페/베이커리 가격 비교")
st.caption("오늘얼마 vs 배민상회·식봄 · 단위가격(100g·100ml·1개당) 기준, 즉시할인 반영, 배송비 미포함")

dates = q("SELECT DISTINCT report_date FROM daily_comparison ORDER BY 1 DESC")["report_date"].tolist()
tab_report, tab_detail, tab_raw, tab_map = st.tabs(["📊 일자별 리포트", "📈 상품 가격 추이", "🗂 로우데이터", "🔗 매핑 검수"])

# ── 일자별 리포트 ──────────────────────────────────────────────
with tab_report:
    if not dates:
        st.info("아직 비교 결과가 없어요. `python -m commerce_signal daily` 를 먼저 실행해 주세요.")
    else:
        day = st.selectbox("날짜", dates, key="report_date")
        df = q("SELECT * FROM daily_comparison WHERE report_date = ?", (day,))
        n_ours = q("SELECT COUNT(*) n FROM snapshots WHERE platform='todaysales' AND crawl_date=?", (day,))["n"][0]
        cols = st.columns(5)
        cols[0].metric("비교 상품", f"{len(df):,}", f"커버리지 {len(df) / max(n_ours, 1) * 100:.0f}%", delta_color="off")
        for col, (g, label) in zip(cols[1:], GRADE_LABEL.items()):
            col.metric(label, int((df["grade"] == g).sum()))

        trend = q("SELECT report_date, grade, COUNT(*) n FROM daily_comparison GROUP BY 1, 2")
        if trend["report_date"].nunique() > 1:
            st.subheader("등급별 상품 수 추이")
            pivot = trend.pivot(index="report_date", columns="grade", values="n").fillna(0)
            order = [g for g in GRADE_LABEL if g in pivot.columns]
            st.line_chart(pivot[order].rename(columns=GRADE_LABEL),
                          color=[GRADE_COLOR[g] for g in order])

        view = df.assign(
            등급=df["grade"].map(GRADE_LABEL),
            경쟁플랫폼=df["comp_min_platform"].map(PLATFORM_LABEL).fillna(df["comp_min_platform"]),
        )[["등급", "our_name", "our_seller", "our_price", "our_unit_price", "measure_unit", "경쟁플랫폼",
           "comp_min_seller", "comp_min_name", "comp_min_price", "comp_min_unit_price", "gap_pct", "match_status"]]
        view.columns = ["등급", "우리 상품", "우리 셀러", "우리 판매가", "우리 단가", "단위", "경쟁 플랫폼",
                        "경쟁 셀러", "경쟁 상품", "경쟁 판매가", "경쟁 단가", "차이(%)", "매칭"]
        grade_filter = st.multiselect("등급 필터", list(GRADE_LABEL.values()), default=list(GRADE_LABEL.values()))
        view = view[view["등급"].isin(grade_filter)].sort_values("차이(%)")
        st.dataframe(view, use_container_width=True, hide_index=True,
                     column_config={"차이(%)": st.column_config.NumberColumn(format="%+.1f%%")})
        csv_button(view, f"price_compare_{day}")

# ── 상품 가격 추이 ────────────────────────────────────────────
with tab_detail:
    products = q("SELECT DISTINCT our_key, our_name, our_seller FROM daily_comparison ORDER BY our_name")
    if products.empty:
        st.info("비교 결과가 쌓이면 상품별 추이를 볼 수 있어요.")
    else:
        label = products["our_name"] + " · " + products["our_seller"]
        pick = st.selectbox("상품", products.index, format_func=lambda i: label[i])
        our_key = products.loc[pick, "our_key"]
        mapped = q("""SELECT comp_key FROM mappings WHERE our_key = ? AND status IN ('confirmed','auto')""", (our_key,))
        keys = [our_key] + mapped["comp_key"].tolist()
        hist = q(f"""SELECT crawl_date, platform, seller_name, product_name, price_sale, unit_price
                     FROM snapshots WHERE product_key IN ({','.join('?' * len(keys))}) ORDER BY crawl_date""",
                 tuple(keys))
        hist["시리즈"] = hist["platform"].map(PLATFORM_LABEL).fillna(hist["platform"]) + " · " + hist["seller_name"]
        st.line_chart(hist.pivot_table(index="crawl_date", columns="시리즈", values="unit_price"))
        st.dataframe(hist, use_container_width=True, hide_index=True)

# ── 로우데이터 ────────────────────────────────────────────────
with tab_raw:
    snap_dates = q("SELECT DISTINCT crawl_date FROM snapshots ORDER BY 1 DESC")["crawl_date"].tolist()
    if not snap_dates:
        st.info("수집된 데이터가 없어요.")
    else:
        c1, c2, c3 = st.columns([1, 1, 2])
        d = c1.selectbox("수집일", snap_dates, key="raw_date")
        platforms = q("SELECT DISTINCT platform FROM snapshots WHERE crawl_date = ?", (d,))["platform"].tolist()
        pf = c2.multiselect("플랫폼", platforms, default=platforms, format_func=lambda p: PLATFORM_LABEL.get(p, p))
        kw = c3.text_input("상품명 검색")
        raw = q("SELECT * FROM snapshots WHERE crawl_date = ?", (d,))
        raw = raw[raw["platform"].isin(pf)]
        if kw:
            raw = raw[raw["product_name"].str.contains(kw, case=False, na=False)]
        st.caption(f"{len(raw):,}건")
        st.dataframe(raw, use_container_width=True, hide_index=True)
        csv_button(raw, f"raw_{d}")

# ── 매핑 검수 ────────────────────────────────────────────────
with tab_map:
    st.caption("자동 매칭(auto)은 리포트에 바로 반영되고, 후보(suggested)는 확정해야 반영돼요. "
               "확정/거절한 매핑은 다음 매칭 때도 유지돼요.")
    status = st.radio("상태", ["suggested", "auto", "confirmed", "rejected"], horizontal=True,
                      format_func={"suggested": "검수 필요", "auto": "자동 매칭", "confirmed": "확정",
                                   "rejected": "거절"}.get)
    m = q("""
        WITH latest AS (SELECT product_key, product_name, seller_name, platform, price_sale, unit_price,
                               measure_unit, ROW_NUMBER() OVER (PARTITION BY product_key ORDER BY crawl_date DESC) rn
                        FROM snapshots)
        SELECT m.our_key, m.comp_key, m.score,
               o.product_name AS our_name, o.seller_name AS our_seller, o.price_sale AS our_price,
               c.platform AS comp_platform, c.product_name AS comp_name, c.seller_name AS comp_seller,
               c.price_sale AS comp_price, o.unit_price AS our_unit, c.unit_price AS comp_unit
        FROM mappings m
        JOIN latest o ON o.product_key = m.our_key AND o.rn = 1
        JOIN latest c ON c.product_key = m.comp_key AND c.rn = 1
        WHERE m.status = ? ORDER BY m.score DESC LIMIT 500""", (status,))
    if m.empty:
        st.info("해당 상태의 매핑이 없어요.")
    else:
        m["comp_platform"] = m["comp_platform"].map(PLATFORM_LABEL).fillna(m["comp_platform"])
        m.insert(0, "검수", None)
        labels = {"score": "유사도", "our_name": "우리 상품", "our_seller": "우리 셀러", "our_price": "우리 판매가",
                  "comp_platform": "경쟁 플랫폼", "comp_name": "경쟁 상품", "comp_seller": "경쟁 셀러",
                  "comp_price": "경쟁 판매가", "our_unit": "우리 단가", "comp_unit": "경쟁 단가"}
        edited = st.data_editor(
            m, hide_index=True, use_container_width=True, disabled=[c for c in m.columns if c != "검수"],
            column_config={"검수": st.column_config.SelectboxColumn(options=list(REVIEW)),
                           "our_key": None, "comp_key": None,
                           **{k: st.column_config.Column(v) for k, v in labels.items()}})
        reviewer = st.text_input("검수자 이름")
        if st.button("선택한 항목 저장", type="primary"):
            changed = edited[edited["검수"].isin(list(REVIEW))]
            with conn() as c:
                for _, r in changed.iterrows():
                    set_status(c, r["our_key"], r["comp_key"], REVIEW[r["검수"]], reviewer)
            st.cache_data.clear()
            st.success(f"{len(changed)}건 저장. 다음 `compare` 실행부터 리포트에 반영돼요.")
