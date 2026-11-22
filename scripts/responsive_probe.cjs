#!/usr/bin/env node
'use strict';

// Original bounded observation helper. Uses an existing project Playwright install.
// It does not install dependencies, attach to a human browser, or assert an audit pass.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { createRequire } = require('node:module');

const HELP = `Responsive observation helper (no audit verdict)

Usage:
  node responsive_probe.cjs --url URL --out NEW_DIR --project PROJECT_DIR
    [--browser chromium|webkit|firefox] [--widths 390,768,1440] [--trace]

Requires an existing playwright or @playwright/test installation resolvable from
PROJECT_DIR, plus its matching browser engine. Nothing is downloaded or installed.
NEW_DIR must not already exist. Widths: 128..3840 pixels, at most 12 unique sizes.
Each width gets a fresh, anonymous browser context at height 900; no host profile,
cookies, login, clicks, form submissions, or storage state is imported or exported.
Non-GET/HEAD/OPTIONS requests and service workers are blocked. Even a GET can
have server-side effects; use an authorized test URL. Screenshots mask form fields
but other visible content, labels, titles and URL paths may still be private.

Writes snapshot.json and viewport PNGs. No page is labelled passed. Console text,
request/response bodies, headers and URL queries/fragments are not saved in JSON.
--trace is opt-in: traces can include private DOM, URLs and network data; review
before sharing. Tracing is off by default. Never publish the output automatically.

Exit codes: 0 observation collected (not a product pass); 1 error/partial result;
2 blocked by dependency/engine, environment permission or inputs; 130/143 interrupted.
`;

class ProbeError extends Error {
  constructor(code, category) { super(category); this.code = code; this.category = category; }
}

function parseArgs(argv) {
  if (argv.length === 1 && ['--help', '-h'].includes(argv[0])) return { help: true };
  const values = {};
  const valueFlags = new Set(['--url', '--out', '--project', '--browser', '--widths']);
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (Object.hasOwn(values, flag)) throw new ProbeError(2, 'duplicate_argument');
    if (flag === '--trace') values[flag] = true;
    else if (valueFlags.has(flag) && argv[i + 1] && !argv[i + 1].startsWith('--')) {
      values[flag] = argv[++i];
    } else throw new ProbeError(2, 'invalid_or_missing_argument');
  }
  if (!values['--url'] || !values['--out'] || !values['--project']) {
    throw new ProbeError(2, 'required_arguments_missing');
  }
  let url;
  try { url = new URL(values['--url']); } catch { throw new ProbeError(2, 'invalid_url'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new ProbeError(2, 'url_requires_http_without_userinfo');
  }
  const browser = values['--browser'] || 'chromium';
  if (!['chromium', 'webkit', 'firefox'].includes(browser)) throw new ProbeError(2, 'invalid_browser');
  const widthText = values['--widths'] || '390,768,1440';
  if (!/^\d+(,\d+)*$/.test(widthText)) throw new ProbeError(2, 'invalid_widths');
  const widths = [...new Set(widthText.split(',').map(Number))];
  if (widths.length > 12 || widths.some(w => !Number.isInteger(w) || w < 128 || w > 3840)) {
    throw new ProbeError(2, 'widths_out_of_bounds');
  }
  let project;
  try {
    project = fs.realpathSync(path.resolve(values['--project']));
    if (!fs.statSync(project).isDirectory()) throw new Error();
  } catch { throw new ProbeError(2, 'project_directory_unavailable'); }
  return { url: url.href, out: path.resolve(values['--out']), project, browser, widths, trace: !!values['--trace'] };
}

function publicLocation(raw) {
  try {
    const u = new URL(raw);
    if (!['http:', 'https:'].includes(u.protocol)) return { scheme: u.protocol, locationOmitted: true };
    return { origin: u.origin, path: u.pathname.slice(0, 512), queryOmitted: !!u.search, fragmentOmitted: !!u.hash };
  } catch { return { locationOmitted: true }; }
}

function errorCategory(error) {
  if (error instanceof ProbeError) return error.category;
  const message = String(error && error.message || ''); // Classify locally; never emit raw errors.
  if (error && error.name === 'TimeoutError') return 'timeout';
  if (/Executable doesn.t exist|browser executable.*not found|Host system is missing dependencies|error while loading shared libraries/i.test(message)) return 'browser_engine_unavailable';
  if (/Operation not permitted|Permission denied|\bEACCES\b|\bEPERM\b/i.test(message)) return 'runtime_permission_denied';
  if (/Target.*closed|browser.*closed|page.*closed/i.test(message)) return 'browser_or_page_closed';
  if (/ERR_NAME_NOT_RESOLVED|NS_ERROR_UNKNOWN_HOST/i.test(message)) return 'dns_failure';
  if (/ERR_CERT|SSL|TLS|CERTIFICATE/i.test(message)) return 'tls_failure';
  if (/ERR_CONNECTION|ECONNREFUSED|NS_ERROR_CONNECTION/i.test(message)) return 'connection_failure';
  return 'operation_failed';
}

function loadPlaywright(project) {
  const localRequire = createRequire(path.join(project, 'package.json'));
  for (const name of ['playwright', '@playwright/test']) {
    try {
      const api = localRequire(name);
      if (api.chromium && api.firefox && api.webkit) return { api, packageName: name };
    } catch { /* Try the second documented package, without installing it. */ }
  }
  throw new ProbeError(2, 'playwright_dependency_unavailable');
}

function counters() {
  return { consoleErrors: 0, uncaughtPageErrors: 0, failedRequests: 0, httpErrorResponses: 0,
    blockedNonReadRequests: 0, blockedCredentialUrls: 0, countLimitReached: false,
    failureCategories: {}, httpStatuses: {} };
}

function count(object, key) {
  if (object[key] >= 1000000) object.countLimitReached = true;
  else object[key] = (object[key] || 0) + 1;
}

function bucket(object, key, max = 40) {
  if (!Object.hasOwn(object, key) && Object.keys(object).length >= max) key = 'other';
  object[key] = Math.min((object[key] || 0) + 1, 1000000);
}

function requestFailureCategory(request) {
  let message = '';
  try { message = String(request.failure()?.errorText || ''); } catch { /* No raw error retained. */ }
  if (/ABORT|BLOCK|CANCEL/i.test(message)) return 'aborted_or_blocked';
  if (/NAME_NOT_RESOLVED|UNKNOWN_HOST|DNS/i.test(message)) return 'dns';
  if (/CERT|SSL|TLS/i.test(message)) return 'tls';
  if (/TIMED_OUT|TIMEOUT/i.test(message)) return 'timeout';
  if (/CONNECTION|CONNECT/i.test(message)) return 'connection';
  return 'other';
}

// Runs in the page. Only reads layout and label metadata; it never reads .value,
// storage, cookies, HTML, request bodies, or the text content of editable fields.
function inspectPage() {
  const cap = (s, n = 120) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const isField = el => /^(INPUT|TEXTAREA|SELECT|OPTION|DATALIST|SCRIPT|STYLE)$/.test(el.tagName)
    || el.hasAttribute('contenteditable') || ['textbox', 'searchbox'].includes(el.getAttribute('role'));
  const safeText = root => {
    let text = '', scanned = 0;
    const walk = node => {
      if (++scanned > 128 || text.length >= 240) return;
      if (node.nodeType === Node.TEXT_NODE) text += ' ' + node.textContent;
      else if (node.nodeType === Node.ELEMENT_NODE && !isField(node)) {
        for (const child of node.childNodes) walk(child);
      }
    };
    walk(root);
    return cap(text);
  };
  const roleOf = el => {
    const explicit = cap(el.getAttribute('role'), 40).split(' ')[0];
    if (explicit) return explicit;
    if (el.tagName === 'BUTTON' || el.tagName === 'SUMMARY') return 'button';
    if (el.tagName === 'A') return 'link';
    if (el.tagName === 'TEXTAREA' || el.hasAttribute('contenteditable')) return 'textbox';
    if (el.tagName === 'SELECT') return el.multiple ? 'listbox' : 'combobox';
    if (el.tagName === 'INPUT') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      return ({ checkbox: 'checkbox', radio: 'radio', range: 'slider', number: 'spinbutton',
        button: 'button', submit: 'button', reset: 'button', search: 'searchbox', hidden: 'hidden' })[type] || 'textbox';
    }
    return 'control';
  };
  const labelOf = el => {
    const aria = el.getAttribute('aria-label');
    if (aria) return cap(aria);
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const names = labelledBy.split(/\s+/).slice(0, 5).map(id => document.getElementById(id)).filter(Boolean).map(safeText);
      if (names.join('').trim()) return cap(names.join(' '));
    }
    if (el.labels?.length) return cap(Array.from(el.labels).slice(0, 3).map(safeText).join(' '));
    if (['BUTTON', 'A', 'SUMMARY'].includes(el.tagName) || ['button', 'link', 'tab', 'menuitem'].includes(el.getAttribute('role'))) return safeText(el);
    return cap(el.getAttribute('title'));
  };
  const bounds = rect => ({ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) });
  const visible = el => {
    const style = getComputedStyle(el), rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const all = document.querySelectorAll('*');
  const scanLimit = Math.min(all.length, 2000);
  let overflowCount = 0;
  const overflowSamples = [];
  for (let i = 0; i < scanLimit; i++) {
    const el = all[i];
    if (!visible(el)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.left < -1 || rect.right > innerWidth + 1) {
      overflowCount++;
      if (overflowSamples.length < 40) overflowSamples.push({ tag: el.tagName.toLowerCase(), indexWithinScan: i, bounds: bounds(rect) });
    }
  }
  const controls = document.querySelectorAll('button,a[href],input,textarea,select,summary,[role],[contenteditable]');
  const controlScanLimit = Math.min(controls.length, 1000);
  let visibleControlCount = 0;
  const samples = [];
  for (let i = 0; i < controlScanLimit; i++) {
    const el = controls[i];
    if (!visible(el)) continue;
    visibleControlCount++;
    if (samples.length < 200) samples.push({ tag: el.tagName.toLowerCase(), roleHint: roleOf(el), nameHint: labelOf(el),
      disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true', bounds: bounds(el.getBoundingClientRect()) });
  }
  return {
    title: cap(document.title, 200),
    overflow: { viewportWidth: innerWidth, documentScrollWidth: document.documentElement.scrollWidth,
      horizontalOverflowPixels: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      elementsExtendingViewportWithinScan: overflowCount, scannedElements: scanLimit,
      scanTruncated: all.length > scanLimit, samples: overflowSamples,
      interpretation: 'geometry_observation_not_a_defect_verdict' },
    controls: { totalMatched: controls.length, scanned: controlScanLimit, scanTruncated: controls.length > controlScanLimit,
      visibleWithinScan: visibleControlCount, samplesCapped: visibleControlCount > samples.length,
      nameMethod: 'DOM_label_hint_not_complete_accessibility_name_computation', samples }
  };
}

let activeBrowser;
let interruptedCode = 0;
for (const [signal, code] of [['SIGINT', 130], ['SIGTERM', 143]]) {
  process.on(signal, () => {
    interruptedCode = code;
    if (activeBrowser) activeBrowser.close().catch(() => {});
  });
}

async function main() {
  let args;
  try { args = parseArgs(process.argv.slice(2)); }
  catch (error) { process.stderr.write(`Blocked: ${errorCategory(error)}. Use --help.\n`); return error.code || 2; }
  if (args.help) { process.stdout.write(HELP); return 0; }

  // mkdir without recursive ensures an existing path (including a symlink) is never reused.
  try { fs.mkdirSync(args.out, { mode: 0o700 }); }
  catch (error) {
    process.stderr.write(`Blocked: ${error.code === 'EEXIST' ? 'output_already_exists' : 'output_directory_unavailable'}.\n`);
    return 2;
  }
  const snapshot = {
    schemaVersion: 1, startedAt: new Date().toISOString(), finishedAt: null,
    status: 'in_progress', auditVerdict: 'not_evaluated', build: { status: 'unknown' },
    target: publicLocation(args.url), browser: { name: args.browser, version: null },
    requestedWidths: args.widths, viewportHeight: 900, traceEnabled: args.trace,
    scope: 'anonymous_navigation_and_static_observation_only',
    limitations: ['No interactions, authentication, permissions, persistence, backend correctness or deployment identity verified.',
      'Viewport screenshots do not cover all scrolling content; DOM scans and error counts are bounded.',
      'DOM role/name hints are not a complete accessibility audit. Geometry overflow may be intentional.',
      'Form controls are masked in screenshots; other visible content, titles, labels and URL paths may be private.',
      'Non-read HTTP methods and service workers are blocked; this may affect rendering. GET endpoints can still have side effects.'],
    observations: [], errors: []
  };
  let exitCode = 0;
  try {
    const loaded = loadPlaywright(args.project);
    snapshot.browser.package = loaded.packageName;
    const browserType = loaded.api[args.browser];
    if (args.trace) process.stderr.write('Trace enabled: output may contain private DOM, full URLs and network data. Review before sharing.\n');
    activeBrowser = await browserType.launch({ headless: true, timeout: 20000 });
    snapshot.browser.version = activeBrowser.version();
    for (const width of args.widths) {
      if (interruptedCode) break;
      const observation = { observedAt: new Date().toISOString(), width, height: 900, status: 'in_progress',
        navigation: { status: 'not_attempted', httpStatus: null }, telemetry: counters(), errors: [],
        screenshot: null, trace: null };
      snapshot.observations.push(observation);
      let context;
      let tracing = false;
      try {
        context = await activeBrowser.newContext({ viewport: { width, height: 900 }, acceptDownloads: false, serviceWorkers: 'block' });
        await context.route('**/*', async route => {
          try {
            const request = route.request();
            let u;
            try { u = new URL(request.url()); } catch { await route.abort(); return; }
            if (u.username || u.password) {
              count(observation.telemetry, 'blockedCredentialUrls'); await route.abort();
            } else if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
              count(observation.telemetry, 'blockedNonReadRequests'); await route.abort();
            } else await route.continue();
          } catch { /* A closed context can settle an intercepted request before the handler. */ }
        });
        if (typeof context.routeWebSocket === 'function') await context.routeWebSocket('**/*', socket => socket.close());
        if (args.trace) { await context.tracing.start({ screenshots: true, snapshots: true, sources: false }); tracing = true; }
        const page = await context.newPage();
        page.setDefaultTimeout(10000);
        page.on('console', message => { if (message.type() === 'error') count(observation.telemetry, 'consoleErrors'); });
        page.on('pageerror', () => count(observation.telemetry, 'uncaughtPageErrors'));
        page.on('requestfailed', request => {
          count(observation.telemetry, 'failedRequests');
          bucket(observation.telemetry.failureCategories, requestFailureCategory(request));
        });
        page.on('response', response => {
          if (response.status() >= 400) {
            count(observation.telemetry, 'httpErrorResponses');
            bucket(observation.telemetry.httpStatuses, String(response.status()));
          }
        });
        page.on('popup', popup => popup.close().catch(() => {}));
        try {
          const response = await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: 20000 });
          observation.navigation = { status: 'loaded', httpStatus: response ? response.status() : null, finalLocation: publicLocation(page.url()) };
        } catch (error) {
          observation.navigation = { status: errorCategory(error) === 'timeout' ? 'timeout' : 'failed', httpStatus: null,
            finalLocation: publicLocation(page.url()), errorCategory: errorCategory(error) };
          observation.errors.push('navigation_' + errorCategory(error)); exitCode = 1;
        }
        if (interruptedCode) break;
        // Bounded settling window; do not wait indefinitely for network-idle on streaming apps.
        await page.waitForTimeout(400);
        try { Object.assign(observation, await page.evaluate(inspectPage)); }
        catch (error) { observation.errors.push('inspection_' + errorCategory(error)); exitCode = 1; }
        try {
          const filename = `viewport-${width}.png`;
          const png = await page.screenshot({ type: 'png', fullPage: false, timeout: 10000,
            mask: [page.locator('input,textarea,select,[contenteditable],[role="textbox"],[role="searchbox"]')] });
          fs.writeFileSync(path.join(args.out, filename), png, { flag: 'wx', mode: 0o600 });
          observation.screenshot = filename;
        } catch (error) { observation.errors.push('screenshot_' + errorCategory(error)); exitCode = 1; }
        observation.status = observation.errors.length ? 'partial' : 'observed';
      } catch (error) {
        observation.errors.push(errorCategory(error)); observation.status = 'failed'; exitCode = 1;
      } finally {
        if (context) {
          if (tracing) {
            try {
              const filename = `trace-${width}.zip`;
              // Playwright's trace API has no exclusive-write option. Stage the trace
              // privately, then use wx so even an unexpected output collision is safe.
              const traceTemp = fs.mkdtempSync(path.join(os.tmpdir(), 'responsive-probe-trace-'));
              try {
                const stagedTrace = path.join(traceTemp, 'trace.zip');
                await context.tracing.stop({ path: stagedTrace });
                fs.writeFileSync(path.join(args.out, filename), fs.readFileSync(stagedTrace), { flag: 'wx', mode: 0o600 });
                observation.trace = filename;
              } finally { fs.rmSync(traceTemp, { recursive: true, force: true }); }
            } catch (error) { observation.errors.push('trace_' + errorCategory(error)); exitCode = 1; }
          }
          await context.close().catch(() => {});
        }
        if (interruptedCode) observation.status = 'interrupted';
        else if (observation.errors.length && observation.status === 'observed') observation.status = 'partial';
        observation.finishedAt = new Date().toISOString();
      }
    }
  } catch (error) {
    const category = errorCategory(error);
    exitCode = error.code === 2 || ['browser_engine_unavailable', 'runtime_permission_denied'].includes(category) ? 2 : 1;
    snapshot.errors.push(category);
  } finally {
    if (activeBrowser) await activeBrowser.close().catch(() => {});
    activeBrowser = null;
    if (interruptedCode) exitCode = interruptedCode;
    snapshot.status = interruptedCode ? 'interrupted' : exitCode === 2 ? 'blocked'
      : exitCode === 1 ? (snapshot.observations.length ? 'partial' : 'failed') : 'observed';
    snapshot.finishedAt = new Date().toISOString();
    try { fs.writeFileSync(path.join(args.out, 'snapshot.json'), JSON.stringify(snapshot, null, 2) + '\n', { flag: 'wx', mode: 0o600 }); }
    catch { process.stderr.write('Error: snapshot_write_failed; any completed images remain in the new output directory.\n'); return 1; }
  }
  process.stdout.write(JSON.stringify({ status: snapshot.status, auditVerdict: 'not_evaluated',
    observedWidths: snapshot.observations.length, snapshot: path.join(args.out, 'snapshot.json') }) + '\n');
  return exitCode;
}

main().then(code => { process.exitCode = code; }).catch(() => {
  process.stderr.write('Error: unexpected_probe_failure. No raw page or network error data emitted.\n');
  process.exitCode = 1;
});
