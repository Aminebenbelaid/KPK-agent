// Capture real UI screenshots from the live app for the project website.
import puppeteer from 'puppeteer-core';
import { mkdirSync } from 'fs';

const BASE = process.env.KPK_URL || 'https://keinplankarriere.qantra.dev';
const ADMIN = process.env.KPK_ADMIN_KEY || '';
const OUT = process.env.KPK_OUT || './shots';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 2 },
  args: ['--no-sandbox', '--hide-scrollbars'],
});

const page = await browser.newPage();
const shot = async (name) => {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log('shot:', name);
};

await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 60000 });
await wait(1500);

if (ADMIN) {
  const claimed = await page.evaluate(async (key) => {
    const r = await fetch('/api/session/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    });
    return r.status;
  }, ADMIN);
  console.log('owner claim ->', claimed);
  await page.reload({ waitUntil: 'networkidle2' });
  await wait(2500);
}

await shot('01-jobs');

const opened = await page.evaluate(() => {
  const row = document.querySelector('.job-row');
  if (!row) return false;
  row.click();
  return true;
});
if (opened) {
  await wait(2000);
  await shot('02-job-detail');
  await page.evaluate(() => {
    const m = document.querySelector('.modal');
    if (m) m.scrollTop = m.scrollHeight;
  });
  await wait(1200);
  await shot('03-apply-assistant');
  await page.evaluate(() => {
    const b = document.querySelector('.modal-close');
    if (b) b.click();
  });
  await wait(800);
}

const clickTab = async (label) => {
  const ok = await page.evaluate((l) => {
    const b = [...document.querySelectorAll('.tab-btn')].find(
      (x) => x.textContent.trim().toLowerCase() === l
    );
    if (!b) return false;
    b.click();
    return true;
  }, label);
  await wait(2500);
  return ok;
};

if (await clickTab('experience')) await shot('04-experience');
if (await clickTab('trends')) { await wait(4000); await shot('05-trends'); }
if (await clickTab('settings')) await shot('06-settings');

await clickTab('jobs');
await page.setViewport({ width: 420, height: 860, deviceScaleFactor: 2 });
await wait(2000);
await shot('07-mobile');

await browser.close();
console.log('done ->', OUT);
