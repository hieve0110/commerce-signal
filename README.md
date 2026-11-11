# commerce-signal
커머스 플랫폼들의 신호 포착하기

커머스 경쟁사(식봄, 네이버페이, 쿠팡, 카카오쇼핑, 배민상회 등)의 공지·업데이트와 뉴스를 매일 모아 보는 대시보드입니다.

## 구조

```
[수집기 + AI]  →  [구글 시트]  →  [index.html]
 매일 아침          데이터 저장소      화면 (누구나 접속)
```

- 데이터: [Commerce Signal DB](https://docs.google.com/spreadsheets/d/16kEIBlp7reU8LdVL9V6wtDVouYVNK2yH8qGN1SsaVVY/edit)
  - `updates` 탭: 공식 공지·블로그·보도자료 (무엇이 바뀌었나, 유저 가치, 타겟 유저, 한 줄 인사이트 등)
  - `news` 탭: 언론 기사 (같은 칸 구성 + 언론사)
  - `sources` 탭: 수집 대상 출처와 읽는 방법(`method`), 뉴스 검색어(`keywords`)
  - `seen` 탭: 이미 판단한 글 (넣은 것과 버린 것 모두). 다음 날 다시 보지 않으려고 씁니다.
- 화면: `index.html` 한 파일. 페이지가 열릴 때 공개된 시트를 읽어서 보여줍니다.

## 수집기 (`collector/`)

| 단계 | 명령 | 하는 일 |
|---|---|---|
| ① 수집 | `npm run collect` | `sources`를 돌며 아직 안 본 새 글 후보를 `collector/out/candidates.json`에 모읍니다 |
| ② 본문 | `npm run read -- --limit 40` | 후보 글의 본문을 `collector/out/articles.json`에 읽어 옵니다 |
| ③ 판단 | AI (Claude) | [`collector/GUIDE.md`](collector/GUIDE.md)대로 관련 있는 글만 골라 칸을 채우고 시트에 씁니다 |

`sources`의 `method` 칸에 따라 읽는 방법이 달라요.

| method | 방법 |
|---|---|
| `html` | 페이지 HTML을 바로 읽음 (막히면 curl로 다시 시도) |
| `browser` | Playwright 브라우저로 화면이 다 그려진 뒤 읽음 |
| `json` | Zendesk 고객센터 JSON API |
| `naver_news` | `keywords`의 검색어마다 네이버 뉴스 "최근 1일" 검색 |
| `-` | 막혀 있어서 수집하지 않음 |

①②는 Node 22 이상이 필요하고, `browser` 출처는 Playwright(Chromium)가 필요합니다.

## 로컬에서 화면 보기

```
npm run serve
```

브라우저에서 http://localhost:8000 을 엽니다.
