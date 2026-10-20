// node --test tests/brain-query.test.mjs — consulta seletiva, roteiro, verificação e CLI. Só dados fictícios.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadSecondBrain } from "../lib/second-brain.mjs";
import { consultar, roteiro, validarConsulta, verificar } from "../lib/brain-query.mjs";
import { executarConsulta, lerArgumentos, resumir } from "../lib/brain-cli.mjs";
import { criarFixture, SENTINELA, FORA_DA_LISTA } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-18T12:00:00Z");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const comFixture = async (fn) => { const root = criarFixture(); try { await fn(root, () => loadSecondBrain({ root, now: NOW })); } finally { rmSync(root, { recursive: true, force: true }); } };
const hashes = (dir) => Object.fromEntries(readdirSync(dir, { recursive: true }).filter((e) => statSync(path.join(dir, e)).isFile()).map((e) => [e, createHash("sha256").update(readFileSync(path.join(dir, e))).digest("hex")]));

test("interface fechada: sem caminho, dono, raiz nem parâmetro livre", () => {
  for (const q of [
    { funcao: "retomar", termo: "x", owner: "fernanda" },
    { funcao: "retomar", termo: "x", root: "/etc" },
    { funcao: "fonte", fonte: "../../etc/passwd" },
    { funcao: "registro", registro: "../segredo" },
    { funcao: "registro", registro: "decisao:1/../../x" },
    { funcao: "apagar" },
    { funcao: "buscar", termo: "x".repeat(81) },
    { funcao: "buscar", termo: "a\u0000b" },
    null,
    ["retomar"],
  ]) assert.equal(validarConsulta(q).ok, false, JSON.stringify(q));
  assert.equal(validarConsulta({ funcao: "registro", registro: "decisao:12" }).ok, true);
  assert.deepEqual(lerArgumentos(["retomar", "--root", "/etc"]), { erro: "Argumento não aceito: --root" });
  assert.deepEqual(lerArgumentos(["retomar", "--dono", "fernanda"]), { erro: "Argumento não aceito: --dono" });
  const cli = readFileSync(path.join(HERE, "../lib/brain-cli.mjs"), "utf8");
  assert.ok(!/process\.env/.test(cli), "CLI não lê raiz de variável de ambiente");
});

test("fluxo A — retomar: tema explícito vira metadado, palavra só ordena, decisão não vigente fica fora", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const r = consultar(b, { funcao: "retomar", termo: "teste" });
  assert.equal(r.ok, true);
  const decisoes = r.itens.filter((i) => i.tipo === "decisao");
  assert.deepEqual(decisoes.map((i) => i.ref), ["decisao:1", "decisao:2", "decisao:4"], "3 (substituída) e 5 (revogada) não governam");
  assert.ok(decisoes.every((i) => i.porque.startsWith("metadado: tema")));
  assert.ok(r.itens.filter((i) => i.tipo === "contexto").every((i) => i.porque.startsWith("busca textual")));
  assert.ok(r.resumo.includes("2 decisão(ões) não vigentes ficaram de fora"));
  const ctx = consultar(b, { funcao: "retomar", termo: "sintético" });
  assert.ok(ctx.itens.some((i) => i.tipo === "contexto") && ctx.itens.some((i) => i.tipo === "fio"));
  assert.ok(ctx.itens.every((i) => i.proveniencia || i.tipo === "onboarding"));
  assert.ok(ctx.proximosPassos.some((p) => p.ref === "fio:a1" && p.texto === "Revisar o roteiro"), "próximo passo é o gravado no fio");
  const proj = consultar(b, { funcao: "retomar", registro: "projeto:meta-nexos" });
  assert.equal(proj.itens[0].ref, "projeto:meta-nexos");
  const outro = consultar(b, { funcao: "retomar", registro: "projeto:saude" });
  assert.ok(outro.bloqueios.some((x) => /dono comprovado/.test(x.motivo)), "projeto de outra pessoa não se abre");
  assert.ok(!JSON.stringify([r, ctx, proj, outro]).includes(SENTINELA));
}));

test("fluxo A sem contexto: a fonte indisponível bloqueia e isso é dito", () => comFixture(async (root, carregar) => {
  rmSync(path.join(root, "chats/uMqjehmr/contexto.md"));
  const r = consultar(await carregar(), { funcao: "retomar", termo: "sintético" });
  assert.ok(r.bloqueios.some((x) => x.fonte === "contexto" && /indisponível \(ausente\)/.test(x.motivo)));
  assert.equal(r.estado, "parcial");
}));

test("fluxo B — rotina: entradas, passos, aprovação, verificação e entrega; execução nunca acontece", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const r = consultar(b, { funcao: "rotina", registro: "rotina:orquestrar-a0-hermes-openclaw" });
  assert.equal(r.estado, "ok");
  const etapas = roteiro(b, r);
  assert.deepEqual(etapas.map((e) => e.etapa), ["captura", "validacao", "consulta", "execucao", "verificacao"]);
  const exec = etapas[3];
  assert.equal(exec.estado, "nao_executado");
  assert.deepEqual(exec.proposta, ["1. Ler o arquivo sintético", "2. Conferir o total"]);
  assert.equal(exec.entrega, "Resumo de uma linha.");
  assert.deepEqual(etapas[1].aprovacoes[0], { ref: "rotina:orquestrar-a0-hermes-openclaw", texto: "Antes de enviar qualquer coisa a terceiros." });
  assert.ok(etapas[1].aprovacoes.some((a) => a.ref === "decisao:2"), "proibição vigente entra como regra");
  assert.match(etapas[4].detalhe, /O total confere com o arquivo/);
  const fora = consultar(b, { funcao: "rotina", registro: "rotina:fora-da-lista" });
  assert.equal(fora.estado, "bloqueado");
  assert.ok(!JSON.stringify(fora).includes(FORA_DA_LISTA));
}));

test("fluxo C — prioridades e pauta pela regra dos fios; lacunas declaradas", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const p = consultar(b, { funcao: "prioridades" });
  assert.deepEqual(p.itens.filter((i) => i.tipo === "fio").map((i) => i.ref), ["fio:a1", "fio:b2", "fio:d4"], "alta, média, baixa; resolvido fora; adiado vencido dentro");
  assert.deepEqual(p.itens.filter((i) => i.tipo === "decisao").map((i) => i.ref), ["decisao:2"], "só a proibição vigente como limite");
  assert.ok(p.bloqueios.some((x) => /estratégia/.test(x.motivo)));
  const pauta = consultar(b, { funcao: "pauta", termo: "lançamento" });
  assert.deepEqual(pauta.itens.filter((i) => i.tipo === "fio").map((i) => i.ref), ["fio:a1"], "c3 também fala de lançamento, mas está resolvido");
  assert.ok(pauta.bloqueios.some((x) => /pessoas-chave/.test(x.motivo)));
  const reun = consultar(b, { funcao: "fonte", fonte: "reunioes" });
  assert.equal(reun.estado, "bloqueado");
  assert.ok(reun.bloqueios.some((x) => /não existe fonte canônica/.test(x.motivo)));
}));

test("busca só ordena; registro mostra apenas relações explícitas; onboarding é proposta", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const busca = consultar(b, { funcao: "buscar", termo: "lançamento" });
  assert.deepEqual(busca.itens.map((i) => i.ref).slice(0, 2).sort(), ["fio:a1", "fio:c3"]);
  assert.ok(busca.itens.every((i) => /não é vínculo/.test(i.porque)));
  const reg = consultar(b, { funcao: "registro", registro: "fio:a1" });
  const rel = reg.itens.slice(1);
  assert.deepEqual(rel.map((i) => i.ref).sort(), ["fio:b2", "fonte:fios", "referencia:Depende do catálogo sintético", "referencia:conversa sintética"].sort());
  assert.ok(rel.every((i) => i.porque.startsWith("relação explícita")));
  assert.ok(!rel.some((i) => i.ref === "fio:c3"));
  const onb = consultar(b, { funcao: "onboarding" });
  assert.equal(onb.itens.length, 13);
  assert.ok(onb.resumo.endsWith("0 aprovada(s)."));
}));

test("verificação relê as fontes: igual => verificado; mudou => divergente; nada é gravado", () => comFixture(async (root, carregar) => {
  const antes = hashes(root);
  const b = await carregar();
  const r = consultar(b, { funcao: "prioridades" });
  const v = verificar(r, await carregar());
  assert.equal(v.estado, "verificado");
  assert.deepEqual(v.registros, { citados: r.itens.length, presentes: r.itens.length });
  assert.deepEqual(hashes(root), antes);
  const f = path.join(root, "fios/matheus.json");
  const dados = JSON.parse(readFileSync(f, "utf8"));
  dados.fios = dados.fios.filter((x) => x.id !== "b2");
  writeFileSync(f, JSON.stringify(dados));
  const v2 = verificar(r, await carregar());
  assert.equal(v2.estado, "divergente");
  assert.ok(v2.fontes.some((x) => x.id === "fios" && !x.igual));
  assert.equal(v2.registros.presentes, r.itens.length - 1);
}));

test("CLI: executa a consulta com carga, roteiro e verificação; recusa argumento livre", () => comFixture(async (root, carregar) => {
  const r = await executarConsulta({ funcao: "rotina", registro: "rotina:orquestrar-a0-hermes-openclaw" }, carregar);
  assert.equal(r.ok, true);
  assert.equal(r.verificacao.estado, "verificado");
  assert.equal(r.roteiro.at(-1).estado, "verificado");
  assert.deepEqual(resumir(r).etapas, ["captura:feito", "validacao:feito", "consulta:feito", "execucao:nao_executado", "verificacao:verificado"]);
  const erro = await executarConsulta({ funcao: "fonte", fonte: "/etc" }, carregar);
  assert.deepEqual(erro, { ok: false, erro: "Fonte desconhecida." });
  const p = spawnSync(process.execPath, [path.join(HERE, "../lib/brain-cli.mjs"), "retomar", "--root", root], { encoding: "utf8" });
  assert.equal(p.status, 2);
  assert.match(p.stderr, /Argumento não aceito: --root/);
}));
