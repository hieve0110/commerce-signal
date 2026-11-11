// 수집기가 같이 쓰는 도구들: 시트 읽기, 페이지 가져오기, 브라우저, 주소 정리
import { execSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const SHEET_ID = '16kEIBlp7reU8LdVL9V6wtDVouYVNK2yH8qGN1SsaVVY';
export const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), 'out');
export const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36';

// ------------------------------------------------------------
// 구글 시트 읽기: 공개 시트는 CSV로 받을 수 있어요
// ------------------------------------------------------------
export async function loadSheet(name) {
  const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&headers=1&sheet=${encodeURIComponent(name)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`시트 ${name} 읽기 실패: ${res.status}`);
  const rows = parseCsv(await res.text());
  const [header, ...body] = rows;
  // 시트의 실제 행 번호(헤더가 1행)를 같이 기억해 두면 나중에 그 행을 고칠 수 있어요
  return body.map((r, i) => Object.fromEntries([...header.map((h, j) => [h, r[j] ?? '']), ['_row', i + 2]]));
}

function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

// ------------------------------------------------------------
// 페이지 가져오기
// ------------------------------------------------------------
export async function fetchText(url, timeoutMs = 25000) {
  const res = await fetch(url, { headers: { 'User-Agent': UA, 'Accept-Language': 'ko-KR,ko;q=0.9' }, signal: AbortSignal.timeout(timeoutMs) });
  const out = { status: res.status, text: await res.text(), url: res.url };
  // 쿠팡처럼 Node의 접속은 막고 curl은 받아 주는 사이트가 있어요
  if (out.status === 403) return curlText(url, timeoutMs) ?? out;
  return out;
}

function curlText(url, timeoutMs) {
  try {
    const raw = execSync(`curl -sSL --max-time ${Math.round(timeoutMs / 1000)} -A ${JSON.stringify(UA)} -w '\\n%{http_code}' ${JSON.stringify(url)}`,
      { maxBuffer: 50 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] }).toString();
    const cut = raw.lastIndexOf('\n');
    return { status: Number(raw.slice(cut + 1)), text: raw.slice(0, cut), url };
  } catch { return null; }
}

// 자바스크립트로 그리는 페이지용 브라우저. 처음 필요할 때 한 번만 띄워요.
let browserPromise;
async function loadPlaywright() {
  try { return await import('playwright'); }
  catch {
    const globalRoot = execSync('npm root -g').toString().trim();
    return await import(join(globalRoot, 'playwright', 'index.mjs'));
  }
}
export async function getBrowserContext() {
  browserPromise ??= loadPlaywright().then(async ({ chromium }) => {
    const browser = await chromium.launch();
    const context = await browser.newContext({ userAgent: UA, locale: 'ko-KR' });
    return { browser, context };
  });
  return (await browserPromise).context;
}
export async function closeBrowser() {
  if (browserPromise) (await browserPromise).browser.close();
}

// ------------------------------------------------------------
// HTML → 글자
// ------------------------------------------------------------
export function htmlToText(html) {
  return decodeEntities(html
    .replace(/<(script|style|noscript|svg)[^>]*>[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<[^>]+>/g, ' '))
    .replace(/\s+/g, ' ').trim();
}
export function decodeEntities(s) {
  return s
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;|&#x27;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)));
}

// ------------------------------------------------------------
// 날짜 찾기: "2026-11-10", "2026.11.10", "26.11.06", "November 3, 2026", "3시간 전" 등
// ------------------------------------------------------------
const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
export function findDate(text, now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const iso = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`;
  let m;
  if ((m = text.match(/(20\d\d)\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})/))) return iso(m[1], m[2], m[3]);
  if ((m = text.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}), (20\d\d)/i))) return iso(m[3], MONTHS[m[1].toLowerCase()], m[2]);
  if ((m = text.match(/(?<!\d)(\d{2})\.(\d{2})\.(\d{2})(?!\d)/))) return iso(2000 + Number(m[1]), m[2], m[3]);
  // "November 10"처럼 연도가 없으면 올해로 보고, 미래 날짜가 되면 작년으로 봐요
  if ((m = text.match(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2})\b(?!,? ?\d)/i))) {
    let y = now.getFullYear();
    if (iso(y, MONTHS[m[1].toLowerCase()], m[2]) > iso(y, now.getMonth() + 1, now.getDate())) y -= 1;
    return iso(y, MONTHS[m[1].toLowerCase()], m[2]);
  }
  if ((m = text.match(/(\d+)\s*(분|시간|일)\s*전/))) {
    const back = new Date(now);
    if (m[2] === '일') back.setDate(back.getDate() - Number(m[1]));
    else if (m[2] === '시간') back.setHours(back.getHours() - Number(m[1]));
    return iso(back.getFullYear(), back.getMonth() + 1, back.getDate());
  }
  return '';
}

// ------------------------------------------------------------
// 주소 정리: 같은 글인데 꼬리표(utm 등)만 다른 주소를 같은 것으로 봐요
// ------------------------------------------------------------
export function normalizeUrl(raw, base) {
  try {
    const u = new URL(decodeEntities(raw), base);
    // 글마다 주소가 없는 목록은 "목록주소#t=제목"으로 구분해요 (collect.mjs의 rowsFromPage)
    if (!u.hash.startsWith('#t=')) u.hash = '';
    for (const k of [...u.searchParams.keys()]) {
      if (/^(utm_|ref$|from$|OutUrl$|SNS$|headerType$|searchValue$|page$|division$)/i.test(k)) u.searchParams.delete(k);
    }
    return u.toString().replace(/\/$/, '');
  } catch { return ''; }
}

// 중복 비교용 키: http/https, www./m. 차이까지 무시해요 (저장은 normalizeUrl 결과로)
export function urlKey(raw) {
  const clean = normalizeUrl(raw);
  return clean.replace(/^https?:\/\//, '').replace(/^(www|m)\./, '').toLowerCase();
}

export function writeOut(name, data) {
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(join(OUT_DIR, name), JSON.stringify(data, null, 1));
  return join(OUT_DIR, name);
}
export function readOut(name) {
  const p = join(OUT_DIR, name);
  return existsSync(p) ? JSON.parse(readFileSync(p, 'utf8')) : null;
}

// 동시에 n개씩만 처리 (사이트에 부담을 덜 주려고)
export async function mapLimit(items, n, fn) {
  const out = new Array(items.length); let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k], k); }
  }));
  return out;
}
