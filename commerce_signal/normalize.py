"""상품명 정규화와 용량/중량 파싱 → 단위가격 계산.

비교는 판매가가 아니라 단위가격(100g·100ml·1개당)으로 한다.
용량이 다른 상품(예: 1kg vs 500g×2)을 공정하게 비교하기 위해서다.
"""
from __future__ import annotations

import html
import re

# 단위 → (차원, 기본단위 환산 배수)
_UNITS = {
    "kg": ("g", 1000.0), "키로": ("g", 1000.0), "g": ("g", 1.0), "그램": ("g", 1.0),
    "l": ("ml", 1000.0), "리터": ("ml", 1000.0), "ml": ("ml", 1.0), "cc": ("ml", 1.0),
}
_COUNT_UNITS = r"(?:ea|개입|개|입|매|팩|봉|병|캔|박스|box|pcs|p|구|롤|스틱|포|t)"

_MEASURE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|키로|그램|g|리터|ml|cc|l)(?![a-wyz])"
    r"(?:\s*[x×*]\s*(\d+)\s*" + _COUNT_UNITS + r"?)?",
    re.IGNORECASE,
)
_COUNT_ONLY = re.compile(r"(\d+)\s*" + _COUNT_UNITS + r"(?![a-z가-힣])", re.IGNORECASE)

_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|<[^>]*>")
_LOGISTICS_TAG = re.compile(r"(?:김해)?d-\d+", re.IGNORECASE)   # 배송 리드타임 표기 'D-2', '김해D-3'
_ORIGIN = re.compile(r"[가-힣]{1,6}산")                          # 원산지 '중국산', '국내산'
_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")
_STOPWORDS = {
    "대용량", "업소용", "식자재", "카페", "카페용", "베이커리", "홈카페", "냉동", "냉장", "실온",
    "국산", "국내산", "수입", "박스", "box", "ea", "set", "세트", "개", "개입", "입", "무료배송",
    "직배송", "택배", "코스트코", "pac", "pak", "외식", "티백",
}

# 단위가격 표시 기준
UNIT_BASE = {"g": 100.0, "ml": 100.0, "ea": 1.0}
UNIT_LABEL = {"g": "100g", "ml": "100ml", "ea": "1개"}


def clean_name(name: str) -> str:
    return html.unescape(name or "").strip()


def parse_measure(text: str) -> tuple[float | None, str | None]:
    """상품명/규격에서 총 용량을 (값, 'g'|'ml'|'ea')로 반환.

    - '150ml*20ea' → (3000, 'ml'),  '25Gx40' → (1000, 'g')
    - '1.25kg(8입)' → (1250, 'g')   (괄호 속 입수는 내용물 개수로 보고 곱하지 않음)
    - '또띠아 12매' → (12, 'ea'),  '카누 100T' → (100, 'ea')
    """
    text = _THOUSANDS.sub("", clean_name(text).lower())
    found = []
    for m in _MEASURE.finditer(text):
        dim, mult = _UNITS[m.group(2).lower()]
        count = int(m.group(3)) if m.group(3) else 1
        found.append((float(m.group(1)) * mult * max(count, 1), dim))
    if found:
        # 같은 단위가 여러 번 나오면 가장 큰 값 = 판매 단위 전체 용량
        # 예) '600G,…,14.4KG(600G*24EA)/BOX' → 14.4kg
        dim = found[0][1]
        total = max(v for v, d in found if d == dim)
        if total > 0:
            return total, dim
    m = _COUNT_ONLY.search(_BRACKETS.sub(" ", text)) or _COUNT_ONLY.search(text)
    if m and int(m.group(1)) > 0:
        return float(m.group(1)), "ea"
    return None, None


def unit_price(price: float | None, measure: float | None, unit: str | None) -> float | None:
    if not price or not measure or not unit:
        return None
    return round(price / measure * UNIT_BASE[unit], 2)


def normalize_name(name: str, seller_name: str = "") -> str:
    text = clean_name(name).lower()
    if seller_name:
        text = text.replace(seller_name.lower(), " ")
    text = _LOGISTICS_TAG.sub(" ", _THOUSANDS.sub("", text))
    text = _MEASURE.sub(" ", text)
    text = _COUNT_ONLY.sub(" ", text)
    text = _NON_WORD.sub(" ", text)
    # 괄호 안 브랜드(예: '딸기잼(오뚜기/850g)')는 비교에 중요하므로 지우지 않고 구분자로만 취급
    return " ".join(t for t in text.split()
                    if t not in _STOPWORDS and not t.isdigit() and not _ORIGIN.fullmatch(t))


def tokens(norm: str) -> set[str]:
    return {t for t in norm.split() if len(t) >= 2}


def bigrams(norm: str) -> set[str]:
    s = norm.replace(" ", "")
    return {s[i:i + 2] for i in range(len(s) - 1)}
