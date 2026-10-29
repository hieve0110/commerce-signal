"""배민상회 셀러별 상품 수집.

공식 공개 API가 아니므로 언제든 응답 형식이 바뀌거나 차단될 수 있다.
차단(403 등)되면 우회하지 말고 csv_import 로 대체하거나 제휴/데이터 제공 경로를 확인할 것.
"""
from __future__ import annotations

import time

import requests

from . import USER_AGENT, finalize

DELIVERY_LABEL = {
    "DIRECT_DELIVERY": "직배송", "FRESH": "새벽배송", "MARKET_DAY": "장날배송",
    "NORMAL_DELIVERY": "택배", "PARCEL": "택배",
}


def _fetch_page(cfg: dict, seller_id: str, page: int) -> dict:
    resp = requests.get(
        f"{cfg['api_base']}/sellers/{seller_id}/goods/paging",
        params={"page": page, "size": 40, "sortType": "RECOMMEND"},
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"baemin success=false: {str(data)[:200]}")
    return data["data"]["goodsList"]


def to_row(item: dict, seller: dict) -> dict:
    goods_id = str(item.get("id", ""))
    return finalize({
        "platform": "baemin",
        "seller_id": seller["id"],
        "seller_name": seller["name"],
        "product_key": f"baemin_{seller['id']}_{goods_id}",
        "product_no": goods_id,
        "product_name": item.get("name", ""),
        "spec": item.get("sizeDesc", ""),
        "category": "",
        "price_original": item.get("customerPrice") or None,
        "price_sale": item.get("goodsPrice") or None,
        "delivery_type": DELIVERY_LABEL.get(item.get("goodsDeliveryType", ""), item.get("goodsDeliveryType", "")),
        "delivery_summary": item.get("unitPriceDesc", ""),
        "is_free_delivery": int(bool(item.get("freeShipping"))),
        "stock": None,
    })


def collect(cfg: dict, log=print) -> list[dict]:
    allowed = set(cfg.get("collect_delivery_types", []))
    rows: list[dict] = []
    for seller in cfg["sellers"]:
        try:
            first = _fetch_page(cfg, seller["id"], 0)
            pages = int(first.get("totalPages") or 1)
            items = list(first.get("content", []))
            for page in range(1, pages):
                time.sleep(cfg.get("request_interval_sec", 1.0))
                items.extend(_fetch_page(cfg, seller["id"], page).get("content", []))
        except Exception as e:  # 셀러 하나 실패해도 나머지는 계속
            log(f"[배민상회] {seller['name']} 수집 실패: {type(e).__name__}: {e}")
            continue
        kept = [to_row(i, seller) for i in items if not allowed or i.get("goodsDeliveryType") in allowed]
        log(f"[배민상회] {seller['name']}: {len(kept)}개 (전체 {len(items)}개)")
        rows.extend(kept)
        time.sleep(cfg.get("request_interval_sec", 1.0))
    return rows
