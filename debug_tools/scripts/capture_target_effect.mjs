#!/usr/bin/env node
// 目标效果评测采集：把原始 DSL 送入本地渲染器，
// 采集 3x 截图、DOM 盒模型与 Web 可见性证据。不修改批跑产物。

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { collectTargetEvidence } from './target_evidence.mjs';
import { collectWebQuality } from './web_quality.mjs';

const require = createRequire(import.meta.url);
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_VIEWPORT = { width: 1600, height: 1000 };

function parseViewport(value) {
  const match = /^(\d+)x(\d+)$/i.exec(String(value || '').trim());
  if (!match) return { ...DEFAULT_VIEWPORT };
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (width <= 0 || height <= 0) return { ...DEFAULT_VIEWPORT };
  return { width, height };
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key.startsWith('--')) throw new Error(`未知参数：${key}`);
    if (value === undefined || value.startsWith('--')) throw new Error(`${key} 缺少参数值`);
    result[key.slice(2)] = value;
  }
  if (!result.jobs || !result.output) throw new Error('必须提供 --jobs 与 --output');
  return result;
}

async function existingPath(candidate) {
  if (!candidate) return null;
  try {
    const stat = await fs.stat(candidate);
    return stat.isFile() ? candidate : null;
  } catch {
    return null;
  }
}

async function browserExecutable() {
  const configured = await existingPath(process.env.WIDGET_DEBUG_GALLERY_BROWSER_EXECUTABLE);
  if (configured) return configured;
  const candidates = process.platform === 'win32'
    ? [
      'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    ]
    : process.platform === 'darwin'
      ? [
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      ]
      : ['/usr/bin/microsoft-edge', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
  for (const candidate of candidates) {
    const found = await existingPath(candidate);
    if (found) return found;
  }
  throw new Error(
    '未找到 Edge/Chrome/Chromium。可通过 WIDGET_DEBUG_GALLERY_BROWSER_EXECUTABLE 指定浏览器路径。',
  );
}

function loadPlaywright() {
  const candidates = [
    process.env.WIDGET_DEBUG_PLAYWRIGHT_CORE,
    path.resolve(SCRIPT_DIR, '..', 'node_modules', 'playwright-core'),
  ].filter(Boolean);
  const failures = [];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      failures.push(`${candidate}: ${error.message}`);
    }
  }
  try {
    return require('playwright-core');
  } catch (error) {
    failures.push(`playwright-core: ${error.message}`);
  }
  throw new Error(`无法加载 playwright-core：\n${failures.join('\n')}`);
}

async function setZoom(page, zoom) {
  await page.evaluate((value) => {
    const range = document.querySelector('.card-renderer__preview-controls input[type="range"]');
    if (!range) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(range, String(value));
    range.dispatchEvent(new Event('input', { bubbles: true }));
    range.dispatchEvent(new Event('change', { bubbles: true }));
  }, zoom);
}

async function setSource(page, text) {
  await page.evaluate((value) => {
    const area = document.querySelector('textarea[aria-label="DSL 输入"]');
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(area, value);
    area.dispatchEvent(new Event('input', { bubbles: true }));
  }, text);
}

async function waitForAssets(page) {
  await page.evaluate(async () => {
    if (document.fonts) await document.fonts.ready;
    const images = Array.from(document.querySelectorAll('.card-renderer__surface img'));
    await Promise.all(images.map((image) => {
      if (image.complete) return Promise.resolve();
      return new Promise((resolve) => {
        image.addEventListener('load', resolve, { once: true });
        image.addEventListener('error', resolve, { once: true });
      });
    }));
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
}

async function renderVariant(page, job, variant, scale) {
  const source = await fs.readFile(variant.source, 'utf8');
  await page.getByRole('button', { name: '清空', exact: true }).click();
  await page.waitForFunction(() => {
    const status = document.querySelector('.card-renderer__status');
    return status && status.textContent.trim() === '请输入 JSONL 或 DSL';
  }, null, { timeout: 30_000 });
  await setSource(page, source);
  if (job.size === '2x2' || job.size === '2x4') {
    await page.locator('.card-renderer__toolbar select').selectOption(job.size);
  }
  await page.waitForTimeout(120);
  await page.getByRole('button', { name: '渲染', exact: true }).click();
  await page.waitForFunction(() => {
    const status = document.querySelector('.card-renderer__status');
    if (!status) return false;
    return status.textContent.trim().startsWith('已渲染') || status.classList.contains('is-error');
  }, null, { timeout: 60_000 });
  const statusText = (await page.locator('.card-renderer__status').textContent() || '').trim();
  if (!statusText.startsWith('已渲染')) {
    return { ok: false, error: statusText || '渲染失败' };
  }
  await page.waitForSelector('.card-renderer__surface', { timeout: 30_000 });
  const runtimeError = page.locator('.card-renderer__surface .card-renderer__runtime-error');
  if (await runtimeError.count()) {
    return { ok: false, error: (await runtimeError.first().textContent() || '').trim() || '卡片渲染失败' };
  }
  await waitForAssets(page);
  const surface = page.locator('.card-renderer__surface').first();
  const evidence = await surface.evaluate(collectTargetEvidence, { size: job.size, scale });
  evidence.webQuality = await surface.evaluate(collectWebQuality);
  await fs.mkdir(path.dirname(variant.png), { recursive: true });
  await surface.screenshot({ path: variant.png, animations: 'disabled' });
  const png = await fs.readFile(variant.png);
  evidence.imageSha256 = createHash('sha256').update(png).digest('hex');
  evidence.sourceSha256 = createHash('sha256').update(source.replace(/\r\n?/g, '\n')).digest('hex');
  await fs.writeFile(variant.evidence, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  return {
    ok: true,
    error: '',
    png: variant.png,
    evidence: variant.evidence,
    imageSha256: evidence.imageSha256,
    surface: evidence.surface,
    visibleText: evidence.visibleText,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const jobs = JSON.parse(await fs.readFile(args.jobs, 'utf8'));
  if (!Array.isArray(jobs)) throw new Error('jobs 文件必须是数组');
  const base = (args.base || 'http://127.0.0.1:8888/debug').replace(/\/+$/, '');
  const scale = Number(args.scale || 3);
  const viewport = parseViewport(args.viewport || process.env.DEBUG_TOOLS_CAPTURE_VIEWPORT);
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ executablePath: await browserExecutable(), headless: true });
  const errors = [];
  try {
    const context = await browser.newContext({
      viewport,
      deviceScaleFactor: scale,
    });
    const page = await context.newPage();
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    await page.goto(`${base}/renderer`, { waitUntil: 'domcontentloaded', timeout: 120_000 });
    await page.waitForSelector('textarea[aria-label="DSL 输入"]', { timeout: 120_000 });
    const autoRender = page.locator('.card-renderer__check input[type="checkbox"]');
    if (await autoRender.isChecked()) await autoRender.uncheck();
    await setZoom(page, 100);
    const items = [];
    for (const job of jobs) {
      for (const variant of job.variants || []) {
        let item;
        try {
          item = await renderVariant(page, job, variant, scale);
        } catch (error) {
          item = { ok: false, error: error instanceof Error ? error.message : String(error) };
        }
        items.push({ id: job.id, variant: variant.name, ...item });
      }
    }
    await fs.mkdir(args.output, { recursive: true });
    await fs.writeFile(
      path.join(args.output, 'target_capture.json'),
      `${JSON.stringify({ items, consoleErrors: errors.slice(0, 50), scale, viewport }, null, 2)}\n`,
      'utf8',
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
