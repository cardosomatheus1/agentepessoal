// O formato real: a Pasta é escrita pelo próprio pasta.py (o helper do agente) numa raiz temporária e lida aqui.
// Pula (com aviso) se não houver python3.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { loadSecondBrain, normalizeDecisions, handleSecondBrainRequest } from "../lib/second-brain.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PASTA_PY = path.resolve(HERE, "../../infra/vm/plugins/cerebro/helpers/pasta.py");
const temPython = spawnSync("python3", ["--version"]).status === 0;

const ESCRITOR = `
import importlib.util, sys, json
spec = importlib.util.spec_from_file_location("pasta", sys.argv[1]); p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
from pathlib import Path
p.RAIZ = Path(sys.argv[2]) / "segundo_cerebro" / "pasta"
p.estrutura()
(p.RAIZ / p.MARCA_MIGRADO).write_text("ok")
p.gravar("decisoes", [
  {"id": 35, "tema": "loja.fornecedor", "tipo": "decisao", "valor": "Fechar com o fornecedor B", "citacao": "vai com o B", "estado": "ativa", "area": "Raiz", "em": 1790000000, "liga": ["assunto:x1y2z3", "pendencia:ab12cd"]},
  {"id": 34, "tema": "loja.fornecedor", "tipo": "decisao", "valor": "Fornecedor A", "estado": "substituida", "substituida_por": 35, "area": "Raiz", "em": 1789000000},
])
p.gravar("pendencias", [{"id": "ab12cd", "titulo": "Assinar o contrato do B", "estado": "aberto", "area": "Raiz", "dono": "você", "prazo": "2026-11-01", "criado": 1790000000, "atualizado": 1790000000, "liga": ["decisao:35"]},
                        {"id": "[old] fio 7", "titulo": "Fio antigo com id estranho", "estado": "resolvido", "area": "pessoal", "ligacoes": "ver a planilha"}])
p.gravar("assuntos", [{"id": "x1y2z3", "titulo": "Fornecedor da loja", "onde_parou": "Escolhido o B; falta assinar", "estado": "andamento", "area": "Raiz", "criado": 1789000000, "atualizado": 1790000000, "historico": [{"em": 1790000000, "nota": "escolheu o B"}]}])
p.gravar_contexto("organizacao.md", "A Raiz é uma loja sintética de teste que vende coisas.", "ok, grava")
# o mesmo item de novo: a 2a gravação de 34 move a 34 para o Arquivo-morto
p.gravar("decisoes", [{"id": 35, "tema": "loja.fornecedor", "tipo": "decisao", "valor": "Fechar com o fornecedor B", "citacao": "vai com o B", "estado": "ativa", "area": "Raiz", "em": 1790000000, "liga": ["assunto:x1y2z3", "pendencia:ab12cd"]}])
print(json.dumps(sorted(str(f.relative_to(p.RAIZ)) for f in p.RAIZ.rglob("*.md"))))
`;

test("o que o pasta.py grava é o que o site lê (frontmatter, liga, [[links]], contexto, Arquivo-morto)", { skip: !temPython && "python3 indisponível" }, async () => {
  const root = mkdtempSync(path.join(tmpdir(), "sc-real-"));
  try {
    const r = spawnSync("python3", ["-I", "-c", ESCRITOR, PASTA_PY, root], { encoding: "utf8" });
    assert.equal(r.status, 0, r.stderr);
    const arquivos = JSON.parse(r.stdout);
    assert.ok(arquivos.some((a) => a.startsWith("Arquivo-morto/Decisoes/0034-")), "a 34 foi para o Arquivo-morto");
    const b = await loadSecondBrain({ root, now: new Date("2026-10-20T12:00:00Z") });
    assert.deepEqual(b.warnings, []);
    assert.deepEqual(b.decisions.map((d) => [d.id, d.area, d.vigente]), [["35", "Raiz", true]], "o Arquivo-morto não aparece");
    assert.deepEqual(b.threads.map((t) => [t.id, t.emAberto]).sort(), [["[old] fio 7", false], ["ab12cd", true]]);
    assert.equal(b.subjects[0].onde_parou, "Escolhido o B; falta assinar");
    assert.deepEqual(b.contexts.map((c) => [c.id, c.estado]), [["organizacao", "validado"], ["marca", "pendente"], ["estrategia", "pendente"], ["cliente-ideal", "pendente"], ["pessoas-chave", "pendente"], ["perfil", "pendente"]]);
    assert.equal(b.sources.find((s) => s.id === "perfil").codigo, "pendente", "perfil.md criado pela estrutura ainda é pendente");
    const lig = b.links.filter((l) => l.resolvido).map((l) => `${l.de}>${l.para}:${l.vias.join("+")}`).sort();
    assert.deepEqual(lig, ["decisao:35>assunto:x1y2z3:liga+wiki", "decisao:35>pendencia:ab12cd:liga+wiki", "pendencia:ab12cd>decisao:35:liga+wiki"], "liga e o [[link]] que o corpo gera são a mesma ligação");
    assert.ok(!b.links.some((l) => /Arquivo-morto|0034/.test(`${l.para} ${l.alvo}`)), "nada aponta para o Arquivo-morto");
    assert.ok(b.links.some((l) => !l.resolvido && l.alvo === "ver a planilha" && l.vias.includes("ligacoes")), "texto livre de ligação vira referência");
    assert.equal(b.index[b.decisions[0].nota], "decisao:35");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("timestamps Unix e validade seguem o contrato das decisões", () => {
  const [d] = normalizeDecisions({ decisoes: [{ id: 1, estado: "ativa", em: 1700000000, valido_ate: 1700000100 }] }, { id: "decisoes", rotulo: "Decisões" }, "2026-01-01", new Date("2026-01-01"));
  assert.equal(d.em, "2023-11-14T22:13:20.000Z"); assert.equal(d.vigente, false); assert.equal(d.estadoEfetivo, "expirada");
});

test("adaptador HTTP real nega sem sessão/tenant e não deixa cache", async () => {
  const env = { SECOND_BRAIN_TOKEN_SHA256: createHash("sha256").update("fixture-not-a-real-secret").digest("hex"), SECOND_BRAIN_DATA_ROOT: "/nonexistent-fixture" };
  const server = createServer(async (req, res) => { const r = await handleSecondBrainRequest(new Request(`http://127.0.0.1${req.url}`, { headers: req.headers }), env); res.writeHead(r.status, r.headers); res.end(JSON.stringify(r.body)); });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const base = `http://127.0.0.1:${server.address().port}`;
    assert.equal((await fetch(base)).status, 401);
    assert.equal((await fetch(base + "?login=fernanda")).status, 400);
    assert.equal((await fetch(base, { headers: { "x-login": "fernanda" } })).status, 403);
    const r = await fetch(base, { headers: { Authorization: "Bearer fixture-not-a-real-secret" } });
    assert.equal(r.status, 200);
    assert.match(r.headers.get("cache-control"), /no-store/);
    const d = await r.json();
    assert.equal(d.owner, "matheus");
    assert.ok(d.sources.every((s) => s.estado === "indisponivel" && s.codigo === "ausente"));
  } finally { await new Promise((resolve) => server.close(resolve)); }
});
