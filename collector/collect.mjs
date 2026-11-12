// ① 수집: 시트의 sources를 돌면서 "아직 안 본 새 글" 후보를 모아요.
//
//   npm run collect                 # 기본: 최근 14일, 출처마다 최대 15건
//   npm run collect -- --days 7 --per-source 8 --only 쿠팡
//
// 결과: collector/out/candidates.json (후보 목록), collector/out/report.json (출처별 상태)
import {
  loadSheet, fetchText, getBrowserContext, closeBrowser, htmlToText, decodeEntities,
  findDate, normalizeUrl, urlKey, writeOut, mapLimit,
} from './lib.mjs';

const args = parseArgs(process.argv.slice(2));
const DAYS = Number(args.days ?? 14);
const PER_SOURCE = Number(args['per-source'] ?? 15);
const since = new Date(Date.now() - DAYS * 86400000).toISOString().slice(0, 10);
const DATE_RE = /(20\d\d\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}\.?)|((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, 20\d\d)/g;

// ------------------------------------------------------------
// 1. 시트 읽기: 수집 대상 + 이미 본 글
// ------------------------------------------------------------
const [sources, updates, news, seen] = await Promise.all(
  ['sources', 'updates', 'news', 'seen'].map(name => loadSheet(name).catch(() => [])),
);
const known = new Set([
  ...updates.map(r => r.source_url), ...news.map(r => r.news_url), ...seen.map(r => r.url),
].filter(Boolean).map(urlKey));

const active = sources
  .filter(s => s.active === 'Y' && s.method && s.method !== '-')
  .filter(s => !args.only || s.company === args.only);

console.log(`출처 ${active.length}곳 확인 · 이미 본 글 ${known.size}건 · ${since} 이후 글만`);

// ------------------------------------------------------------
// 2. 출처마다 링크 모으기 (method 칸에 따라 방법이 달라요)
// ------------------------------------------------------------
const report = [];
const candidates = [];
const taken = new Set();

await mapLimit(active, 4, async (src) => {
  const entry = { row: src._row, company: src.company, service: src.service, method: src.method, found: 0, fresh: 0, status: 'ok', error: '' };
  try {
    const links = await collectLinks(src);
    entry.found = links.length;
    const kind = src.method === 'naver_news' || src.source_type === 'NEWS' ? 'news' : 'notice';
    const fresh = [];
    for (const l of links) {
      const key = urlKey(l.url);
      if (!key || known.has(key) || taken.has(key)) continue;
      if (l.date && l.date < since) continue;
      taken.add(key);
      fresh.push({ kind, company: src.company, service: src.service, source_row: src._row, method: src.method, ...l });
      if (fresh.length >= PER_SOURCE) break;
    }
    entry.fresh = fresh.length;
    if (!links.length) entry.status = 'empty';
    candidates.push(...fresh);
  } catch (e) {
    entry.status = 'error';
    entry.error = String(e.message || e).slice(0, 160);
  }
  report.push(entry);
  console.log(`${entry.status.padEnd(5)} ${String(entry.fresh).padStart(3)}건 새 글 / ${String(entry.found).padStart(3)}건 | ${src.company} · ${src.service} (${src.method})${entry.error ? ' · ' + entry.error : ''}`);
});
await closeBrowser();

// 공지 먼저, 그다음 날짜가 최신인 순서
candidates.sort((a, b) => (a.kind === b.kind ? 0 : a.kind === 'notice' ? -1 : 1) || String(b.date).localeCompare(String(a.date)));
report.sort((a, b) => a.row - b.row);

const file = writeOut('candidates.json', { collected_at: new Date().toISOString(), since, candidates });
writeOut('report.json', report);
console.log(`\n후보 ${candidates.length}건 → ${file}`);

// ============================================================
// 방법별 링크 수집
// ============================================================
async function collectLinks(src) {
  switch (src.method) {
    case 'html': return linksFromHtml(src.url, (await fetchOk(src.url)).text);
    case 'browser': return linksFromBrowser(src.url);
    case 'json': return linksFromZendesk(src.url);
    case 'naver_news': return linksFromNaverNews(src);
    default: throw new Error(`모르는 method: ${src.method}`);
  }
}

async function fetchOk(url) {
  const res = await fetchText(url);
  if (res.status >= 400) throw new Error(`HTTP ${res.status}`);
  return res;
}

// html: <a> 태그와 그 뒤의 글자에서 제목·날짜를 찾아요
function linksFromHtml(pageUrl, html) {
  const out = [];
  const re = /<a\b[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
  let m;
  while ((m = re.exec(html))) {
    const title = htmlToText(m[2]);
    // 날짜는 보통 제목 뒤에 있지만, Shopify처럼 제목 앞에 있는 곳도 있어요
    const after = htmlToText(html.slice(m.index, m.index + m[0].length + 400));
    const before = htmlToText(html.slice(Math.max(0, m.index - 300), m.index));
    out.push({ title, url: m[1], date: findDate(after) || findDate(before) });
  }
  return keepArticles(pageUrl, out);
}

// browser: 화면이 다 그려진 뒤 읽어요. 두 가지 방법을 써 봐요.
//   1) "날짜가 들어 있는 줄" 찾기: 링크 대신 클릭 이벤트로 만든 목록(토스, 무신사 등)도 읽혀요
//   2) 1)로 못 찾으면 <a> 링크와, 링크를 감싼 줄의 글자에서 날짜 찾기
async function linksFromBrowser(pageUrl) {
  const context = await getBrowserContext();
  const page = await context.newPage();
  try {
    const res = await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 40000 });
    if (res && res.status() >= 400) throw new Error(`HTTP ${res.status()}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(3000);

    const rows = await page.evaluate(rowsFromPage);
    const fromRows = keepArticles(pageUrl, rows.map(r => ({
      title: r.text.replace(DATE_RE, ' ').replace(/^(공지|중요|NEW)\s+/i, '').replace(/\s+/g, ' ').trim(),
      url: r.href || `${pageUrl}#t=${encodeURIComponent(r.text.slice(0, 80))}`,
      date: findDate(r.text),
    })));
    if (fromRows.length) return fromRows;

    const raw = await page.$$eval('a[href]', as => as.map(a => {
      const box = a.closest('li, tr, article, [class*="item"], [class*="Item"], [class*="card"], [class*="Card"], [class*="list"] > *') || a.parentElement;
      return { href: a.href, text: (a.innerText || '').trim(), around: (box?.innerText || '').slice(0, 400) };
    }));
    return keepArticles(pageUrl, raw.map(r => ({ title: r.text.split('\n')[0], url: r.href, date: findDate(r.around + ' ' + r.text) })));
  } finally {
    await page.close();
  }
}

// 브라우저 안에서 실행돼요: 날짜가 들어 있는 가장 작은 덩어리를 찾아 한 줄(글 하나)로 봐요
function rowsFromPage() {
  const re = /(20\d\d\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2})|((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, 20\d\d)/;
  const all = [...document.querySelectorAll('li, tr, article, a, div')]
    .filter(el => { const t = (el.innerText || '').trim(); return t.length >= 12 && t.length <= 300 && re.test(t); });
  const leaves = all.filter(el => !all.some(o => o !== el && el.contains(o)));
  // 날짜만 있는 작은 칸이면 제목까지 들어오도록 부모로 올라가요
  const rows = leaves.map(el => {
    let r = el;
    while (r.parentElement && (r.innerText || '').replace(re, '').trim().length < 8) r = r.parentElement;
    return r;
  });
  return [...new Set(rows)].map(el => ({
    text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300),
    href: (el.closest('a') || el.querySelector('a'))?.href || '',
  }));
}

// json: 카카오쇼핑처럼 Zendesk 고객센터는 글 목록을 JSON으로 줘요
async function linksFromZendesk(apiUrl) {
  const url = apiUrl + (apiUrl.includes('?') ? '&' : '?') + 'sort_by=created_at&sort_order=desc&per_page=30';
  const data = JSON.parse((await fetchOk(url)).text);
  return (data.articles || []).map(a => ({ title: a.title, url: a.html_url, date: String(a.created_at).slice(0, 10) }));
}

// naver_news: 검색어마다 "최근 1일" 뉴스를 검색해요 (검색어당 최대 10건)
async function linksFromNaverNews(src) {
  const keywords = String(src.keywords || '').split(',').map(s => s.trim()).filter(Boolean);
  const out = [];
  for (const kw of keywords) {
    const url = src.url.replace('{keyword}', encodeURIComponent(kw)).replace(/pd=\d+/, 'pd=4');
    const html = (await fetchOk(url)).text;
    const re = /<a\b[^>]*href="(https?:\/\/[^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
    let m;
    while ((m = re.exec(html))) {
      const host = new URL(decodeEntities(m[1])).hostname;
      if (/naver\.(com|me)$/.test(host)) continue;
      const title = htmlToText(m[2]).replace(/새 창 열림$/, '').trim();
      if (title.length < 12 || title.length > 120) continue;
      const around = htmlToText(html.slice(Math.max(0, m.index - 600), m.index + 200));
      out.push({ title, url: normalizeUrl(m[1]), date: findDate(around), keyword: kw });
    }
  }
  return out;
}

// 메뉴·로그인·페이지 번호 같은 링크는 빼고 "글"처럼 보이는 링크만 남겨요
function keepArticles(pageUrl, links) {
  const base = new URL(pageUrl);
  const site = base.hostname.replace(/^(www|m)\./, '');
  const listKey = urlKey(pageUrl);
  const out = [];
  const seenHere = new Set();
  for (const l of links) {
    const url = normalizeUrl(l.url, pageUrl);
    if (!url || !/^https?:/.test(url)) continue;
    const u = new URL(url);
    if (!u.hostname.replace(/^(www|m)\./, '').endsWith(site)) continue;
    const key = urlKey(url);
    if (key === listKey || seenHere.has(key)) continue;
    const path = u.pathname + u.search;
    const looksLikeArticle = u.hash.startsWith('#t=') || /\d{3,}/.test(path) || (u.pathname.split('/').filter(Boolean).pop() || '').length >= 12;
    if (!looksLikeArticle || /login|signup|javascript:|\/(tag|category|categories|author)\//i.test(path)) continue;
    const title = String(l.title || '').replace(/\s+/g, ' ').trim();
    if (title.length < 6 || title.length > 200) continue;
    seenHere.add(key);
    out.push({ title, url, date: l.date || '' });
  }
  // 날짜가 붙은 글이 하나라도 있으면, 날짜 없는 링크는 메뉴·배너일 가능성이 커서 빼요
  return out.some(l => l.date) ? out.filter(l => l.date) : out;
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) out[argv[i].slice(2)] = argv[i + 1];
  return out;
}
