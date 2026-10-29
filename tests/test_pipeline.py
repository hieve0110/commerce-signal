from commerce_signal import compare, matching
from commerce_signal.collectors import finalize
from commerce_signal.db import connect, replace_snapshots
from commerce_signal.normalize import normalize_name, parse_measure
from commerce_signal.report import build_blocks, gather

CFG = {
    "matching": {"auto_threshold": 0.82, "suggest_threshold": 0.6, "max_candidates": 5, "max_size_ratio": 2.0},
    "report": {"competitive_pct": 5.0, "weak_pct": 15.0, "top_n": 10, "competitor_drop_alert_pct": 5.0},
}


def test_parse_measure():
    assert parse_measure("리얼과즙 파인애플 샤베트 150ml*20ea[박스]") == (3000.0, "ml")
    assert parse_measure("초콜릿브라우니 25Gx40") == (1000.0, "g")
    assert parse_measure("농심가락짜장면 1.25kg(8입)") == (1250.0, "g")
    assert parse_measure("볼도우,600G,에버웰푸드,14.4KG(600G*24EA)/BOX") == (14400.0, "g")
    assert parse_measure("헤이즐넛시럽,토스키,1,000ML/EA") == (1000.0, "ml")
    assert parse_measure("선인 또띠아 12매") == (12.0, "ea")
    assert parse_measure("카누 미니 마일드 100T") == (100.0, "ea")
    assert parse_measure("생강차(유안,실온)") == (None, None)


def test_normalize_keeps_brand_in_brackets():
    assert normalize_name("딸기잼(오뚜기/850g)") == "딸기잼 오뚜기"
    assert normalize_name("블루큐라소시럽,외식,말레이시아산,모닌,1L/EA,김해D-2") == "블루큐라소시럽 모닌"


def _row(platform, seller, pno, name, price):
    return finalize({"platform": platform, "seller_id": seller, "seller_name": seller,
                     "product_key": f"{platform}_{seller}_{pno}", "product_no": pno,
                     "product_name": name, "price_sale": price})


def test_end_to_end(tmp_path):
    db = str(tmp_path / "t.db")
    ours = [_row("todaysales", "푸드팡", "1", "초코시럽(리고/567g)", 5000),
            _row("todaysales", "푸드팡", "2", "카페시럽(청정원/1.5L)", 9000)]
    comps = [_row("baemin", "A", "10", "리고 초코시럽 585g", 6000),      # 단가 1025.6 > 우리 881.8 → 우리가 최저
             _row("foodspring", "B", "20", "청정원 카페시럽 1.5L", 7000)]  # 우리가 28.6% 비쌈
    with connect(db) as conn:
        replace_snapshots(conn, "2026-10-28", "todaysales", ours)
        replace_snapshots(conn, "2026-10-28", "baemin", comps[:1])
        replace_snapshots(conn, "2026-10-28", "foodspring", comps[1:])
        sugg = matching.suggest(ours, comps, CFG["matching"])
        assert {(s["our_key"], s["comp_key"], s["status"]) for s in sugg} >= {
            ("todaysales_푸드팡_1", "baemin_A_10", "auto"), ("todaysales_푸드팡_2", "foodspring_B_20", "auto")}
        matching.save_suggestions(conn, sugg)
        # 사람이 거절한 매핑은 재매칭해도 살아나지 않음
        matching.set_status(conn, "todaysales_푸드팡_2", "foodspring_B_20", "rejected", "tester")
        matching.save_suggestions(conn, matching.suggest(ours, comps, CFG["matching"]))
        assert compare.build(conn, "2026-10-28", CFG["report"]) == 1
        matching.set_status(conn, "todaysales_푸드팡_2", "foodspring_B_20", "confirmed", "tester")
        assert compare.build(conn, "2026-10-28", CFG["report"]) == 2

        rows = {r["our_key"]: r for r in conn.execute("SELECT * FROM daily_comparison")}
        assert rows["todaysales_푸드팡_1"]["grade"] == "lowest"
        assert rows["todaysales_푸드팡_2"]["grade"] == "very_weak"
        assert rows["todaysales_푸드팡_2"]["gap_pct"] == 28.6

        # 다음날: 경쟁사 초코시럽 가격 인하로 최저가 역전
        replace_snapshots(conn, "2026-10-29", "todaysales", ours)
        replace_snapshots(conn, "2026-10-29", "baemin", [_row("baemin", "A", "10", "리고 초코시럽 585g", 4500)])
        compare.build(conn, "2026-10-29", CFG["report"])  # 식봄은 전일 데이터로 대체
        s = gather(conn, "2026-10-29", CFG["report"])
        assert [r["our_key"] for r in s["lost_lowest"]] == ["todaysales_푸드팡_1"]
        assert [r["our_key"] for r in s["comp_drops"]] == ["todaysales_푸드팡_1"]
        assert build_blocks(s)[0]["type"] == "header"
