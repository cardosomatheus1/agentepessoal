/* Optional browser regression: build first, then run with an existing Playwright.
   PLAYWRIGHT_MODULE=/path/to/playwright node tests/connection-map.e2e.mjs
   No dependency install. Server binds only to loopback; data is entirely synthetic. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import http from 'node:http';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
// Resolve an optional, already installed test runner; no app dependency is added.
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright');
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(__dirname, '..');
const OUT = process.env.MAP_TEST_OUTPUT || path.join(os.tmpdir(), 'connection-map-results');
fs.mkdirSync(OUT, { recursive: true });
const TOKEN = 'synthetic-map-test-not-a-real-secret';
const results = { checks: [], screenshots: [], pageErrors: [], externalRequests: [] };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const pass = name => { results.checks.push(name); console.log('PASS', name); };
let server, browser, fixture, port, base;
function write(name, data) { const dest = path.join(fixture, name); fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, typeof data === 'string' ? data : JSON.stringify(data)); }
function hashes() { return fs.readdirSync(fixture, { recursive: true }).filter(f => fs.statSync(path.join(fixture, f)).isFile()).sort().map(f => [f, createHash('sha256').update(fs.readFileSync(path.join(fixture, f))).digest('hex')]); }
async function shot(page, filename) {
  const dest = path.join(OUT, filename);
  const viewport = page.viewportSize();
  // Tall capture at the same responsive width, avoiding scroll-container clipping.
  await page.setViewportSize({ ...viewport, height: 2200 });
  await page.locator('#conexoes').screenshot({ path: dest });
  await page.setViewportSize(viewport);
  results.screenshots.push(dest);
}
// Stand-in for the Agent Zero gateway (infra/vm/plugins/segundo_cerebro): the "session" is this flag; the bearer is
// added only on the API hop to Next and never seen by the browser. /logout ends the session like Agent Zero's.
let sessao = 'nenhuma', gateway, authFromBrowser = 0;
function startGateway(nextBase) {
  return new Promise((resolve, reject) => {
    gateway = http.createServer(async (req, res) => {
      if (req.headers.authorization) authFromBrowser++;
      const url = new URL(req.url, 'http://x');
      if (url.pathname === '/logout') { sessao = 'nenhuma'; res.writeHead(302, { Location: '/login?next=/segundo-cerebro' }); return res.end(); }
      if (url.pathname === '/login') { res.writeHead(200, { 'Content-Type': 'text/html' }); return res.end('<h1>login falso</h1>'); }
      if (url.pathname === '/api/segundo-cerebro' && sessao !== 'matheus') { res.writeHead(sessao === 'outra' ? 403 : 401, { 'Content-Type': 'application/json' }); return res.end('{}'); }
      const headers = url.pathname === '/api/segundo-cerebro' ? { Authorization: `Bearer ${TOKEN}` } : {};
      const r = await fetch(nextBase + url.pathname + (url.pathname === '/api/segundo-cerebro' ? '' : url.search), { headers, redirect: 'manual' });
      res.writeHead(r.status, { 'Content-Type': r.headers.get('content-type') || 'application/octet-stream', ...(r.headers.get('location') ? { Location: r.headers.get('location') } : {}) });
      res.end(Buffer.from(await r.arrayBuffer()));
    });
    gateway.on('error', reject);
    gateway.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${gateway.address().port}`));
  });
}
// The map is a Sigma (WebGL) canvas: counts come from the graph handed to the renderer, positions from its viewport.
async function drawn(page, nodes, edges) {
  await page.waitForFunction(([n, e]) => { const el = document.querySelector('[data-renderer]'); return el?.dataset.renderer === 'pronto' && el.dataset.nodes === String(n) && el.dataset.edges === String(e); }, [nodes, edges], { timeout: 20000 });
  assert.ok(await page.locator('[data-renderer] canvas').count() > 0);
}
const at = (page, id) => page.locator('[data-renderer]').evaluate((el, id) => el.__mapaViewport(id), id);
async function login(page) { sessao = 'matheus'; await page.goto(`${base}/segundo-cerebro`); await page.getByRole('heading', { name: 'Mapa de conexões', exact: true }).waitFor(); }
(async () => {
  try {
    fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'map-synthetic-'));
    write('memoria/decisoes/matheus.json', { decisoes: [{ id: 'd1', tema: 'Estilo sintético', valor: 'Objetivo e claro', estado: 'ativa' }] });
    write('memoria/usuarios/matheus.md', '- Perfil inteiramente fictício para teste\n');
    const threads = [
      { id: 'f1', titulo: 'Lançamento do site', detalhe: 'Organizar o lançamento do projeto fictício.', proximo_passo: 'Revisar o roteiro de lançamento', prioridade: 'alta', prazo: '2026-10-20', estado: 'aberto', criado: '2026-10-10', ligacoes: [{ id: 'f2', motivo: 'Precisa da identidade visual' }, { id: 'f3', motivo: 'Publicar o catálogo' }, 'Reels de lançamento'] },
      { id: 'f2', titulo: 'Identidade visual', detalhe: 'Cores e marca do exemplo sintético.', atualizado: '2026-10-12', ligacoes: [{ id: 'f3', motivo: 'Usar a marca no catálogo' }] },
      { id: 'f3', titulo: 'Catálogo de produtos', detalhe: 'Lista fictícia dos produtos.', ligacoes: ['Briefing comercial'] },
      { id: 'f4', titulo: 'Lançamento sem ligação', detalhe: 'Mesmo assunto, mas sem conexão explícita.' },
    ];
    write('fios/matheus.json', { fios: threads });
    write('fios/fernanda.json', { fios: [{ titulo: 'OTHER_PERSON_SENTINEL', ligacoes: ['SECRET_OTHER_PERSON'] }] });
    const before = hashes();
    port = await new Promise((resolve, reject) => { const socket = net.createServer(); socket.on('error', reject); socket.listen(0, '127.0.0.1', () => { const value = socket.address().port; socket.close(() => resolve(value)); }); });
    const nextBase = `http://127.0.0.1:${port}`;
    const log = fs.openSync(path.join(OUT, 'server.log'), 'w');
    server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '-H', '127.0.0.1', '-p', String(port)], { cwd: APP, detached: true, stdio: ['ignore', log, log], env: { PATH: process.env.PATH, HOME: os.tmpdir(), NODE_ENV: 'production', NEXT_TELEMETRY_DISABLED: '1', SECOND_BRAIN_DATA_ROOT: fixture, SECOND_BRAIN_TOKEN_SHA256: createHash('sha256').update(TOKEN).digest('hex') } });
    fs.closeSync(log);
    let ready = false;
    for (let i = 0; i < 100; i++) { if (server.exitCode !== null) throw new Error('Next exited early'); try { if ((await fetch(`${nextBase}/segundo-cerebro`)).ok) { ready = true; break; } } catch {} await sleep(100); }
    assert.ok(ready, 'server ready');
    assert.equal((await fetch(`${nextBase}/api/segundo-cerebro`)).status, 401);
    assert.equal((await fetch(`${nextBase}/api/segundo-cerebro?user=fernanda`, { headers: { Authorization: `Bearer ${TOKEN}` } })).status, 400);
    const payload = await fetch(`${nextBase}/api/segundo-cerebro`, { headers: { Authorization: `Bearer ${TOKEN}` } });
    const data = await payload.json();
    assert.equal(data.connections.nodes.length, 5); assert.equal(data.connections.edges.length, 5);
    assert.ok(!JSON.stringify(data).includes('OTHER_PERSON_SENTINEL'));
    assert.equal(payload.headers.get('cache-control'), 'private, no-store');
    pass('existing bearer, identity isolation and no-store unchanged');
    base = await startGateway(nextBase);
    browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, headless: true, args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    for (const [label, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }], ['small-mobile', { width: 320, height: 740 }]]) {
      const context = await browser.newContext({ viewport, isMobile: label !== 'desktop', hasTouch: label !== 'desktop' });
      const page = await context.newPage();
      page.on('pageerror', error => results.pageErrors.push(error.message));
      page.on('request', request => { if (!request.url().startsWith(base)) results.externalRequests.push(request.url()); });
      await page.goto(`${base}/segundo-cerebro`); await login(page);
      await page.locator('#conexoes').scrollIntoViewIfNeeded();
      const map = page.getByRole('group', { name: 'Mapa interativo de conexões explícitas', exact: true });
      await drawn(page, 5, 5);
      assert.equal(await at(page, 'fio:f4'), null);
      assert.equal(await page.locator('#passos').getByRole('heading', { name: 'Lançamento sem ligação' }).count(), 1);
      await map.scrollIntoViewIfNeeded();
      let box = await map.boundingBox();
      const launch = await at(page, 'fio:f1');
      if (label === 'desktop') await page.mouse.click(box.x + launch.x, box.y + launch.y); else await page.touchscreen.tap(box.x + launch.x, box.y + launch.y);
      const details = page.getByRole('complementary', { name: 'Detalhes do nó' });
      await details.getByText('Revisar o roteiro de lançamento', { exact: true }).waitFor();
      assert.ok((await details.innerText()).includes('registro f1'));
      pass(`${label}: only explicit graph; details and original thread list retained`);
      await shot(page, `mapa_${label}.png`);
      const jump = page.locator('#conexoes').getByRole('combobox', { name: 'Ir para' });
      await jump.focus();
      await jump.selectOption({ label: 'Referência: Reels de lançamento' });
      await details.getByText('Texto citado em uma ligação.', { exact: false }).waitFor();
      pass(`${label}: keyboard selection and textual-reference distinction`);
      await page.getByRole('button', { name: 'Ajustar mapa à tela', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('output[aria-label="Zoom"]')?.textContent === '100%');
      await sleep(400);
      await page.getByRole('button', { name: 'Aumentar zoom', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('output[aria-label="Zoom"]')?.textContent === '125%');
      await map.focus();
      const original = await at(page, 'fio:f1');
      await page.keyboard.press('ArrowRight');
      assert.notDeepEqual(await at(page, 'fio:f1'), original);
      await page.getByRole('button', { name: 'Ajustar mapa à tela', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('output[aria-label="Zoom"]')?.textContent === '100%');
      await sleep(400);
      await map.scrollIntoViewIfNeeded();
      box = await map.boundingBox();
      const beforePan = await at(page, 'fio:f1');
      await page.mouse.move(box.x + 10, box.y + box.height - 15); await page.mouse.down(); await page.mouse.move(box.x + 60, box.y + box.height - 40, { steps: 5 }); await page.mouse.up();
      await sleep(400);
      assert.ok(Math.hypot((await at(page, 'fio:f1')).x - beforePan.x, (await at(page, 'fio:f1')).y - beforePan.y) > 20);
      await page.getByRole('button', { name: 'Ajustar mapa à tela', exact: true }).click();
      pass(`${label}: zoom, keyboard pan, pointer pan and reset`);
      await page.getByLabel('Buscar no mapa', { exact: true }).fill('IDENTIDADE');
      await drawn(page, 3, 2);
      await page.getByLabel('Buscar no mapa', { exact: true }).fill('nao-existe');
      await page.getByRole('heading', { name: 'Nenhuma conexão encontrada', exact: true }).waitFor();
      assert.equal(await page.locator('[data-renderer]').count(), 0);
      await page.getByRole('button', { name: 'Limpar filtros', exact: true }).click();
      await page.locator('#conexoes').getByRole('combobox', { name: 'Mostrar' }).selectOption('texto');
      await drawn(page, 4, 2);
      await page.getByRole('button', { name: 'Lista', exact: true }).click();
      const list = page.getByRole('list', { name: 'Lista de conexões explícitas', exact: true });
      assert.equal(await list.locator(':scope > li').count(), 2);
      await list.getByRole('button', { name: 'Explorar no mapa' }).first().click();
      await details.getByRole('heading', { name: 'Lançamento do site', exact: true }).waitFor();
      await page.locator('#conexoes').getByRole('combobox', { name: 'Mostrar' }).selectOption('todos');
      await drawn(page, 5, 5);
      await page.getByRole('button', { name: 'Lista', exact: true }).click();
      assert.equal(await list.locator(':scope > li').count(), 5);
      pass(`${label}: search, no matches, type filter with neighbors and accessible alternative list`);
      const widths = await page.locator('body, main, #conexoes').evaluateAll(elements => elements.map(el => ({ client: el.clientWidth, scroll: el.scrollWidth })));
      assert.ok(widths.every(size => size.scroll <= size.client), JSON.stringify(widths));
      pass(`${label}: no horizontal overflow`);
      assert.deepEqual(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length })), { local: 0, session: 0 });
      assert.equal(await page.locator('input[type=password]').count(), 0, 'no key field in the page');
      await page.getByRole('link', { name: 'Sair', exact: true }).click();
      await page.waitForURL(`${base}/login?next=/segundo-cerebro`);
      await page.goto(`${base}/segundo-cerebro`);
      const entrar = page.getByRole('link', { name: 'Entrar', exact: true });
      await entrar.waitFor();
      assert.equal(await entrar.getAttribute('href'), '/login?next=/segundo-cerebro');
      assert.equal(await page.locator('[data-renderer], #conexoes canvas').count(), 0);
      pass(`${label}: logout goes through /logout; expired session shows only the login link; no stored credential`);
      await context.close();
    }
    {
      sessao = 'outra';
      const context = await browser.newContext({ viewport: { width: 1000, height: 800 } });
      const page = await context.newPage(); await page.goto(`${base}/segundo-cerebro`);
      await page.getByRole('link', { name: 'Sair', exact: true }).waitFor();
      assert.equal(await page.getByRole('link', { name: 'Sair', exact: true }).getAttribute('href'), '/logout');
      assert.equal(await page.locator('[data-renderer], #conexoes canvas').count(), 0);
      pass("another person's session sees no data, only the logout link");
      await context.close();
    }
    assert.equal(authFromBrowser, 0); pass('the browser never sent an Authorization header');
    assert.deepEqual(hashes(), before); pass('synthetic source files are byte-for-byte unchanged');
    assert.deepEqual(results.pageErrors, []); assert.deepEqual(results.externalRequests, []); pass('no uncaught page errors or external requests');
    // Refresh edge cases using only this disposable fixture, not personal sources.
    const context = await browser.newContext({ viewport: { width: 1000, height: 800 } });
    const page = await context.newPage(); await login(page);
    await drawn(page, 5, 5);
    threads[0].ligacoes.push({ id: 'f1', motivo: 'Self-link explícito' }, { id: 'f2', motivo: 'Segunda evidência explícita' }, '<img src=x onerror=alert(1)>');
    write('fios/matheus.json', { fios: threads });
    await page.getByRole('button', { name: 'Atualizar', exact: true }).click();
    await drawn(page, 6, 8);
    assert.equal(await page.locator('#conexoes img').count(), 0);
    pass('refresh preserves explicit self/duplicate links and safely escapes HTML labels');
    write('fios/matheus.json', { fios: [] });
    await page.getByRole('button', { name: 'Atualizar', exact: true }).click();
    await page.getByText('Nenhuma ligação registrada nos fios.', { exact: true }).waitFor();
    assert.equal(await page.locator('[data-renderer], #conexoes canvas').count(), 0);
    pass('refresh empty state does not retain stale graph');
    fs.unlinkSync(path.join(fixture, 'fios/matheus.json'));
    await page.getByRole('button', { name: 'Atualizar', exact: true }).click();
    await page.locator('#conexoes').getByText('Fonte indisponível — veja os avisos acima.', { exact: true }).waitFor();
    pass('missing source distinguished from empty data');
    await context.close(); results.status = 'passed';
  } catch (error) { results.status = 'failed'; results.error = error.stack; console.error(error); process.exitCode = 1; }
  finally {
    if (browser) await browser.close();
    if (gateway) await new Promise(resolve => gateway.close(resolve));
    if (server) { try { process.kill(-server.pid, 'SIGTERM'); } catch {} await Promise.race([new Promise(resolve => server.once('exit', resolve)), sleep(2500)]); try { process.kill(-server.pid, 'SIGKILL'); } catch {} }
    if (fixture) fs.rmSync(fixture, { recursive: true, force: true });
    if (port) { try { await fetch(`http://127.0.0.1:${port}/segundo-cerebro`, { signal: AbortSignal.timeout(1000) }); results.serverStopped = false; process.exitCode = 1; } catch { results.serverStopped = true; } }
    fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
    console.log('RESULT', results.status, 'serverStopped', results.serverStopped);
  }
})();
