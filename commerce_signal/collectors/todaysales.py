"""오늘얼마(우리 마켓) 상품 수집 — Shopby Shop API /products/search."""
from __future__ import annotations

import time

import requests

from . import USER_AGENT, finalize


def _fetch_page(cfg: dict, page: int, retries: int = 3) -> dict:
    headers = {
        "clientid": cfg["client_id"],
        "version": "1.0",
        "platform": "PC",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    params = {
        "categoryNos": cfg["category_no"],
        "pageNumber": page,
        "pageSize": cfg["page_size"],
        "hasTotalCount": "true",
        "order.by": "POPULAR",
        "order.direction": "DESC",
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(f"{cfg['api_base']}/products/search", headers=headers,
                                params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def to_row(item: dict, category_no: str) -> dict:
    sale = float(item.get("salePrice") or 0)
    discount = float(item.get("immediateDiscountAmt") or 0) + float(item.get("additionDiscountAmt") or 0)
    delivery = item.get("deliveryConditionInfo") or {}
    partner_no = str(item.get("partnerNo", ""))
    product_no = str(item.get("productNo", ""))
    return finalize({
        "platform": "todaysales",
        "seller_id": partner_no,
        "seller_name": item.get("partnerName") or "",
        "product_key": f"todaysales_{partner_no}_{product_no}",
        "product_no": product_no,
        "product_name": item.get("productName", ""),
        "spec": "",
        "category": item.get("displayCategoryNos") or category_no,
        "price_original": sale or None,
        "price_sale": (sale - discount) or None,
        "delivery_type": "택배" if "택배" in (item.get("partnerName") or "") else "직배송",
        "delivery_summary": delivery.get("summary", ""),
        "is_free_delivery": int(item.get("deliveryConditionType") == "FREE"),
        "stock": item.get("stockCnt"),
    })


def collect(cfg: dict, log=print) -> list[dict]:
    first = _fetch_page(cfg, 1)
    total = int(first.get("totalCount") or 0)
    pages = max(1, -(-total // cfg["page_size"]))
    log(f"[오늘얼마] 카테고리 {cfg['category_no']}: {total}개 / {pages}페이지")
    items = list(first.get("items", []))
    for page in range(2, pages + 1):
        time.sleep(cfg.get("request_interval_sec", 0.3))
        items.extend(_fetch_page(cfg, page).get("items", []))
    rows, seen = [], set()
    for item in items:
        if item.get("saleStatusType") not in (None, "ONSALE"):
            continue
        row = to_row(item, cfg["category_no"])
        if row["product_key"] in seen:
            continue
        seen.add(row["product_key"])
        rows.append(row)
    log(f"[오늘얼마] 판매중 {len(rows)}개 수집")
    return rows
