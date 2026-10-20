// node --test tests/second-brain.test.mjs — só dados fictícios numa Pasta temporária.
import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, symlinkSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handleSecondBrainRequest, redact, checkBearer } from "../lib/second-brain.mjs";
import { criarFixture, naPasta, PASTA, SENTINELA, FORA_DA_LISTA } from "./fixture-brain.mjs";

const TOKEN = "fixture-token-not-real-123";
const DIGEST = createHash("sha256").update(TOKEN).digest("hex");
const NOW = new Date("2026-10-20T12:00:00Z");
const HERE = path.dirname(fileURLToPath(import.meta.url));

function hashes(dir) {
  const out = {};
  for (const e of readdirSync(dir, { recursive: true })) {
    const p = path.join(dir, e);
    if (statSync(p).isFile()) out[e] = createHash("sha256").update(readFileSync(p)).digest("hex");
  }
  return out;
}
const req = (url = "http://127.0.0.1/api/segundo-cerebro", headers = {}, method = "GET") => new Request(url, { method, headers });
const auth = { Authorization: `Bearer ${TOKEN}` };
const envFor = (root) => ({ SECOND_BRAIN_TOKEN_SHA256: DIGEST, SECOND_BRAIN_DATA_ROOT: root });
const comFixture = async (fn) => { const root = criarFixture(); try { await fn(root); } finally { rmSync(root, { recursive: true, force: true }); } };

test("acesso válido devolve só a Pasta do Matheus, com cabeçalhos sem cache e sem gravar nada", () => comFixture(async (root) => {
  const antes = hashes(root);
  const r = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
  assert.equal(r.status, 200);
  assert.equal(r.headers["Cache-Control"], "private, no-store");
  assert.equal(r.headers.Vary, "Authorization");
  const b = r.body;
  assert.equal(b.owner, "matheus");
  assert.equal(b.fetchedAt, NOW.toISOString());
  assert.deepEqual(Object.keys(b).sort(), ["areas", "conflicts", "connections", "contexts", "coverage", "daily", "decisions", "diagnostics", "documents", "fetchedAt", "gaps", "index", "links", "meetings", "owner", "pasta", "profile", "projects", "rules", "sources", "subjects", "threads", "warnings"]);
  assert.deepEqual(b.warnings, []);
  assert.equal(b.pasta.migrada, true);
  assert.deepEqual([b.decisions.length, b.threads.length, b.subjects.length, b.contexts.length, b.meetings.length, b.daily.length, b.documents.length, b.projects.length], [5, 4, 2, 6, 1, 2, 1, 1]);
  assert.deepEqual(b.profile.map((p) => p.texto), ["Mora numa cidade fictícia", "Prefere respostas em português"]);
  assert.ok(b.sources.every((s) => s.estado === "ok" && s.arquivoAtualizadoEm), JSON.stringify(b.sources.map((s) => [s.id, s.estado])));
  const json = JSON.stringify(b);
  assert.ok(!json.includes(SENTINELA), "nada do Arquivo-morto nem de subpasta de projeto");
  assert.ok(!json.includes(FORA_DA_LISTA), "nada dos registros antigos (memoria/, fios/, chats/, skills/, projects/)");
  assert.ok(!json.includes(root), "sem caminho cru");
  assert.deepEqual(hashes(root), antes, "nenhuma escrita");
}));

test("segredos reconhecíveis são removidos e HTML fica como texto", () => comFixture(async (root) => {
  naPasta(root, "Decisoes/0006-x.md", '---\nid: 6\ntema: "t.x"\nvalor: "curto <script>alert(1)</script> senha: hunter2abc e Bearer abcdefghijklmnop"\nestado: "ativa"\n---\n# x\n');
  const { body } = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
  const v = body.decisions.find((d) => d.id === "6").valor;
  assert.ok(!v.includes("hunter2abc") && !v.includes("abcdefghijklmnop"), v);
  assert.ok(v.includes("<script>alert(1)</script>"), "texto preservado; quem escapa é o React");
  assert.equal(redact("api_key=AKIAABCDEFGHIJKLMNOP"), "api_key=[removido]");
  assert.ok(!redact("use sk-abcdefghijklmnopqrstu").includes("sk-abc"));
}));

test("sem chave configurada => 503; sem/errada => 401; método diferente de GET => 405", async () => {
  assert.equal((await handleSecondBrainRequest(req(undefined, auth), {}, NOW)).status, 503);
  assert.equal((await handleSecondBrainRequest(req(undefined, auth), { SECOND_BRAIN_TOKEN_SHA256: "abc" }, NOW)).status, 503);
  assert.equal((await handleSecondBrainRequest(req(undefined, auth), { SECOND_BRAIN_TOKEN_SHA256: DIGEST, SECOND_BRAIN_DATA_ROOT: "relativo/x" }, NOW)).status, 503);
  const env = envFor("/nao-existe-fixture");
  assert.equal((await handleSecondBrainRequest(req(), env, NOW)).status, 401);
  assert.equal((await handleSecondBrainRequest(req(undefined, { Authorization: "Bearer errado" }), env, NOW)).status, 401);
  assert.equal((await handleSecondBrainRequest(req(undefined, { Authorization: TOKEN }), env, NOW)).status, 401);
  assert.equal(checkBearer(`Bearer ${TOKEN}`, DIGEST), true);
  assert.equal((await handleSecondBrainRequest(req(undefined, auth, "POST"), env, NOW)).status, 405);
});

test("query string (inclusive caminho) e cabeçalhos de identidade são recusados, mesmo autenticado", () => comFixture(async (root) => {
  const env = envFor(root);
  for (const q of ["?usuario=fernanda", "?tenant=fernanda", "?x", "?pasta=Arquivo-morto", "?arquivo=../../etc/passwd", "?"]) {
    const r = await handleSecondBrainRequest(req(`http://127.0.0.1/api/segundo-cerebro${q}`, auth), env, NOW);
    assert.equal(r.status, q === "?" ? 200 : 400, q);
  }
  for (const h of ["x-user", "x-login", "x-tenant"]) {
    const r = await handleSecondBrainRequest(req(undefined, { ...auth, [h]: "fernanda" }), env, NOW);
    assert.equal(r.status, 403, h);
  }
}));

test("Pasta ausente: toda fonte indisponível com aviso próprio (nunca lista vazia fingindo sucesso)", async () => {
  const { status, body } = await handleSecondBrainRequest(req(undefined, auth), envFor("/nao-existe-fixture"), NOW);
  assert.equal(status, 200);
  assert.ok(body.sources.every((s) => s.estado === "indisponivel" && s.codigo === "ausente"));
  assert.deepEqual(body.warnings.map((w) => w.fonte), ["pasta", "regras", "contexto", "perfil", "decisoes", "pendencias", "assuntos", "reunioes", "notas", "documentos", "projetos"]);
  assert.equal(body.pasta.migrada, false);
  assert.ok(body.gaps.some((g) => g.id === "pasta-nao-migrada"));
});

test("link simbólico (na raiz, na Pasta, numa subpasta ou num item) e arquivo acima de 1 MB são recusados", () => comFixture(async (root) => {
  const pasta = path.join(root, PASTA);
  // item que é link para o Arquivo-morto
  symlinkSync(path.join(pasta, "Arquivo-morto/Decisoes", readdirSync(path.join(pasta, "Arquivo-morto/Decisoes"))[0]), path.join(pasta, "Decisoes/0010-link.md"));
  // subpasta inteira trocada por link
  rmSync(path.join(pasta, "Reunioes"), { recursive: true });
  mkdirSync(path.join(root, "outro"));
  writeFileSync(path.join(root, "outro/2026-01-01-x.md"), `# ${SENTINELA}\n`);
  symlinkSync(path.join(root, "outro"), path.join(pasta, "Reunioes"));
  writeFileSync(path.join(pasta, "Documentos/grande.md"), "# g\n" + "a".repeat(1024 * 1024 + 10));
  const { body } = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
  const f = (id) => body.sources.find((s) => s.id === id);
  assert.deepEqual([f("decisoes").estado, f("decisoes").codigo], ["indisponivel", "ilegivel"], "coleção com item recusado não está completa");
  assert.deepEqual(f("decisoes").arquivos, [{ chave: "0010-link.md", codigo: "link" }]);
  assert.equal(body.decisions.length, 5, "os legíveis aparecem");
  assert.deepEqual([f("reunioes").estado, f("reunioes").codigo], ["indisponivel", "link"]);
  assert.deepEqual([f("documentos").estado, f("documentos").codigo], ["ok", "parcial"]);
  assert.ok(f("documentos").arquivos.some((a) => a.chave === "grande.md" && a.codigo === "grande"));
  assert.ok(!JSON.stringify(body).includes(SENTINELA));
  const alias = path.join(root, "alias");
  symlinkSync(root, alias);
  const viaLink = await handleSecondBrainRequest(req(undefined, auth), envFor(alias), NOW);
  assert.ok(viaLink.body.sources.every((s) => s.codigo === "link"), "raiz por link simbólico é recusada");
}));

test("a interface não usa HTML cru nem guarda a chave; o adaptador só varre num lugar e não grava", () => {
  const page = readFileSync(path.join(HERE, "../app/segundo-cerebro/page.tsx"), "utf8");
  assert.ok(!/dangerouslySetInnerHTML|innerHTML|localStorage|sessionStorage|document\.cookie/.test(page));
  assert.ok(!/\?token=|searchParams/.test(page));
  assert.ok(!/https?:\/\//.test(page), "sem recurso externo");
  const adapter = readFileSync(path.join(HERE, "../lib/second-brain.mjs"), "utf8");
  assert.ok(!/writeFile|appendFile|\bunlink|\brm\(|mkdir|rename\(|glob|recursive/.test(adapter), "adaptador só lê");
  assert.equal((adapter.match(/readdir\(/g) ?? []).length, 1, "uma única varredura (listarPasta), sem recursão");
  assert.ok(!/CONTEXTO_CHAT|ROTINAS_PERMITIDAS|PROJETOS_PERMITIDOS|DOCUMENTOS_PERMITIDOS|"memoria"|"fios"/.test(adapter), "as fontes antigas saíram");
});
