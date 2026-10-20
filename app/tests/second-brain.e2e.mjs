/* Navegador (Playwright existente, nada instalado), depois do `npm run build`:
     PLAYWRIGHT_MODULE=/caminho/playwright PLAYWRIGHT_CHROMIUM_EXECUTABLE=/caminho/chrome \
     E2E_OUT=/pasta/resultados [E2E_REAIS=1] node tests/second-brain.e2e.mjs
   Fase 1 (sempre): dados sintéticos. Fase 2 (E2E_REAIS=1): as fontes reais autorizadas de /a0/usr, só leitura,
   para os prints; os arquivos lidos são conferidos por hash antes e depois.
   Harness local: Next em 127.0.0.1 numa porta livre escolhida aqui + um gateway falso que faz o papel da sessão do
   Agent Zero e põe o bearer só no salto para a API. Isto NÃO prova a autenticação de produção (plugin segundo_cerebro);
   prova a página, a API real com bearer e o isolamento de identidade. */
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import http from "node:http";
import { createHash, randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { buildBrainGraph } from "../lib/brain-graph.mjs";
import { DOCUMENTOS_PERMITIDOS, ROTINAS_PERMITIDAS, PROJETOS_PERMITIDOS, CONTEXTO_CHAT } from "../lib/second-brain.mjs";
import { criarFixture, SENTINELA, FORA_DA_LISTA } from "./fixture-brain.mjs";

// Opções também por argumento (--playwright=, --chromium=, --out=, --reais), além das variáveis de ambiente.
const ARG = Object.fromEntries(process.argv.slice(2).map((a) => { const [k, ...v] = a.replace(/^--/, "").split("="); return [k, v.length ? v.join("=") : "1"]; }));
const { chromium } = createRequire(import.meta.url)(ARG.playwright || process.env.PLAYWRIGHT_MODULE || "playwright");
const CHROMIUM = ARG.chromium || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;
const REAIS = ARG.reais === "1" || process.env.E2E_REAIS === "1";
const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = ARG.out || process.env.E2E_OUT || path.join(os.tmpdir(), "second-brain-e2e");
const PRINTS = path.join(OUT, "prints");
const LOGS = path.join(OUT, "logs");
fs.mkdirSync(PRINTS, { recursive: true });
fs.mkdirSync(LOGS, { recursive: true });
const results = { fases: {}, checks: [], screenshots: [], pageErrors: [], consoleErrors: [], externalRequests: [], processos: [] };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pass = (n) => { results.checks.push(n); console.log("PASS", n); };
const sha = (b) => createHash("sha256").update(b).digest("hex");
const TIPOS_ROTULOS = ["Fonte", "Projeto", "Contexto", "Documento", "Rotina", "Fato da ficha", "Fio", "Referência textual"];
const FUNCAO = { A: "retomar", B: "rotina", C: "prioridades" };

// Porta escolhida explicitamente: a primeira livre a partir de uma base fixa, em 127.0.0.1.
async function portaLivre(base) {
  for (let p = base; p < base + 200; p++) {
    const livre = await new Promise((resolve) => { const s = net.createServer(); s.once("error", () => resolve(false)); s.listen(p, "127.0.0.1", () => s.close(() => resolve(true))); });
    if (livre) return p;
  }
  throw new Error("sem porta livre");
}

async function subirNext(root, porta, token) {
  const log = fs.openSync(path.join(LOGS, `next-${porta}.log`), "w");
  const proc = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "-H", "127.0.0.1", "-p", String(porta)], {
    cwd: APP, detached: true, stdio: ["ignore", log, log],
    env: { PATH: process.env.PATH, HOME: os.tmpdir(), NODE_ENV: "production", NEXT_TELEMETRY_DISABLED: "1", SECOND_BRAIN_DATA_ROOT: root, SECOND_BRAIN_TOKEN_SHA256: sha(token) },
  });
  fs.closeSync(log);
  results.processos.push({ pid: proc.pid, porta });
  for (let i = 0; i < 150; i++) {
    if (proc.exitCode !== null) throw new Error("Next saiu cedo");
    try { if ((await fetch(`http://127.0.0.1:${porta}/segundo-cerebro`)).ok) return proc; } catch {}
    await sleep(100);
  }
  throw new Error("Next não subiu");
}

async function pararNext(proc, porta) {
  try { process.kill(-proc.pid, "SIGTERM"); } catch {}
  await Promise.race([new Promise((r) => proc.once("exit", r)), sleep(3000)]);
  try { process.kill(-proc.pid, "SIGKILL"); } catch {}
  try { await fetch(`http://127.0.0.1:${porta}/segundo-cerebro`, { signal: AbortSignal.timeout(1000) }); return false; } catch { return true; }
}

// Gateway falso (papel do plugin segundo_cerebro): sessão = variável; bearer só no salto para a API.
function subirGateway(nextBase, token, porta, estado) {
  return new Promise((resolve, reject) => {
    const g = http.createServer(async (req, res) => {
      if (req.headers.authorization) estado.authDoNavegador++;
      const url = new URL(req.url, "http://x");
      if (url.pathname === "/logout") { estado.sessao = "nenhuma"; res.writeHead(302, { Location: "/login?next=/segundo-cerebro" }); return res.end(); }
      if (url.pathname === "/login") { res.writeHead(200, { "Content-Type": "text/html" }); return res.end("<h1>login falso</h1>"); }
      // No ar, /favicon.ico é do Agent Zero (fora da lista do gateway); o login falso não deve gerar 404 dele.
      if (url.pathname === "/favicon.ico") { res.writeHead(204); return res.end(); }
      if (url.pathname === "/api/segundo-cerebro" && estado.sessao !== "matheus") { res.writeHead(estado.sessao === "outra" ? 403 : 401, { "Content-Type": "application/json" }); return res.end("{}"); }
      const api = url.pathname === "/api/segundo-cerebro";
      const r = await fetch(nextBase + url.pathname + (api ? "" : url.search), { headers: api ? { Authorization: `Bearer ${token}` } : {}, redirect: "manual" });
      res.writeHead(r.status, { "Content-Type": r.headers.get("content-type") || "application/octet-stream", ...(r.headers.get("location") ? { Location: r.headers.get("location") } : {}) });
      res.end(Buffer.from(await r.arrayBuffer()));
    });
    g.on("error", reject);
    g.listen(porta, "127.0.0.1", () => resolve(g));
  });
}

const hashesDir = (dir) => fs.readdirSync(dir, { recursive: true }).filter((f) => fs.statSync(path.join(dir, f)).isFile()).sort().map((f) => [f, sha(fs.readFileSync(path.join(dir, f)))]);
function arquivosReais() {
  const rel = ["memoria/decisoes/matheus.json", "memoria/usuarios/matheus.md", "fios/matheus.json", `chats/${CONTEXTO_CHAT}/contexto.md`,
    ...ROTINAS_PERMITIDAS.map((s) => `skills/${s}/SKILL.md`), ...PROJETOS_PERMITIDOS.flatMap((p) => [`projects/${p}/.a0proj/dono.txt`, `projects/${p}/.a0proj/project.json`]), ...DOCUMENTOS_PERMITIDOS.map((d) => d.partes.join("/"))];
  return rel.map((r) => { try { return [r, sha(fs.readFileSync(path.join("/a0/usr", r)))]; } catch (e) { return [r, e.code]; } });
}

async function contexto(browser, base, label, viewport) {
  const ctx = await browser.newContext({ viewport, isMobile: !label.includes("desktop"), hasTouch: !label.includes("desktop"), deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => results.pageErrors.push(`${label}: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    // 401/403 da API são provocados de propósito (sessão expirada, outra conta); qualquer outro erro conta.
    const esperado = /^Failed to load resource: .*status of 40[13]\b/.test(m.text()) && (m.location()?.url ?? "").endsWith("/api/segundo-cerebro");
    (esperado ? (results.consoleEsperados ??= []) : results.consoleErrors).push(`${label}: ${m.text().slice(0, 200)} @ ${(m.location()?.url ?? "").replace(/^https?:\/\/[^/]+/, "")}`);
  });
  page.on("request", (r) => { if (!r.url().startsWith(base)) results.externalRequests.push(r.url()); });
  return { ctx, page };
}
const desenhado = (page, nodes) => page.waitForFunction((n) => { const el = document.querySelector("#mapa [data-renderer]"); return el?.dataset.renderer === "pronto" && (n === null || el.dataset.nodes === String(n)); }, nodes, { timeout: 30000 });
const palco = (page) => page.locator("#mapa [data-renderer]");
const chip = (page, grupo, nome) => page.locator("#mapa fieldset").filter({ has: page.locator("legend", { hasText: new RegExp("^" + grupo + "$") }) }).locator("label", { hasText: nome }).locator("input");
async function semOverflow(page, label) {
  const larguras = await page.locator("body, main, section").evaluateAll((els) => els.map((el) => ({ id: el.id || el.tagName, client: el.clientWidth, scroll: el.scrollWidth })));
  const ruins = larguras.filter((w) => w.scroll > w.client + 1);
  assert.deepEqual(ruins, [], `${label}: overflow horizontal ${JSON.stringify(ruins)}`);
}
async function print(page, nome, alvo) {
  const dest = path.join(PRINTS, nome);
  const vp = page.viewportSize();
  // A página rola dentro de <main>: aumenta a altura da janela só durante a captura para caber tudo.
  const altura = await page.evaluate((sel) => (sel ? document.querySelector(sel).scrollHeight + 160 : document.querySelector("main").scrollHeight + (document.querySelector("nav")?.offsetHeight ?? 0) + 40), alvo ?? null);
  const limite = Math.min(Math.max(vp.height, altura), 16000);
  await page.setViewportSize({ width: vp.width, height: limite });
  await sleep(700);
  if (alvo) await page.locator(alvo).screenshot({ path: dest });
  else await page.screenshot({ path: dest });
  await page.setViewportSize(vp);
  await sleep(300);
  results.screenshots.push({ arquivo: dest, cortadoEm16000px: altura > 16000 });
}
async function rodarFluxo(page, nome) {
  const anterior = await page.locator('[aria-label="Resultado da consulta"]').getAttribute("data-carga", { timeout: 200 }).catch(() => null);
  await page.getByRole("button", { name: new RegExp("^" + nome) }).click();
  // Espera o resultado DESTE fluxo (sua função e uma carga nova), já verificado.
  await page.waitForFunction(([fn, ant]) => { const el = document.querySelector('[aria-label="Resultado da consulta"]'); return el?.dataset.funcao === fn && el.dataset.carga !== ant && el.dataset.verificacao === "verificado"; }, [FUNCAO[nome[0]], anterior], { timeout: 20000 });
  const res = page.getByRole("region", { name: "Resultado da consulta" });
  assert.equal(await res.locator('[data-etapa="execucao"]').getAttribute("data-estado"), "nao_executado");
  assert.equal(await res.locator('[data-etapa="verificacao"]').getAttribute("data-estado"), "verificado");
  return res;
}

async function fase1(browser) {
  const fixture = criarFixture();
  const token = randomBytes(24).toString("hex");
  const estado = { sessao: "nenhuma", authDoNavegador: 0 };
  const pNext = await portaLivre(39417);
  const next = await subirNext(fixture, pNext, token);
  const pGw = await portaLivre(pNext + 1);
  const gw = await subirGateway(`http://127.0.0.1:${pNext}`, token, pGw, estado);
  const base = `http://127.0.0.1:${pGw}`;
  const antes = hashesDir(fixture);
  const f = { portas: { next: pNext, gateway: pGw } };
  try {
    const api = `http://127.0.0.1:${pNext}/api/segundo-cerebro`;
    assert.equal((await fetch(api)).status, 401);
    assert.equal((await fetch(`${api}?user=fernanda`, { headers: { Authorization: `Bearer ${token}` } })).status, 400);
    assert.equal((await fetch(api, { headers: { Authorization: `Bearer ${token}`, "x-user": "fernanda" } })).status, 403);
    const r = await fetch(api, { headers: { Authorization: `Bearer ${token}` } });
    assert.equal(r.headers.get("cache-control"), "private, no-store");
    const dados = await r.json();
    const json = JSON.stringify(dados);
    assert.ok(!json.includes(SENTINELA) && !json.includes(FORA_DA_LISTA));
    const total = buildBrainGraph(dados).nodes.length;
    f.nos = total;
    pass("fase 1: API real com bearer, identidade fixa, no-store e sem dados de outra pessoa");

    for (const [label, viewport] of [["desktop", { width: 1440, height: 1000 }], ["mobile", { width: 390, height: 844 }], ["mobile-pequeno", { width: 320, height: 740 }]]) {
      const { ctx, page } = await contexto(browser, base, label, viewport);
      estado.sessao = "matheus";
      await page.goto(`${base}/segundo-cerebro`);
      await page.getByRole("heading", { name: "Mapa do Segundo Cérebro" }).waitFor();
      await page.locator("#mapa").scrollIntoViewIfNeeded();
      await desenhado(page, total);
      pass(`${label}: mapa com todos os ${total} nós (registros, fontes e referências)`);

      await chip(page, "Relação", "Veio da fonte").uncheck();
      await page.waitForFunction(() => Number(document.querySelector("#mapa [data-renderer]")?.dataset.isolados) > 0);
      assert.equal(await palco(page).getAttribute("data-nodes"), String(total), "sem as arestas de proveniência, nenhum nó some");
      assert.ok(Number(await palco(page).getAttribute("data-isolados")) >= 9, "isolados continuam no mapa");
      await chip(page, "Relação", "Veio da fonte").check();
      pass(`${label}: filtro de relação mantém nós isolados`);

      for (const t of TIPOS_ROTULOS) await chip(page, "Tipo", t).uncheck();
      await desenhado(page, 5);
      for (const t of TIPOS_ROTULOS) await chip(page, "Tipo", t).check();
      await desenhado(page, total);
      await chip(page, "Fonte", "Fios").uncheck();
      await page.waitForFunction((n) => { const el = document.querySelector("#mapa [data-renderer]"); return el?.dataset.renderer === "pronto" && Number(el.dataset.nodes) < n; }, total);
      await chip(page, "Fonte", "Fios").check();
      await desenhado(page, total);
      pass(`${label}: filtros por tipo e por fonte`);

      const busca = page.getByLabel("Buscar no mapa");
      await busca.fill("catalogo");
      await desenhado(page, 2);
      assert.equal(await page.getByLabel("Posição na busca").textContent(), "1/2");
      const camAntes = await palco(page).evaluate((el) => el.__mapaCamera());
      await busca.press("Enter");
      const det = page.getByRole("complementary", { name: "Detalhes do nó" });
      await det.getByText("Fonte", { exact: true }).waitFor();
      await sleep(500);
      const camDepois = await palco(page).evaluate((el) => el.__mapaCamera());
      assert.notDeepEqual(camDepois, camAntes, "a câmera foca o nó buscado");
      await page.getByRole("button", { name: "Próximo resultado" }).click();
      assert.equal(await page.getByLabel("Posição na busca").textContent(), "2/2");
      pass(`${label}: busca navegável (resultado 1/2, Enter e próximo focam o nó)`);

      await busca.fill("");
      await desenhado(page, total);
      await page.locator("#mapa").getByRole("combobox", { name: "Ir para" }).selectOption({ label: "Fio: Catálogo sintético" });
      await det.getByRole("heading", { name: "Catálogo sintético" }).waitFor();
      assert.match(await det.innerText(), /Evidência: fonte fios · registro b2 · campo ligacoes/);
      await det.getByRole("button", { name: "Abrir o registro na página" }).click();
      await page.waitForFunction(() => document.getElementById("reg-fio_b2")?.getAttribute("data-destacado") === "sim");
      pass(`${label}: detalhes com evidência e navegação até o registro`);

      await page.locator("#mapa").getByRole("button", { name: "Lista", exact: true }).click();
      assert.equal(await page.getByRole("list", { name: "Lista de registros do mapa" }).locator(":scope > li").count(), total);
      await page.locator("#mapa").getByRole("button", { name: "Mapa", exact: true }).click();
      await desenhado(page, total);
      pass(`${label}: lista acessível com todos os nós`);

      await page.locator("#consulta").scrollIntoViewIfNeeded();
      let res = await rodarFluxo(page, "A · Retomar contexto");
      assert.ok(await res.locator('li[data-ref^="decisao:"]').count() > 0, "decisões do tema entram na retomada");
      res = await rodarFluxo(page, "B · Consultar rotina");
      assert.match(await res.innerText(), /Ler o arquivo sintético/);
      assert.match(await res.innerText(), /Antes de enviar qualquer coisa a terceiros/);
      res = await rodarFluxo(page, "C · Prioridades e pauta");
      assert.match(await res.getByRole("list", { name: "Bloqueios" }).innerText(), /estratégia/);
      pass(`${label}: fluxos A, B e C com roteiro, execução não feita e verificação real`);

      assert.match(await page.locator('#fontes tr[data-fonte="reunioes"]').innerText(), /sem fonte canônica/);
      assert.match(await page.locator("#reunioes").innerText(), /Lacuna/);
      await semOverflow(page, label);
      assert.deepEqual(await page.evaluate(() => ({ l: localStorage.length, s: sessionStorage.length })), { l: 0, s: 0 });
      assert.equal(await page.locator("input[type=password]").count(), 0);
      pass(`${label}: lacunas visíveis, sem overflow, nada guardado no navegador`);

      await page.getByRole("link", { name: "Sair", exact: true }).click();
      await page.waitForURL(`${base}/login?next=/segundo-cerebro`);
      await page.goto(`${base}/segundo-cerebro`);
      assert.equal(await page.getByRole("link", { name: "Entrar", exact: true }).getAttribute("href"), "/login?next=/segundo-cerebro");
      assert.equal(await page.locator("[data-renderer]").count(), 0);
      pass(`${label}: sair passa por /logout; sessão expirada só mostra Entrar`);
      await ctx.close();
    }
    {
      estado.sessao = "outra";
      const { ctx, page } = await contexto(browser, base, "outra", { width: 1000, height: 800 });
      await page.goto(`${base}/segundo-cerebro`);
      await page.getByRole("link", { name: "Sair", exact: true }).waitFor();
      assert.equal(await page.locator("[data-renderer], #mapa").count(), 0);
      pass("sessão de outra pessoa não vê dados");
      await ctx.close();
    }
    {
      estado.sessao = "matheus";
      const { ctx, page } = await contexto(browser, base, "desktop-atualizar", { width: 1280, height: 900 });
      await page.goto(`${base}/segundo-cerebro`);
      await desenhado(page, total);
      const fios = JSON.parse(fs.readFileSync(path.join(fixture, "fios/matheus.json"), "utf8"));
      fios.fios.push({ id: "z9", titulo: "<img src=x onerror=alert(1)>", estado: "aberto", ligacoes: ["a1"], criado: 1790000700, atualizado: 1790000700 });
      fs.writeFileSync(path.join(fixture, "fios/matheus.json"), JSON.stringify(fios));
      await page.getByRole("button", { name: "Atualizar", exact: true }).click();
      await desenhado(page, total + 1);
      assert.equal(await page.locator("main img").count(), 0, "HTML vira texto");
      fs.unlinkSync(path.join(fixture, "fios/matheus.json"));
      await page.getByRole("button", { name: "Atualizar", exact: true }).click();
      await page.locator("#passos").getByText(/Fonte indisponível \(ausente\)/).waitFor();
      pass("atualizar relê a fonte: novo registro aparece, HTML escapado, fonte ausente ≠ vazia");
      await ctx.close();
    }
    assert.equal(estado.authDoNavegador, 0);
    pass("o navegador nunca mandou Authorization");
    const semFios = (l) => l.filter(([n]) => n !== "fios/matheus.json");
    assert.deepEqual(semFios(hashesDir(fixture)), semFios(antes));
    pass("arquivos sintéticos intactos (fora o que o próprio teste mudou)");
  } finally {
    await new Promise((r) => gw.close(r));
    f.nextParado = await pararNext(next, pNext);
    fs.rmSync(fixture, { recursive: true, force: true });
    results.fases.sintetica = f;
  }
}

async function fase2(browser) {
  const token = randomBytes(24).toString("hex");
  const estado = { sessao: "matheus", authDoNavegador: 0 };
  const antes = arquivosReais();
  const pNext = await portaLivre(39517);
  const next = await subirNext("/a0/usr", pNext, token);
  const pGw = await portaLivre(pNext + 1);
  const gw = await subirGateway(`http://127.0.0.1:${pNext}`, token, pGw, estado);
  const base = `http://127.0.0.1:${pGw}`;
  const f = { portas: { next: pNext, gateway: pGw } };
  try {
    const dados = await (await fetch(`http://127.0.0.1:${pNext}/api/segundo-cerebro`, { headers: { Authorization: `Bearer ${token}` } })).json();
    const json = JSON.stringify(dados);
    const grafo = buildBrainGraph(dados);
    f.fontes = dados.sources.map((s) => `${s.id}:${s.codigo}:${s.registros}`);
    f.nos = grafo.nodes.length;
    f.arestas = grafo.edges.length;
    const semHandles = json.replace(/(^|[\s"(])@[\w.]+/g, "$1");
    assert.ok(!/[\w.+-]+@[\w-]+\.(?:com|br|net|org|io)\b/i.test(semHandles), "nenhum e-mail na projeção (handles @ ficam)");
    assert.ok(!/\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/.test(json) && !/\(\d{2}\)\s?9\d{4}-?\d{4}/.test(json), "nenhum CPF/telefone na projeção");
    pass("fase 2: projeção real sanitizada (sem e-mail, CPF ou telefone)");
    for (const [label, viewport] of [["desktop", { width: 1440, height: 1000 }], ["mobile", { width: 390, height: 844 }]]) {
      const { ctx, page } = await contexto(browser, base, `real-${label}`, viewport);
      await page.goto(`${base}/segundo-cerebro`);
      await page.getByRole("heading", { name: "Mapa do Segundo Cérebro" }).waitFor();
      await page.locator("#mapa").scrollIntoViewIfNeeded();
      await desenhado(page, f.nos);
      await sleep(800);
      await print(page, `${label}_pagina_completa.png`);
      await print(page, `${label}_mapa.png`, "#mapa");
      const det = page.getByRole("complementary", { name: "Detalhes do nó" });
      const alvo = dados.decisions.find((d) => d.substitui) ?? dados.decisions[0];
      await page.locator("#mapa").getByRole("combobox", { name: "Ir para" }).selectOption({ value: `decisao:${alvo.id}` });
      await det.getByText("Fonte", { exact: true }).waitFor();
      await sleep(800);
      await print(page, `${label}_mapa_detalhes.png`, "#mapa");
      await page.getByLabel("Buscar no mapa").fill(dados.decisions[0].tema?.split(".")[0] ?? "a");
      await sleep(300);
      await desenhado(page, null);
      await page.getByLabel("Buscar no mapa").press("Enter");
      await sleep(800);
      await print(page, `${label}_mapa_busca.png`, "#mapa");
      await page.getByLabel("Buscar no mapa").fill("");
      await page.locator("#consulta").scrollIntoViewIfNeeded();
      for (const [fluxo, nome] of [["A · Retomar contexto", "consulta_A_retomar"], ["B · Consultar rotina", "consulta_B_rotina"], ["C · Prioridades e pauta", "consulta_C_prioridades"]]) {
        await rodarFluxo(page, fluxo);
        await print(page, `${label}_${nome}.png`, "#consulta");
      }
      await print(page, `${label}_fontes.png`, "#fontes");
      if (label === "desktop") { await print(page, "desktop_onboarding.png", "#onboarding"); await print(page, "desktop_rotinas.png", "#rotinas"); await print(page, "desktop_visao_geral.png", "#visao"); }
      await semOverflow(page, `real-${label}`);
      pass(`real ${label}: mapa (${f.nos} nós), detalhes, busca, 3 fluxos verificados, fontes; prints salvos`);
      await ctx.close();
    }
    assert.equal(estado.authDoNavegador, 0);
  } finally {
    await new Promise((r) => gw.close(r));
    f.nextParado = await pararNext(next, pNext);
    f.fontesReaisIntactas = JSON.stringify(arquivosReais()) === JSON.stringify(antes);
    f.arquivosConferidos = antes.length;
    results.fases.real = f;
  }
  assert.ok(f.fontesReaisIntactas, "fontes reais sem nenhuma mudança");
  pass("fontes reais intactas (hash antes = depois)");
}

let browser;
try {
  browser = await chromium.launch({ executablePath: CHROMIUM, headless: true, args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  await fase1(browser);
  if (REAIS) await fase2(browser);
  assert.deepEqual(results.pageErrors, []);
  assert.deepEqual(results.consoleErrors, []);
  assert.deepEqual(results.externalRequests, []);
  pass("sem erro de página, erro de console nem requisição externa");
  results.status = "passed";
} catch (e) {
  results.status = "failed";
  results.error = String(e.stack || e).split("\n").slice(0, 8).join("\n");
  console.error(e);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(LOGS, "e2e_results.json"), JSON.stringify(results, null, 2));
  console.log("RESULT", results.status, "checks", results.checks.length);
}
