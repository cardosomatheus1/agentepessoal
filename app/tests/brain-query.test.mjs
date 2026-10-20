// node --test tests/brain-query.test.mjs — consulta seletiva sobre a Pasta, roteiro, verificação e CLI. Só dados fictícios.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadSecondBrain, PENDENTE } from "../lib/second-brain.mjs";
import { consultar, roteiro, validarConsulta, verificar } from "../lib/brain-query.mjs";
import { executarConsulta, lerArgumentos, resumir } from "../lib/brain-cli.mjs";
import { criarFixture, frontmatter, PASTA, SENTINELA, FORA_DA_LISTA } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-20T12:00:00Z");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const comFixture = async (fn) => { const root = criarFixture(); try { await fn(root, () => loadSecondBrain({ root, now: NOW })); } finally { rmSync(root, { recursive: true, force: true }); } };
const hashes = (dir) => Object.fromEntries(readdirSync(dir, { recursive: true }).filter((e) => statSync(path.join(dir, e)).isFile()).map((e) => [e, createHash("sha256").update(readFileSync(path.join(dir, e))).digest("hex")]));

test("interface fechada: sem caminho, dono, raiz nem parâmetro livre", () => {
  for (const q of [
    { funcao: "retomar", termo: "x", owner: "fernanda" },
    { funcao: "retomar", termo: "x", root: "/etc" },
    { funcao: "fonte", fonte: "../../etc/passwd" },
    { funcao: "fonte", fonte: "rotinas" },
    { funcao: "registro", registro: "../segredo" },
    { funcao: "registro", registro: "decisao:1/../../x" },
    { funcao: "registro", registro: "decisao:..x" },
    { funcao: "registro", registro: "rotina:x" },
    { funcao: "rotina", registro: "rotina:x" },
    { funcao: "apagar" },
    { funcao: "buscar", termo: "x".repeat(81) },
    { funcao: "buscar", termo: "a\u0000b" },
    { funcao: "buscar", termo: "x", area: "a\nb" },
    null,
    ["retomar"],
  ]) assert.equal(validarConsulta(q).ok, false, JSON.stringify(q));
  assert.equal(validarConsulta({ funcao: "registro", registro: "decisao:12" }).ok, true);
  assert.equal(validarConsulta({ funcao: "registro", registro: "pendencia:[old] fio 7" }).ok, true, "id antigo com colchetes e espaço");
  assert.equal(validarConsulta({ funcao: "assuntos", area: "Raiz" }).ok, true);
  assert.deepEqual(lerArgumentos(["retomar", "--root", "/etc"]), { erro: "Argumento não aceito: --root" });
  assert.deepEqual(lerArgumentos(["retomar", "--dono", "fernanda"]), { erro: "Argumento não aceito: --dono" });
  assert.deepEqual(lerArgumentos(["assuntos", "--area", "Raiz"]).consulta, { funcao: "assuntos", area: "Raiz" });
  assert.ok(!/process\.env/.test(readFileSync(path.join(HERE, "../lib/brain-cli.mjs"), "utf8")), "CLI não lê raiz de variável de ambiente");
});

test("retomar: assunto com onde parou, tema explícito como metadado, ligações gravadas; não vigente fica fora", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const r = consultar(b, { funcao: "retomar", termo: "teste" });
  const decisoes = r.itens.filter((i) => i.tipo === "decisao");
  assert.deepEqual(decisoes.map((i) => i.ref), ["decisao:1", "decisao:2", "decisao:4"], "3 (substituída) e 5 (revogada) não governam");
  assert.ok(decisoes.every((i) => i.porque.startsWith("metadado: tema")));
  assert.ok(r.resumo.includes("2 decisão(ões) não vigentes ficaram de fora"));
  const loja = consultar(b, { funcao: "retomar", termo: "fornecedor" });
  assert.equal(loja.itens[0].ref, "assunto:s1");
  assert.equal(loja.itens[0].trecho, "Onde parou: Falta escolher entre os dois orçamentos");
  assert.deepEqual(loja.proximosPassos, [{ ref: "assunto:s1", texto: "Retomar de onde parou: Falta escolher entre os dois orçamentos" }]);
  const reg = consultar(b, { funcao: "retomar", registro: "assunto:s1" });
  assert.deepEqual(reg.itens[0].ref, "assunto:s1");
  assert.deepEqual(reg.itens.slice(1).map((i) => [i.ref, i.porque]).sort(), [["decisao:1", "ligação gravada: liga"], ["pendencia:a1", "ligação gravada: liga"]], "só o que está ligado de verdade (a nota do dia que cita o assunto não é decisão nem pendência)");
  const nada = consultar(b, { funcao: "retomar", registro: "assunto:naoexiste" });
  assert.ok(nada.bloqueios.some((x) => /não está na Pasta/.test(x.motivo)));
  assert.ok(!JSON.stringify([r, loja, reg]).includes(SENTINELA));
}));

test("assuntos (onde parou): em andamento primeiro, encerrado fora; área filtra", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const r = consultar(b, { funcao: "assuntos" });
  assert.deepEqual(r.itens.map((i) => i.ref), ["assunto:s1"]);
  assert.match(r.resumo, /1 encerrado/);
  assert.equal(consultar(b, { funcao: "assuntos", area: "pessoal" }).itens.length, 0, "s2 é pessoal mas está encerrado");
  assert.equal(consultar(b, { funcao: "assuntos", area: "NEXOS" }).itens.length, 0);
}));

test("filtro por área em todas as funções (contexto e perfil valem para todas)", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const raiz = consultar(b, { funcao: "fonte", fonte: "pendencias", area: "Raiz" });
  assert.deepEqual(raiz.itens.map((i) => [i.ref, i.area]), [["pendencia:a1", "Raiz"], ["pendencia:c3", "Raiz"]]);
  assert.match(raiz.resumo, /na área Raiz/);
  const p = consultar(b, { funcao: "prioridades", area: "Orbyte" });
  assert.deepEqual(p.itens.filter((i) => i.tipo === "pendencia").map((i) => i.ref), ["pendencia:b2"]);
  const busca = consultar(b, { funcao: "buscar", termo: "sintético", area: "Raiz" });
  assert.ok(busca.itens.length && busca.itens.every((i) => ["Raiz", "geral", "pessoal"].includes(i.area) && (i.area === "Raiz" || ["contexto", "fato"].includes(i.tipo))), JSON.stringify(busca.itens.map((i) => [i.ref, i.area])));
  assert.ok(!busca.itens.some((i) => i.ref === "pendencia:b2"), "Orbyte fica fora do recorte da Raiz");
  const etapas = roteiro(b, raiz);
  assert.match(etapas[0].detalhe, /área Raiz/);
}));

test("prioridades e pauta: pendências pela regra; contexto pendente bloqueia, validado entra", () => comFixture(async (root, carregar) => {
  let b = await carregar();
  const p = consultar(b, { funcao: "prioridades" });
  assert.deepEqual(p.itens.filter((i) => i.tipo === "pendencia").map((i) => i.ref), ["pendencia:a1", "pendencia:b2", "pendencia:d4"], "alta, média, baixa; resolvida fora; adiada vencida dentro");
  assert.deepEqual(p.itens.filter((i) => i.tipo === "decisao").map((i) => i.ref), ["decisao:2"], "só a proibição vigente como limite");
  assert.ok(p.itens.some((i) => i.ref === "contexto:estrategia"), "estratégia validada entra");
  assert.ok(!p.bloqueios.some((x) => /Estratégia/.test(x.motivo)));
  const pauta = consultar(b, { funcao: "pauta", termo: "lançamento" });
  assert.deepEqual(pauta.itens.filter((i) => i.tipo === "pendencia").map((i) => i.ref), ["pendencia:a1"], "c3 também fala de lançamento, mas está resolvida");
  assert.ok(pauta.bloqueios.some((x) => /Pessoas-chave pendente/.test(x.motivo)));
  writeFileSync(path.join(root, PASTA, "Contexto/estrategia.md"), `${frontmatter({ status: "pendente" })}# Estratégia\n\n${PENDENTE}\n`);
  writeFileSync(path.join(root, PASTA, "Contexto/pessoas-chave.md"), `${frontmatter({ status: "validado", aprovado: "ok" })}# Pessoas-chave\n\n- Sócio sintético: cuida do financeiro\n`);
  b = await carregar();
  assert.ok(consultar(b, { funcao: "prioridades" }).bloqueios.some((x) => /Estratégia pendente/.test(x.motivo)));
  const pauta2 = consultar(b, { funcao: "pauta" });
  assert.ok(pauta2.itens.some((i) => i.ref === "contexto:pessoas-chave") && !pauta2.bloqueios.length);
  const ctx = consultar(b, { funcao: "contexto" });
  assert.equal(ctx.itens.length, 6);
  assert.match(ctx.resumo, /validada\(s\), \d pendente\(s\)/);
}));

test("busca só ordena; registro mostra só relações explícitas", () => comFixture(async (root, carregar) => {
  const b = await carregar();
  const busca = consultar(b, { funcao: "buscar", termo: "lançamento" });
  assert.deepEqual(busca.itens.map((i) => i.ref).slice(0, 2).sort(), ["pendencia:a1", "pendencia:c3"]);
  assert.ok(busca.itens.every((i) => /não é vínculo/.test(i.porque)));
  const reg = consultar(b, { funcao: "registro", registro: "pendencia:a1" });
  const rel = reg.itens.slice(1).map((i) => i.ref).sort();
  assert.deepEqual(rel, ["assunto:s1", "decisao:1", "fonte:pendencias", "pendencia:b2", "referencia:Depende do catálogo sintético", "referencia:conversa sintética", "reuniao:2026-10-15-reuniao-raiz"].sort());
  assert.ok(reg.itens.slice(1).every((i) => i.porque.startsWith("relação explícita")));
  assert.ok(!rel.includes("pendencia:c3"));
}));

test("verificação relê a Pasta: igual => verificado; mudou => divergente; nada é gravado", () => comFixture(async (root, carregar) => {
  const antes = hashes(root);
  const b = await carregar();
  const r = consultar(b, { funcao: "prioridades" });
  const v = verificar(r, await carregar());
  assert.equal(v.estado, "verificado");
  assert.deepEqual(v.registros, { citados: r.itens.length, presentes: r.itens.length });
  assert.deepEqual(hashes(root), antes);
  rmSync(path.join(root, PASTA, "Pendencias/b2-catalogo-sintetico.md"));
  const v2 = verificar(r, await carregar());
  assert.equal(v2.estado, "divergente");
  assert.ok(v2.fontes.some((x) => x.id === "pendencias" && !x.igual));
  assert.equal(v2.registros.presentes, r.itens.length - 1);
}));

test("CLI: executa a consulta com carga, roteiro e verificação; recusa argumento livre", () => comFixture(async (root, carregar) => {
  const r = await executarConsulta({ funcao: "assuntos" }, carregar);
  assert.equal(r.ok, true);
  assert.equal(r.verificacao.estado, "verificado");
  assert.deepEqual(resumir(r).etapas, ["captura:feito", "validacao:feito", "consulta:feito", "execucao:nao_executado", "verificacao:verificado"]);
  assert.deepEqual(r.roteiro[3].proposta, ["Retomar de onde parou: Falta escolher entre os dois orçamentos (assunto:s1)"]);
  assert.deepEqual(await executarConsulta({ funcao: "fonte", fonte: "/etc" }, carregar), { ok: false, erro: "Fonte desconhecida." });
  const p = spawnSync(process.execPath, [path.join(HERE, "../lib/brain-cli.mjs"), "retomar", "--root", root], { encoding: "utf8" });
  assert.equal(p.status, 2);
  assert.match(p.stderr, /Argumento não aceito: --root/);
  assert.ok(!JSON.stringify(r).includes(FORA_DA_LISTA));
}));
