# commerce-signal
커머스 플랫폼들의 신호 포착하기

경쟁사(식봄, 네이버페이, 쿠팡, 카카오쇼핑, 배민상회)의 공지·업데이트를 모아 보는 대시보드입니다.

## 구조

```
[수집 + AI 요약]  →  [구글 시트]  →  [index.html]
   (3단계 예정)      데이터 저장소      화면
```

- 데이터: [Commerce Signal DB](https://docs.google.com/spreadsheets/d/16kEIBlp7reU8LdVL9V6wtDVouYVNK2yH8qGN1SsaVVY/edit)
  - `updates` 탭: 수집한 업데이트 (무엇이 바뀌었나, 유저 가치, 타겟 유저, 한 줄 인사이트 등)
  - `sources` 탭: 수집 대상 회사와 공지 URL
- 화면: `index.html` 한 파일. 페이지가 열릴 때 공개된 시트를 읽어서 보여줍니다.

## 로컬에서 보기

```
python3 -m http.server 8000
```

브라우저에서 http://localhost:8000 을 엽니다.
