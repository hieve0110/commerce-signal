"""식봄 셀러(vendor)별 상품 수집 — GraphQL.

공식 공개 API가 아니므로 언제든 응답 형식이 바뀌거나 차단될 수 있다.
차단되면 우회하지 말고 csv_import 로 대체하거나 제휴/데이터 제공 경로를 확인할 것.
"""
from __future__ import annotations

import time

import requests

from . import USER_AGENT, finalize

QUERY = """
query SellerGoods($id: ID!, $input: GoodsListInput!, $after: String, $areaId: ID) {
  goodsList(first: 80, after: $after, input: $input, areaId: $areaId) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges { node { nid name standard unit price { salePrice originalPrice discountRate } isFreeDelivery } }
  }
  node(id: $id) { ... on Vendor { nid name delivery { __typename } } }
}
"""
DELIVERY_LABEL = {"DirectDelivery": "직배송", "AggregateDelivery": "싱싱배송"}


def _fetch_page(cfg: dict, seller_id: str, after: str | None) -> dict:
    vendor = f"vendor_{seller_id}"
    variables = {
        "id": vendor,
        "input": {"sort": "POPULAR_DESC", "vendorId": vendor, "categoryId": "goodsCategoryNode_0",
                  "terms": "", "delivery": "ALL"},
        "after": after,
        "areaId": None,
    }
    resp = requests.post(
        cfg["api_url"], json={"query": QUERY, "variables": variables},
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}, timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("data"):
        raise RuntimeError(f"foodspring no data: {str(body.get('errors'))[:200]}")
    return body["data"]


def to_row(node: dict, seller_id: str, seller_name: str, delivery: str) -> dict:
    price = node.get("price") or {}
    nid = str(node.get("nid", ""))
    return finalize({
        "platform": "foodspring",
        "seller_id": seller_id,
        "seller_name": seller_name,
        "product_key": f"foodspring_{seller_id}_{nid}",
        "product_no": nid,
        "product_name": node.get("name", ""),
        "spec": node.get("standard", ""),
        "category": "",
        "price_original": price.get("originalPrice") or None,
        "price_sale": price.get("salePrice") or None,
        "delivery_type": delivery,
        "delivery_summary": node.get("unit", ""),
        "is_free_delivery": int(bool(node.get("isFreeDelivery"))),
        "stock": None,
    })


def collect(cfg: dict, log=print) -> list[dict]:
    rows: list[dict] = []
    for seller in cfg["sellers"]:
        seller_rows: list[dict] = []
        after = None
        try:
            while True:
                data = _fetch_page(cfg, seller["id"], after)
                vendor = data.get("node") or {}
                name = vendor.get("name") or seller["name"]
                delivery = DELIVERY_LABEL.get((vendor.get("delivery") or {}).get("__typename", ""), "")
                goods = data.get("goodsList") or {}
                seller_rows += [to_row(e["node"], seller["id"], name, delivery) for e in goods.get("edges", [])]
                page_info = goods.get("pageInfo") or {}
                if not page_info.get("hasNextPage"):
                    break
                after = page_info.get("endCursor")
                time.sleep(cfg.get("request_interval_sec", 0.5))
        except Exception as e:
            log(f"[식봄] {seller['name']} 수집 실패: {type(e).__name__}: {e}")
        log(f"[식봄] {seller['name']}: {len(seller_rows)}개")
        rows.extend(seller_rows)
    return rows
