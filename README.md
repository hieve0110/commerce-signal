# commerce-signal
커머스 플랫폼들의 신호 포착하기

## POC: 카페/베이커리 가격 비교

오늘얼마 마켓 **베이커리·카페** 카테고리 상품을 배민상회·식봄 상품과 비교해서, 매일 아침 슬랙으로 리포트를 보내고 대시보드에서 일자별 결과와 로우데이터를 볼 수 있게 합니다.

```
① 수집      오늘얼마(Shopby Shop API, 카테고리 1270088) + 배민상회 + 식봄
② 매칭      상품명·브랜드·용량으로 같은 상품 후보 찾기 → 자동 매칭 / 검수 필요
③ 비교      단위가격(100g·100ml·1개당)으로 경쟁 최저가와 비교 → 등급
④ 리포트    슬랙: 최저가 TOP(앱푸시 후보) · 크게 비싼 상품 · 전일 대비 변동
⑤ 대시보드  일자별 리포트 · 상품 가격 추이 · 로우데이터(CSV) · 매핑 검수
```

### 등급 기준 (`config/poc.toml`에서 변경)

| 등급 | 우리 단가 vs 경쟁 최저 단가 |
|---|---|
| 🟢 최저가 | 같거나 쌈 |
| 🟡 경쟁 | +5% 이내 |
| 🟠 열위 | +5 ~ 15% |
| 🔴 크게 열위 | +15% 초과 |

- 가격은 **즉시할인 반영가**. 쿠폰·배송비는 아직 미포함
- 용량을 읽지 못한 상품은 사람이 **확정한 매핑**일 때만 판매가로 비교

## 시작하기

```bash
pip install -r requirements.txt

# 1) 매일 돌리는 명령 (수집 → 매칭 → 비교 → 슬랙)
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."   # 없으면 화면에 출력
python -m commerce_signal daily

# 2) 대시보드
streamlit run dashboard/app.py
```

개별 단계:

```bash
python -m commerce_signal collect --only todaysales     # 특정 플랫폼만 수집
python -m commerce_signal match                         # 매칭 후보 다시 계산
python -m commerce_signal compare --date 2026-10-29     # 비교표 재계산
python -m commerce_signal report --dry-run              # 슬랙 보내지 않고 미리보기
python -m pytest                                        # 테스트
```

### 슬랙 웹훅 만들기
1. https://api.slack.com/apps → **Create New App** → From scratch
2. **Incoming Webhooks** 켜기 → **Add New Webhook to Workspace** → 리포트 받을 채널 선택
3. 나온 URL을 `SLACK_WEBHOOK_URL`로 설정 (GitHub에서는 Settings → Secrets → Actions)

### 매일 자동 실행 (GitHub Actions)
`.github/workflows/daily-price-report.yml` 이 매일 07:40 KST에 `daily`를 실행하고, 누적 데이터(`data/commerce_signal.db`)를 저장소에 커밋합니다.
- 기본 브랜치(main)에 머지된 뒤부터 동작
- Secrets에 `SLACK_WEBHOOK_URL`, (선택) Variables에 `DASHBOARD_URL` 등록
- 가격 데이터가 저장소에 쌓이므로 **저장소는 비공개(private)로 유지**

## 매핑 검수
대시보드 **🔗 매핑 검수** 탭에서 후보를 확정/거절합니다.
- `auto` (자동 매칭): 유사도 0.82 이상 + 용량 단위 같음 + 크기 2배 이내 → 리포트에 바로 반영
- `suggested` (검수 필요): 확정해야 반영
- 확정/거절한 결과는 다음 매칭 때도 유지됩니다

## 경쟁사 수집 주의사항
- 배민상회·식봄 수집기는 공식 공개 API가 아닌 웹 내부 API를 사용합니다. 응답 형식이 바뀌거나 차단될 수 있고, **차단되면 우회하지 말고** 아래 CSV 업로드로 대체합니다. 운영 전 약관·법무 확인이 필요합니다.
- 경쟁사 수집이 실패하면 최대 2일 전 데이터로 비교하고, 슬랙 리포트에 수집 건수가 표시됩니다.

경쟁사 가격 CSV 업로드 (필수 컬럼 `product_name`, `price_sale`):

```bash
python -m commerce_signal import-csv baemin_prices.csv --platform baemin
```

## 구조

```
commerce_signal/
  collectors/   todaysales.py · baemin.py · foodspring.py · csv_import.py
  normalize.py  상품명 정규화, 용량 파싱, 단위가격
  matching.py   매칭 후보 생성·저장
  compare.py    일자별 비교표 (daily_comparison)
  report.py     슬랙 리포트
  db.py         SQLite 스키마 (snapshots · mappings · daily_comparison)
dashboard/app.py  Streamlit 대시보드
config/poc.toml   카테고리, 경쟁 셀러 목록, 매칭·등급 기준
```
