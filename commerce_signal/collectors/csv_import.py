"""경쟁사 가격을 CSV로 직접 넣는 경로 (자동 수집이 막혔을 때, MD가 조사한 가격 등).

필수 컬럼: product_name, price_sale
선택 컬럼: seller_name, product_no, spec, price_original, delivery_type, is_free_delivery
"""
from __future__ import annotations

import csv
import hashlib

from . import finalize


def collect(path: str, platform: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            name = (r.get("product_name") or "").strip()
            if not name or not r.get("price_sale"):
                continue
            seller = (r.get("seller_name") or "").strip()
            pno = (r.get("product_no") or "").strip() or hashlib.md5(f"{seller}|{name}".encode()).hexdigest()[:10]
            rows.append(finalize({
                "platform": platform,
                "seller_id": seller,
                "seller_name": seller,
                "product_key": f"{platform}_{seller}_{pno}",
                "product_no": pno,
                "product_name": name,
                "spec": r.get("spec", ""),
                "category": "",
                "price_original": float(r["price_original"]) if r.get("price_original") else None,
                "price_sale": float(r["price_sale"]),
                "delivery_type": r.get("delivery_type", ""),
                "delivery_summary": "",
                "is_free_delivery": int(str(r.get("is_free_delivery", "")).lower() in ("1", "true", "y")),
                "stock": None,
            }))
    return rows
