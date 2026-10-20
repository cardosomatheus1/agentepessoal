// node --test tests/second-brain.test.mjs — só dados fictícios em diretório temporário.
import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, readdirSync, statSync, symlinkSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handleSecondBrainRequest, redact, checkBearer, FICHA_MARCA } from "../lib/second-brain.mjs";
import { escreverExtras } from "./fixture-brain.mjs";

const TOKEN = "fixture-token-not-real-123";
const DIGEST = createHash("sha256").update(TOKEN).digest("hex");
const SENTINELA = "FERNANDA_SENTINELA_9f3a";
const NOW = new Date("2026-10-17T12:00:00Z");
const HERE = path.dirname(fileURLToPath(import.meta.url));

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "sc-"));
  mkdirSync(path.join(root, "memoria/decisoes"), { recursive: true });
  mkdirSync(path.join(root, "memoria/usuarios"), { recursive: true });
  mkdirSync(path.join(root, "fios"), { recursive: true });
  writeFileSync(
    path.join(root, "memoria/decisoes/matheus.json"),
    JSON.stringify({
      diario: [`registro interno ${SENTINELA}`],
      decisoes: [
        { id: "d1", tema: "Tom", tipo: "preferencia", valor: "curto <script>alert(1)</script>", citacao: "fala curto", origem: "chat", em: "2026-10-01T10:00:00Z", estado: "ativa", valido_ate: null, interno: SENTINELA },
        { id: "d2", tema: "Campanha", tipo: "regra", valor: "pausar", citacao: "pausa", origem: "chat", em: "2026-09-01", estado: "ativa", valido_ate: "2026-10-01" },
        { id: "d3", tema: "Chave", tipo: "regra", valor: "senha: hunter2abc e Bearer abcdefghijklmnop", estado: "revogada" },
      ],
    }),
  );
  // Formato do helper ficha.py: MARCA no topo, uma entrada por linha "- " (linha solta e item recuado não contam).
  writeFileSync(path.join(root, "memoria/usuarios/matheus.md"), `# Sobre matheus\n> ${FICHA_MARCA}\nTexto solto ignorado\n  - recuado ignorado\n- Mora em SP\n- Prefere português\n`);
  writeFileSync(
    path.join(root, "fios/matheus.json"),
    JSON.stringify({
      cache: SENTINELA,
      fios: [
        { id: "f1", titulo: "Site", detalhe: "refazer", fontes: ["conversa 10/10"], dono: "matheus", prazo: "2026-10-20", prioridade: "alta", proximo_passo: "mandar briefing", ligacoes: [{ id: "f2", motivo: "depende" }, "Texto livre registrado"], estado: "aberto", criado: "2026-10-10", atualizado: "2026-10-15" },
        { id: "f2", titulo: "Logo", detalhe: "Site também", prioridade: "baixa", estado: "aberto", criado: "2026-10-11", atualizado: "2026-10-12" },
        { id: "f3", titulo: "Site e Logo sem ligação", estado: "aberto" },
      ],
    }),
  );
  // Outra pessoa no mesmo diretório: nunca pode aparecer.
  writeFileSync(path.join(root, "memoria/decisoes/fernanda.json"), JSON.stringify({ decisoes: [{ id: "x", tema: SENTINELA }] }));
  writeFileSync(path.join(root, "memoria/usuarios/fernanda.md"), `- ${SENTINELA}\n`);
  writeFileSync(path.join(root, "fios/fernanda.json"), JSON.stringify({ fios: [{ id: "x", titulo: SENTINELA }] }));
  escreverExtras(root);
  return root;
}

function hashes(dir) {
  const out = {};
  for (const e of readdirSync(dir, { recursive: true })) {
    const p = path.join(dir, e);
    if (statSync(p).isFile()) out[e] = createHash("sha256").update(readFileSync(p)).digest("hex");
  }
  return out;
}

function req(url = "http://127.0.0.1/api/segundo-cerebro", headers = {}, method = "GET") {
  return new Request(url, { method, headers });
}
const auth = { Authorization: `Bearer ${TOKEN}` };
const envFor = (root) => ({ SECOND_BRAIN_TOKEN_SHA256: DIGEST, SECOND_BRAIN_DATA_ROOT: root });

test("acesso válido devolve só Matheus, campos permitidos e cabeçalhos sem cache", async () => {
  const root = fixture();
  try {
    const antes = hashes(root);
    const r = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
    assert.equal(r.status, 200);
    assert.equal(r.headers["Cache-Control"], "private, no-store");
    assert.equal(r.headers.Vary, "Authorization");
    const b = r.body;
    assert.equal(b.owner, "matheus");
    assert.equal(b.fetchedAt, NOW.toISOString());
    assert.deepEqual(Object.keys(b).sort(), ["conflicts", "connections", "contexts", "coverage", "daily", "decisions", "diagnostics", "documents", "fetchedAt", "gaps", "meetings", "owner", "profile", "projects", "proposals", "routines", "sources", "threads", "warnings"]);
    assert.equal(b.warnings.length, 0);
    assert.equal(b.decisions.length, 3);
    assert.equal(b.threads.length, 3);
    assert.deepEqual(b.profile.map((p) => p.texto), ["Mora em SP", "Prefere português"]);
    assert.equal(b.profile[0].proveniencia.linha, 5);
    assert.equal(b.profile[0].numero, 1, "número da entrada, como a ferramenta ficha usa");
    assert.ok(b.profile[0].proveniencia.arquivoAtualizadoEm);
    const json = JSON.stringify(b);
    assert.ok(!json.includes(SENTINELA), "nada de Fernanda, diário ou cache");
    assert.ok(!json.includes(root), "sem caminho cru");
    assert.equal(b.decisions[0].proveniencia.fonte, "decisoes");
    assert.equal(b.decisions[0].proveniencia.em, "2026-10-01T10:00:00Z");
    assert.ok(b.sources.filter((s) => s.estado !== "sem_contrato").every((s) => s.estado === "ok" && s.arquivoAtualizadoEm));
    assert.deepEqual(b.sources.filter((s) => s.estado === "sem_contrato").map((s) => s.id), ["reunioes", "daily"]);
    assert.deepEqual(hashes(root), antes, "nenhuma escrita");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("validade vencida vira expirada; revogada não é vigente", async () => {
  const root = fixture();
  try {
    const { body } = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
    const [d1, d2, d3] = body.decisions;
    assert.equal(d1.vigente, true);
    assert.equal(d2.estadoEfetivo, "expirada");
    assert.equal(d2.vigente, false);
    assert.equal(d3.vigente, false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("grafo só com ligações explícitas; texto livre vira nó textual separado", async () => {
  const root = fixture();
  try {
    const { body } = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
    const { nodes, edges } = body.connections;
    assert.equal(edges.length, 2);
    assert.deepEqual(edges.map((e) => [e.de, e.para]), [["fio:f1", "fio:f2"], ["fio:f1", "texto:Texto livre registrado"]]);
    assert.equal(edges[0].rotulo, "depende");
    assert.equal(edges[0].evidencia.fioId, "f1");
    assert.equal(nodes.find((n) => n.id === "texto:Texto livre registrado").tipo, "texto");
    assert.ok(!nodes.some((n) => n.id === "fio:f3"), "f3 cita Site/Logo no título mas não tem ligação: nada inferido");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("segredos reconhecíveis são removidos e HTML fica como texto", async () => {
  const root = fixture();
  try {
    const { body } = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
    const v = body.decisions[2].valor;
    assert.ok(!v.includes("hunter2abc") && !v.includes("abcdefghijklmnop"), v);
    assert.equal(body.decisions[0].valor, "curto <script>alert(1)</script>", "texto preservado; quem escapa é o React");
    assert.equal(redact("api_key=AKIAABCDEFGHIJKLMNOP"), "api_key=[removido]");
    assert.ok(!redact("use sk-abcdefghijklmnopqrstu").includes("sk-abc"));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("sem chave configurada => 503; sem/errada => 401", async () => {
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

test("query string e cabeçalhos de identidade são recusados, mesmo autenticado", async () => {
  const root = fixture();
  try {
    const env = envFor(root);
    for (const q of ["?usuario=fernanda", "?tenant=fernanda", "?x", "?"]) {
      const r = await handleSecondBrainRequest(req(`http://127.0.0.1/api/segundo-cerebro${q}`, auth), env, NOW);
      assert.equal(r.status, q === "?" ? 200 : 400, q);
    }
    for (const h of ["x-user", "x-login", "x-tenant"]) {
      const r = await handleSecondBrainRequest(req(undefined, { ...auth, [h]: "fernanda" }), env, NOW);
      assert.equal(r.status, 403, h);
      assert.ok(!JSON.stringify(r.body).includes(SENTINELA));
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("arquivo ausente e corrompido viram fonte indisponível com aviso separado", async () => {
  const root = fixture();
  try {
    rmSync(path.join(root, "memoria/usuarios/matheus.md"));
    writeFileSync(path.join(root, "fios/matheus.json"), "{ quebrado");
    writeFileSync(path.join(root, "memoria/decisoes/matheus.json"), JSON.stringify({ outra: [] }));
    const { status, body } = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
    assert.equal(status, 200);
    assert.deepEqual(body.warnings.map((w) => [w.fonte, w.codigo]), [["decisoes", "invalida"], ["perfil", "ausente"], ["fios", "invalida"]]);
    assert.deepEqual(body.sources.filter((s) => s.estado === "indisponivel").map((s) => s.id), ["decisoes", "perfil", "fios"]);
    const json = JSON.stringify(body);
    assert.ok(!json.includes(root) && !/SyntaxError|ENOENT|Unexpected/.test(json), "sem caminho nem exceção crua");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("link simbólico e arquivo acima de 1 MB são recusados", async () => {
  const root = fixture();
  try {
    const alvo = path.join(root, "memoria/decisoes/fernanda.json");
    rmSync(path.join(root, "memoria/decisoes/matheus.json"));
    symlinkSync(alvo, path.join(root, "memoria/decisoes/matheus.json"));
    rmSync(path.join(root, "fios"), { recursive: true });
    mkdirSync(path.join(root, "outro"));
    writeFileSync(path.join(root, "outro/matheus.json"), JSON.stringify({ fios: [{ id: "x", titulo: SENTINELA }] }));
    symlinkSync(path.join(root, "outro"), path.join(root, "fios"));
    writeFileSync(path.join(root, "memoria/usuarios/matheus.md"), "- " + "a".repeat(1024 * 1024 + 10));
    const { body } = await handleSecondBrainRequest(req(undefined, auth), envFor(root), NOW);
    assert.deepEqual(body.warnings.map((w) => [w.fonte, w.codigo]), [["decisoes", "link"], ["perfil", "grande"], ["fios", "link"]]);
    assert.ok(!JSON.stringify(body).includes(SENTINELA));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("a interface não usa HTML cru nem guarda a chave", () => {
  const page = readFileSync(path.join(HERE, "../app/segundo-cerebro/page.tsx"), "utf8");
  assert.ok(!/dangerouslySetInnerHTML|innerHTML|localStorage|sessionStorage|document\.cookie/.test(page));
  assert.ok(!/\?token=|searchParams/.test(page));
  assert.ok(!/https?:\/\//.test(page), "sem recurso externo");
  const adapter = readFileSync(path.join(HERE, "../lib/second-brain.mjs"), "utf8");
  assert.ok(!/writeFile|appendFile|\bunlink|readdir|glob/.test(adapter), "adaptador só lê arquivos fixos");
});
