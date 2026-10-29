"""플랫폼별 수집기. 모든 수집기는 snapshots 테이블 형식의 dict 리스트를 반환한다."""
from __future__ import annotations

from ..normalize import clean_name, parse_measure, unit_price

USER_AGENT = "commerce-signal/0.1 (todaysales price monitor POC)"


def finalize(row: dict) -> dict:
    """공통 후처리: 이름 정리 + 용량 파싱 + 단위가격 계산."""
    row["product_name"] = clean_name(row.get("product_name", ""))
    value, unit = parse_measure(f"{row['product_name']} {row.get('spec') or ''}")
    row["measure_value"], row["measure_unit"] = value, unit
    row["unit_price"] = unit_price(row.get("price_sale"), value, unit)
    return row
