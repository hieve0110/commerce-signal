// ② 본문 읽기: candidates.json의 후보 글을 열어서 본문을 가져와요.
//
//   npm run read                    # 후보 앞에서부터 40건
//   npm run read -- --limit 60 --offset 40
//   npm run read -- --url https://...   # 글 하나만 (확인용)
//
// 결과: collector/out/articles.json
import {
  fetchText, getBrowserContext, closeBrowser, htmlToText, decodeEntities, findDate, readOut, writeOut, mapLimit,
} from './lib.mjs';

const args = parseArgs(process.argv.slice(2));
const LIMIT = Number(args.limit ?? 40);
const OFFSET = Number(args.offset ?? 0);
const MAX_CHARS = 2500;

const items = args.url
  ? [{ url: args.url, title: '' }]
  : (readOut('candidates.json')?.candidates ?? []).slice(OFFSET, OFFSET + LIMIT);
if (!items.length) { console.log('읽을 후보가 없어요. 먼저 npm run collect 를 실행하세요.'); process.exit(0); }

const articles = await mapLimit(items, 4, async (item) => {
  // 목록에만 있고 상세 주소가 없는 글(#t=)은 제목이 곧 내용이에요
  if (item.url.includes('#t=')) return { ...item, body: item.title, body_source: 'list' };
  try {
    let page = await fromFetch(item.url);
    // 본문에 제목 앞부분이 안 보이면 메뉴만 읽힌 것 → 브라우저로 다시 읽어요
    const head = (item.title || '').replace(/^\[[^\]]*\]\s*/, '').slice(0, 10);
    const missingTitle = head && !page.body.includes(head);
    if (page.status >= 400 || page.body.length < 200 || missingTitle) page = await fromBrowser(item.url, head).catch(() => page);
    return { ...item, ...page };
  } catch (e) {
    return { ...item, body: '', error: String(e.message || e).slice(0, 120) };
  }
});
await closeBrowser();

const file = writeOut('articles.json', articles);
const ok = articles.filter(a => a.body && a.body.length >= 200).length;
console.log(`본문 ${ok}/${articles.length}건 읽음 → ${file}`);
for (const a of articles) if (!a.body || a.body.length < 200) console.log(`  짧거나 실패: ${a.title?.slice(0, 40) || a.url} ${a.error ?? ''}`);

// ------------------------------------------------------------
async function fromFetch(url) {
  const { status, text } = await fetchText(url);
  return { status, ...extract(text) };
}

async function fromBrowser(url, head = '') {
  const context = await getBrowserContext();
  const page = await context.newPage();
  try {
    const res = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 40000 });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);
    const html = await page.content();
    // 제목이 들어 있고 글자가 충분한 영역 중 가장 작은 것 = 본문
    const main = await page.evaluate((head) => {
      const boxes = [...document.querySelectorAll('article, main, section, div')]
        .map(el => ({ el, text: el.innerText || '' }))
        .filter(b => b.text.length >= 200 && (!head || b.text.includes(head)))
        .sort((a, b) => a.text.length - b.text.length);
      return (boxes[0]?.text) || document.body.innerText;
    }, head);
    const meta = extract(html);
    return { ...meta, status: res ? res.status() : 0, body: clean(main).slice(0, MAX_CHARS), body_source: 'browser' };
  } finally {
    await page.close();
  }
}

// 언론사 이름, 발행일, 본문을 뽑아요
function extract(html) {
  const meta = (name) => {
    const m = html.match(new RegExp(`<meta[^>]+(?:property|name)=["']${name}["'][^>]+content=["']([^"']*)["']`, 'i'))
      || html.match(new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]+(?:property|name)=["']${name}["']`, 'i'));
    return m ? decodeEntities(m[1]).trim() : '';
  };
  const article = html.match(/<article[\s\S]*?<\/article>/i)?.[0];
  const paragraphs = [...html.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)].map(m => htmlToText(m[1])).filter(t => t.length > 30).join(' ');
  const body = [article && htmlToText(article), paragraphs, htmlToText(html)]
    .find(t => t && t.length >= 300) || paragraphs || htmlToText(html);
  return {
    page_title: meta('og:title') || htmlToText(html.match(/<title>([\s\S]*?)<\/title>/i)?.[1] || ''),
    press: meta('og:site_name') || meta('twitter:site'),
    published: (meta('article:published_time') || meta('og:regDate') || '').slice(0, 10) || findDate(htmlToText(html).slice(0, 3000)),
    body: clean(body).slice(0, MAX_CHARS),
    body_source: 'fetch',
  };
}

function clean(text) {
  return text.replace(/\s+/g, ' ').replace(/(카카오톡|페이스북|트위터|URL복사|공유하기|글자크기)\s*/g, '').trim();
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) out[argv[i].slice(2)] = argv[i + 1];
  return out;
}
