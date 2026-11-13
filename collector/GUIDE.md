# 매일 수집 지침 (AI용)

매일 아침 이 문서대로 수집한다. 사람이 읽어도 이해할 수 있게 썼다.

- 시트: [Commerce Signal DB](https://docs.google.com/spreadsheets/d/16kEIBlp7reU8LdVL9V6wtDVouYVNK2yH8qGN1SsaVVY/edit) (ID `16kEIBlp7reU8LdVL9V6wtDVouYVNK2yH8qGN1SsaVVY`)
- 시트 쓰기는 Google Sheets 커넥터로 한다. 읽기는 스크립트가 공개 CSV로 한다.
- 날짜와 시각은 한국 시간(KST) 기준이다.

## 순서

1. `npm run collect`
   - 시트 `sources`의 사용 중인 출처를 돌며, `updates`·`news`·`seen`에 없는 새 글 후보를 `collector/out/candidates.json`에 모은다.
   - 출처별 결과는 `collector/out/report.json`에 남는다.
2. `npm run read -- --limit 40`
   - 후보 앞쪽 40건의 본문을 `collector/out/articles.json`에 읽어 온다. 공지가 먼저, 뉴스가 뒤에 온다.
   - 40건을 다 처리한 뒤 후보가 더 남았으면 `npm run read -- --offset 40 --limit 40`으로 한 번 더 한다. 하루 최대 80건까지만 처리한다. 남은 후보는 `seen`에 넣지 않는다. 다음 날 다시 후보로 올라온다.
3. 글마다 아래 "판단 기준"으로 **넣을지(added) / 버릴지(skipped)** 정한다.
4. 넣을 글은 아래 "칸 채우기 규칙"대로 채워서 시트에 쓴다.
   - 공식 공지·블로그·보도자료(`kind: notice`)는 `updates` 탭
   - 언론 기사(`kind: news`)는 `news` 탭
5. 이번에 판단한 글은 **넣은 것과 버린 것 모두** `seen` 탭에 쓴다. 그래야 다음 날 다시 보지 않는다.
6. `report.json`을 보고 `sources` 탭의 `last_checked`(G열)와 `status`(H열)를 고친다.
   - `ok` → `ok`, `empty` → `empty`, `error` → `error`
   - 에러가 났으면 `note`(I열) 맨 앞에 `[날짜] 에러 내용`을 붙인다. 원래 메모는 지우지 않는다.
7. 마지막에 "출처 n곳 확인, 후보 n건, 추가 n건(공지 n, 뉴스 n), 버림 n건, 에러 난 출처"를 한 단락으로 정리한다.

## 판단 기준

이 대시보드의 독자는 **커머스 플랫폼 기획자**다. "우리 서비스 기획에 참고가 되는가?"를 기준으로 고른다.

**넣는다**
- 새 기능, 서비스 출시·종료, 화면·구조 변경, 실험(테스트) 공지
- 판매자·입점사·광고주·구매자에게 영향을 주는 정책, 약관, 수수료, 정산, 배송, 반품 변경
- 광고 상품, 광고 지면, 광고 운영 방식의 변화
- 결제, 멤버십, 포인트, 제휴 구조의 변화 (단순 할인 행사는 제외)
- AI 커머스(쇼핑 에이전트, AI 추천, AI 광고 자동화)
- 실적, 투자, 인수, 규제, 제재처럼 경쟁 구도를 바꾸는 소식
- 커머스와 관련된 업계 흐름 기사 (해외 사례도 포함)

**낮은 점수(10~19)로 넣는다** — 화면에서 "주요만"을 고르면 숨겨지고 "전부"에서만 보인다
- 경쟁사 **공식 공지**(`kind: notice`) 중 시스템 점검, 제휴사·은행 작업으로 인한 일시 중단, 장애·복구 안내
- 공식 공지 중 특정 브랜드·가맹점과 하는 단순 할인·적립 이벤트
- 공식 공지 중 작은 운영 변경 (키워드그룹 추가, 행정구역 코드 변경, 계정 편의 기능 등)
- 이런 글은 칸을 짧게 채운다. `why_it_matters`와 `key_takeaway`는 한 문장이면 된다.

**버린다** (`seen`의 `reason`에 짧게 이유를 쓴다)
- 뉴스(`kind: news`) 중 단순 할인 행사, 퀴즈 정답, 당첨자 발표
- 커머스와 관계없는 글 (연예, 스포츠, 웹툰·콘텐츠, 지자체 행사, 일반 금융 상품 등)
- 같은 사건을 다룬 중복 기사: 가장 자세한 기사 하나만 넣고 나머지는 `중복: <넣은 기사 ID>`로 버린다. 이미 `news`나 `updates`에 같은 사건이 있어도 버린다.
- 본문을 못 읽어서 내용을 확인할 수 없는 글. 제목만으로 충분히 판단되면 넣어도 된다.

## 칸 채우기 규칙

`updates`와 `news`는 칸 구성이 거의 같다. 시트에 이미 있는 행들이 좋은 예시다. 쓰기 전에 몇 줄 읽고 말투와 길이를 맞춘다.

| 칸 | 규칙 |
|---|---|
| `update_id` / `news_id` | 영문 소문자와 숫자, `_`만 쓴다. 공지는 `회사slug_글번호` (예: `naverads_35081`, `naverpay_200022279`). 글 번호가 없으면 `회사slug_YYYYMMDD_짧은영단어`. 뉴스는 `언론사slug_기사번호` (예: `etnews_20261110000311`). 이미 있는 ID와 겹치면 안 된다. |
| `company` | 시트에 이미 쓰는 이름을 쓴다: 식봄, 네이버페이, 쿠팡, 카카오쇼핑, 배민상회, 배민, 네이버, 카카오, 토스, 당근, G마켓, 오늘의집, 무신사, Shopify, 업계. 업계 기사라도 주인공 회사가 분명하면 그 회사 이름을 쓴다. 투데이마케팅 기사는 기사 속 회사 이름을 쓴다. |
| `service` | 서비스나 제품 이름 (예: 플레이스광고, 쇼핑탭, Open API) |
| `published_at` | `YYYY-MM-DD`. 후보의 `date`, 없으면 본문의 날짜. 앞에 작은따옴표 `'`를 붙여 글자로 저장한다. |
| `update_type` (updates만) | FEATURE, POLICY, API, EXPERIMENT, LAUNCH, EVENT, PARTNERSHIP, PR 중 하나 |
| `press` (news만) | 언론사 이름 (예: 전자신문). `articles.json`의 `press`가 비면 기사 주소로 판단한다. |
| `title` | 원문 제목 그대로. 목록에서 붙은 "카테고리 명 일반 공지 일자…", "new 공통 2026-11-11" 같은 꼬리는 지운다. 영어 등 외국어 제목은 한국어로 옮기고 원제를 괄호에 붙인다. 예: `Shop 노출 자격 요건 변경 (Updated eligibility requirements for Shop)` |
| `summary` | 핵심 내용 1~2문장. 날짜, 숫자, 대상을 구체적으로 쓴다. 본문 끝까지 읽고 "단, ~는 제외" 같은 예외 조건이 있으면 꼭 넣는다. |
| `what_changed` | 바뀐 점만 짧게. "기존 → 변경" 형식이 좋다. |
| `user_value` | 이용자(판매자, 광고주, 구매자)가 얻는 것 1~2문장 |
| `target_user` | 누가 영향을 받는지 짧게 |
| `why_it_matters` | 경쟁 관점에서 왜 중요한지 2~3문장. 다른 회사 사례나 이미 시트에 있는 소식과 연결되면 언급한다. |
| `key_takeaway` | 한 줄 인사이트. "누가 무엇을 하고 있다. 그래서 무엇을 볼 만하다." 형식으로 두 문장 이내. |
| `keywords` | 쉼표로 구분한 3~6개, 띄어쓰기 없이 |
| `impact_score` | 0~100 숫자 (아래 기준) |
| `source_url` / `news_url` | 후보의 `url` 그대로 |
| `collected_at` | 오늘 날짜 `'YYYY-MM-DD` |

**중요도(`impact_score`) 기준**
- 80~100: 판매자·구매자 흐름이나 경쟁 구도를 바꾸는 변화 (수수료·정책 대개편, 대형 인수, 핵심 기능 출시)
- 60~79: 의미 있는 기능·정책·광고 상품 변화, 눈여겨볼 실험
- 40~59: 작은 기능 개선, 제휴 확대, 참고할 만한 업계 동향
- 20~39: 기록해 둘 정도의 운영 변화
- 10~19: 점검·일시 중단·장애 안내, 단순 할인·적립 이벤트, 작은 운영 변경 (위 "낮은 점수로 넣는다")
- 10 미만으로 판단되면 넣지 말고 버린다.

**문장 스타일**
- "~다"로 끝나는 짧은 평서문. 과장하는 말(혁신적, 획기적, 매우 중요)은 쓰지 않는다.
- 원문에 없는 사실을 지어내지 않는다. 추측은 "~로 보인다", "~할 수 있다"로 쓴다.
- 이모지는 쓰지 않는다.

## 시트에 쓰는 방법

1. 각 탭의 A열을 `get_values`로 읽어 마지막 행 다음 줄을 찾는다 (예: `updates!A:A`).
2. 탭마다 `update_values` 한 번에 여러 행을 쓴다. 값은 칸 순서대로 넣는다.
   - `updates`: update_id, company, service, published_at, update_type, title, summary, what_changed, user_value, target_user, why_it_matters, key_takeaway, keywords, impact_score, source_url, collected_at
   - `news`: news_id, company, service, published_at, press, title, summary, what_changed, user_value, target_user, why_it_matters, key_takeaway, keywords, impact_score, news_url, collected_at
   - `seen`: url, kind, decision(added/skipped), reason, title, checked_at
3. 날짜 칸은 `'2026-11-11`처럼 작은따옴표를 붙인다. 붙이지 않으면 시트가 날짜 형식으로 바꿔서 웹페이지가 빈칸으로 읽는다.
4. 다 쓴 뒤 `get_values`로 방금 쓴 범위를 다시 읽어 확인한다.

## 하지 말 것

- 시트의 기존 행을 지우거나 덮어쓰지 않는다. `sources`의 G·H·I열 갱신만 예외다.
- `sources`의 출처를 추가하거나 끄지 않는다. 문제가 있으면 마지막 정리에 적는다.
- 저장소에 커밋하지 않는다. 이 작업은 시트만 바꾼다.
