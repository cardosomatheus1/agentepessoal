// node --test tests/second-brain-full.test.mjs — a Pasta inteira: formato, estados, ligações, área, Arquivo-morto.
import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadSecondBrain, parseFrontmatter, wikiLinks, Ilegivel, redact, PENDENTE } from "../lib/second-brain.mjs";
import { criarFixture, naPasta, frontmatter, ficha, stemDe, DECISOES, PASTA, SENTINELA, FORA_DA_LISTA } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-20T12:00:00Z");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const comFixture = async (fn, opts) => { const root = criarFixture(opts); try { await fn(root); } finally { rmSync(root, { recursive: true, force: true }); } };
const hashes = (dir) => Object.fromEntries(readdirSync(dir, { recursive: true }).filter((e) => statSync(path.join(dir, e)).isFile()).map((e) => [e, createHash("sha256").update(readFileSync(path.join(dir, e))).digest("hex")]));
const fonte = (b, id) => b.sources.find((s) => s.id === id);
const arq = (root, rel) => path.join(root, PASTA, rel);

test("frontmatter: o mesmo formato do pasta.ler_frontmatter (JSON por linha, derivados fora, desvio = ilegível)", () => {
  const { campos, corpo } = parseFrontmatter('---\nid: 35\ntema: "loja: fornecedor"\nliga: ["decisao:1", "assunto:x"]\nhistorico: [{"em": 1.5, "nota": "a: b"}]\nvazio: null\nstatus: "ativa"\ntags: ["decisao", "raiz"]\n\n---\n# Corpo\n');
  assert.deepEqual({ ...campos }, { id: 35, tema: "loja: fornecedor", liga: ["decisao:1", "assunto:x"], historico: [{ em: 1.5, nota: "a: b" }], vazio: null });
  assert.equal(corpo, "# Corpo\n");
  for (const ruim of ["sem cabeçalho\n", "---\nid: 1\n", "---\nid 1\n---\n", "---\nid: nao-json\n---\n", "---\nid: \"aberto\n---\n", "---\n---\n"]) {
    assert.throws(() => parseFrontmatter(ruim, "x.md"), Ilegivel, JSON.stringify(ruim));
  }
  const p = parseFrontmatter('---\n__proto__: {"poluido": true}\nid: 1\n---\n');
  assert.equal(({}).poluido, undefined);
  assert.equal(p.campos.id, 1);
  assert.deepEqual(wikiLinks("ver [[Decisoes/0035-x]], [[Contexto/organizacao|org]] e [[Assuntos/x1#Histórico]]; [[./Documentos/a.md]] [[Decisoes/0035-x]]"), ["Decisoes/0035-x", "Contexto/organizacao", "Assuntos/x1", "Documentos/a"]);
});

test("cada item carrega a área, a referência e a proveniência (arquivo na Pasta); nada dos registros antigos", () => comFixture(async (root) => {
  const antes = hashes(root);
  const b = await loadSecondBrain({ root, now: NOW });
  for (const lista of [b.decisions, b.threads, b.subjects, b.contexts, b.meetings, b.daily, b.documents, b.projects, b.profile]) {
    for (const item of lista) {
      const p = item.proveniencia;
      assert.ok(item.area, JSON.stringify(item));
      assert.ok(p && p.fonte && p.fonteRotulo && p.localizador && p.dono === "matheus" && p.arquivoAtualizadoEm, JSON.stringify(p));
      assert.ok(!path.isAbsolute(p.localizador));
    }
  }
  assert.equal(b.decisions[0].proveniencia.localizador, `Decisoes/${stemDe("decisao", DECISOES[0])}.md`);
  assert.equal(b.decisions[0].ref, "decisao:1");
  assert.deepEqual(b.areas, ["geral", "NEXOS", "Orbyte", "pessoal", "Raiz"]);
  const json = JSON.stringify(b);
  assert.ok(!json.includes(FORA_DA_LISTA), "nada das nove fontes antigas");
  assert.ok(!json.includes(root));
  assert.deepEqual(hashes(root), antes, "nenhuma escrita");
}));

test("ids, vigência, substituição, pendência em aberto e assunto em andamento seguem os contratos", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b.decisions.map((d) => [d.id, d.estadoEfetivo, d.vigente]), [["1", "ativa", true], ["2", "ativa", true], ["3", "substituida", false], ["4", "ativa", true], ["5", "revogada", false]]);
  assert.equal(b.decisions[3].substitui, "3");
  assert.equal(b.decisions[2].substituida_por, "4");
  assert.equal(b.decisions[4].motivo, "mudou de ideia");
  assert.deepEqual(b.threads.map((f) => [f.id, f.emAberto]), [["a1", true], ["b2", true], ["c3", false], ["d4", true]], "adiado com data vencida volta a contar");
  assert.deepEqual(b.subjects.map((a) => [a.id, a.estado, a.emAndamento, a.onde_parou]), [["s1", "andamento", true, "Falta escolher entre os dois orçamentos"], ["s2", "encerrado", false, "Decidiu ficar onde está"]]);
  assert.deepEqual(b.subjects[0].historico.map((h) => h.nota), ["começou", "dois orçamentos na mesa"]);
  assert.deepEqual(b.profile.map((f) => f.numero), [1, 2]);
  assert.deepEqual(b.daily.map((n) => n.id), ["2026-10-19", "2026-10-18"], "nota do dia mais recente primeiro");
  assert.deepEqual(fonte(b, "notas").arquivos, [{ chave: "rascunho.md", codigo: "nome_fora_do_padrao" }], "nome fora de AAAA-MM-DD não vira nota do dia");
  assert.deepEqual(b.meetings.map((m) => [m.titulo, m.data, m.area]), [["Reunião da Raiz", "2026-10-15", "Raiz"]]);
  assert.deepEqual(b.rules.regras, ["Leia `Contexto/` antes.", "Nunca invente: o que falta fica marcado. Continua na linha de baixo.", "Nada se apaga."]);
}));

test("contexto: pendente e validado separados; perfil pendente não é ficha vazia nem formato antigo", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b.contexts.map((c) => [c.id, c.estado]), [["organizacao", "validado"], ["marca", "pendente"], ["estrategia", "validado"], ["cliente-ideal", "pendente"], ["pessoas-chave", "pendente"], ["perfil", "validado"]]);
  const org = b.contexts[0];
  assert.equal(org.aprovado, "ok, pode gravar");
  assert.ok(org.validadoEm);
  assert.deepEqual(org.secoes.map((s) => s.titulo), [null, "Ferramentas"]);
  assert.ok(!JSON.stringify(b.contexts).includes(PENDENTE), "o marcador não vira texto");
  assert.deepEqual(b.gaps.filter((g) => g.id.startsWith("contexto-")).map((g) => g.id), ["contexto-marca", "contexto-cliente-ideal", "contexto-pessoas-chave"]);
  // perfil ainda não preenchido pela entrevista
  writeFileSync(arq(root, "Contexto/perfil.md"), `${frontmatter({ status: "pendente", tags: ["contexto", "perfil"] })}# Perfil do Matheus\n\n${PENDENTE}\n`);
  let c = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual([fonte(c, "perfil").estado, fonte(c, "perfil").codigo], ["vazia", "pendente"]);
  assert.equal(c.contexts.find((x) => x.id === "perfil").estado, "pendente");
  assert.ok(!c.warnings.some((w) => w.fonte === "perfil"), "pendente é esperado, não é falha");
  // ficha no formato antigo (texto livre, sem a marca)
  writeFileSync(arq(root, "Contexto/perfil.md"), "# Perfil antigo\n- texto livre de antes da migração\n");
  c = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual([fonte(c, "perfil").estado, fonte(c, "perfil").codigo], ["indisponivel", "formato_antigo"]);
  assert.equal(c.profile.length, 0);
  // seção de contexto que sumiu: a fonte fica parcial e diz qual
  rmSync(arq(root, "Contexto/marca.md"));
  c = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual([fonte(c, "contexto").codigo, fonte(c, "contexto").arquivos], ["parcial", [{ chave: "marca.md", codigo: "ausente" }]]);
}));

test("item ilegível: a coleção vira erro com aviso (nunca lista vazia nem 'tudo certo'); nota livre ilegível deixa a fonte parcial", () => comFixture(async (root) => {
  writeFileSync(arq(root, "Pendencias/zz-quebrada.md"), "---\nid: \"zz\"\ntitulo: sem aspas no fim\n---\n# quebrada\n");
  writeFileSync(arq(root, "Assuntos/s3-sem-cabecalho.md"), "# Assunto sem cabeçalho\n");
  writeFileSync(arq(root, "Reunioes/2026-10-16-x.md"), "---\narea: Raiz\n");
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual([fonte(b, "pendencias").estado, fonte(b, "pendencias").codigo], ["indisponivel", "ilegivel"]);
  assert.deepEqual(fonte(b, "pendencias").arquivos, [{ chave: "zz-quebrada.md", codigo: "ilegivel" }]);
  assert.equal(b.threads.length, 4, "os legíveis continuam visíveis");
  assert.deepEqual([fonte(b, "assuntos").estado, fonte(b, "assuntos").codigo], ["indisponivel", "ilegivel"]);
  assert.deepEqual([fonte(b, "reunioes").estado, fonte(b, "reunioes").codigo], ["ok", "parcial"]);
  const avisos = b.warnings.map((w) => [w.fonte, w.codigo]);
  assert.deepEqual(avisos, [["pendencias", "ilegivel"], ["assuntos", "ilegivel"], ["reunioes", "parcial"]]);
  assert.match(b.warnings[0].mensagem, /NÃO está completa.*zz-quebrada\.md \(ilegivel\)/);
  assert.ok(b.gaps.some((g) => g.id === "fonte-pendencias"));
  // todos ilegíveis: continua erro, não "vazia"
  for (const f of readdirSync(arq(root, "Decisoes"))) if (f !== "indice.md") writeFileSync(arq(root, `Decisoes/${f}`), "lixo");
  const c = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual([fonte(c, "decisoes").estado, fonte(c, "decisoes").codigo, c.decisions.length], ["indisponivel", "ilegivel", 0]);
}));

test("Arquivo-morto nunca aparece: nem item, nem link, nem nó; o link só conta na lacuna", () => comFixture(async (root) => {
  naPasta(root, "Notas-do-dia/2026-10-20.md", `# Nota\n\n- [[Arquivo-morto/Decisoes/0009-x]] e [[/Arquivo-morto/${SENTINELA}]]\n`);
  const b = await loadSecondBrain({ root, now: NOW });
  const json = JSON.stringify(b);
  assert.ok(!json.includes(SENTINELA));
  assert.ok(!json.includes("Arquivo-morto/"), "nenhum item, ligação, índice ou nome de link do Arquivo-morto");
  assert.ok(json.includes("(no Arquivo-morto)"), "o link no texto vira só um aviso");
  assert.ok(!b.sources.some((s) => /Arquivo-morto/.test(s.localizador)));
  assert.match(b.gaps.find((g) => g.id === "arquivo-morto").motivo, /^3 link/);
  assert.ok(!b.decisions.some((d) => d.id === "9"));
}));

test("ligações: de `liga` e de [[links]] entre Decisão, Pendência, Assunto, Contexto, Reunião, Nota e Documento", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  const l = (de, para) => b.links.find((x) => x.de === de && x.para === para);
  assert.deepEqual(l("decisao:1", "pendencia:a1").vias, ["liga", "wiki"], "liga e o link que o corpo repete viram uma ligação só");
  assert.deepEqual(l("pendencia:a1", "assunto:s1").vias, ["liga", "wiki"]);
  assert.deepEqual(l("assunto:s1", "decisao:1").vias, ["liga", "wiki"]);
  assert.deepEqual(l("contexto:organizacao", "decisao:1").vias, ["wiki"]);
  assert.deepEqual(l("reuniao:2026-10-15-reuniao-raiz", "pendencia:a1").vias, ["wiki"]);
  assert.deepEqual(l("nota:2026-10-19", "assunto:s1").vias, ["wiki"]);
  assert.deepEqual(l("documento:auditoria-2026-10-20", "contexto:organizacao").vias, ["wiki"], "[[x|apelido]] também liga");
  assert.deepEqual(l("pendencia:b2", "pendencia:a1").vias, ["ligacoes"], "id de pendência no texto de ligação antigo");
  assert.ok(!l("decisao:4", "decisao:3") && !l("decisao:3", "decisao:4"), "substituição fica na relação própria, não duplica como link");
  const soltas = b.links.filter((x) => !x.resolvido).map((x) => [x.de, x.para]);
  assert.deepEqual(soltas, [["pendencia:a1", "referencia:Depende do catálogo sintético"], ["documento:auditoria-2026-10-20", "referencia:Documentos/inexistente"]], "destino fora da Pasta vira referência, nunca inventado");
  assert.ok(!b.links.some((x) => x.de === "pendencia:a1" && x.para === "pendencia:c3"), "'Lançamento' nos dois títulos não é ligação");
  for (const x of b.links) assert.ok(x.evidencia.fonte && x.evidencia.campo && x.evidencia.localizador, JSON.stringify(x));
  assert.equal(b.index["Contexto/organizacao"], "contexto:organizacao");
  assert.equal(b.index[`Pendencias/a1-lancamento-sintetico`], "pendencia:a1");
  // liga para item inexistente vira diagnóstico (não autoritativo)
  naPasta(root, "Decisoes/0007-quebrada.md", frontmatter({ id: 7, tema: "t.q", valor: "Liga para o nada", estado: "ativa", liga: ["assunto:naoexiste"] }) + "# q\n");
  const c = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(c.diagnostics.filter((d) => d.tipo === "liga_quebrada").map((d) => [d.registros, d.detalhe]), [[["decisao:7"], "liga = assunto:naoexiste"]]);
}));

test("Pasta não migrada: aviso e lacuna (o agente ainda grava nos registros antigos)", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  assert.equal(b.pasta.migrada, false);
  assert.deepEqual(b.warnings.map((w) => [w.fonte, w.codigo]), [["pasta", "nao_migrada"]]);
  assert.equal(b.gaps[0].id, "pasta-nao-migrada");
}, { migrada: false }));

test("dados pessoais e segredos são redigidos antes da projeção", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  const json = JSON.stringify(b);
  for (const proibido of ["teste@exemplo.com.br", "98765-4321", "123.456.789-09", "sk-abcdefghijklmnopqrstuvwxyz123", "abc123def456"]) assert.ok(!json.includes(proibido), proibido);
  assert.ok(json.includes("[e-mail removido]") && json.includes("[telefone removido]") && json.includes("[documento removido]"));
  assert.equal(redact("CNPJ 12.345.678/0001-90 cartão 4111 1111 1111 1111"), "CNPJ [documento removido] cartão [número removido]");
  const comum = "sha 46c5d2c372c39377c63b7dc52ce716733be911d5 chamado 34938963 loja 4199543 em 17/10/2026 11:35";
  assert.equal(redact(comum), comum);
}));

test("texto longo é cortado e contado", () => comFixture(async (root) => {
  naPasta(root, "Decisoes/0008-longa.md", frontmatter({ id: 8, tema: "t.l", valor: "v".repeat(5000), estado: "ativa" }) + "# l\n");
  const b = await loadSecondBrain({ root, now: NOW });
  const d = b.decisions.find((x) => x.id === "8");
  assert.ok(d.valor.endsWith("…") && d.valor.length === 4001);
  assert.ok(fonte(b, "decisoes").truncados >= 1);
}));

test("cada carga relê a Pasta: mudança aparece na próxima leitura, com nova impressão só na fonte que mudou", () => comFixture(async (root) => {
  const a = await loadSecondBrain({ root, now: NOW });
  naPasta(root, "Pendencias/e5-nova.md", frontmatter({ id: "e5", titulo: "Pendência nova", estado: "aberto", area: "Raiz", criado: 1790000600 }) + "# Pendência nova\n");
  const b = await loadSecondBrain({ root, now: NOW });
  assert.notEqual(fonte(a, "pendencias").impressao, fonte(b, "pendencias").impressao);
  assert.equal(fonte(a, "decisoes").impressao, fonte(b, "decisoes").impressao);
  assert.ok(b.threads.some((f) => f.id === "e5") && !a.threads.some((f) => f.id === "e5"));
}));

test("conflito só com evidência estruturada; assunto parecido não é conflito", () => comFixture(async (root) => {
  const b0 = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b0.conflicts, []);
  assert.deepEqual(b0.diagnostics, []);
  naPasta(root, "Decisoes/0006-longo.md", frontmatter({ id: 6, tema: "teste.tom", tipo: "preferencia", valor: "Responder longo", estado: "ativa" }) + "# x\n");
  naPasta(root, "Decisoes/0099-substitui.md", frontmatter({ id: 7, tema: "teste.x", valor: "Aponta para inexistente", estado: "ativa", substitui: 99 }) + "# x\n");
  writeFileSync(arq(root, "Contexto/perfil.md"), ficha(["Mora numa cidade fictícia", "mora numa cidade FICTÍCIA!"]));
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b.conflicts.map((c) => [c.tipo, c.registros]), [["decisoes_ativas_mesmo_tema", ["decisao:1", "decisao:6"]], ["ficha_entrada_duplicada", ["fato:perfil-1", "fato:perfil-2"]]]);
  assert.ok(b.conflicts.every((c) => c.autoritativo === false && c.regra));
  assert.deepEqual(b.diagnostics.map((x) => x.tipo), ["referencia_quebrada"]);
}));

test("os módulos não gravam; brain-graph e brain-query são puros (rodam no navegador)", () => {
  for (const f of ["second-brain.mjs", "brain-graph.mjs", "brain-query.mjs", "brain-cli.mjs"]) {
    const src = readFileSync(path.join(HERE, "../lib", f), "utf8");
    assert.ok(!/writeFile|appendFile|\bunlink|\brm\(|mkdir|rename\(/.test(src), f);
  }
  for (const f of ["brain-graph.mjs", "brain-query.mjs", "brain-cli.mjs"]) assert.ok(!/readdir/.test(readFileSync(path.join(HERE, "../lib", f), "utf8")), `${f} não varre`);
  for (const f of ["brain-graph.mjs", "brain-query.mjs"]) assert.ok(!/node:/.test(readFileSync(path.join(HERE, "../lib", f), "utf8")), `${f} é puro`);
});

test("interface inteira: sem HTML cru, sem guardar chave, sem recurso externo e sem endpoint novo; mostra as seções da Pasta", () => {
  const pasta = path.join(HERE, "../app/segundo-cerebro");
  const tsx = readdirSync(pasta).filter((f) => f.endsWith(".tsx"));
  assert.ok(tsx.length >= 5);
  for (const f of tsx) {
    const src = readFileSync(path.join(pasta, f), "utf8");
    assert.ok(!/dangerouslySetInnerHTML|innerHTML|localStorage|sessionStorage|document\.cookie|\?token=|searchParams/.test(src), f);
    assert.ok(!/https?:\/\//.test(src), `${f}: sem recurso externo`);
    for (const m of src.matchAll(/fetch\(\s*["'`]([^"'`]+)/g)) assert.equal(m[1], "/api/segundo-cerebro", `${f}: só a API existente`);
    assert.ok(!/method:\s*["'](POST|PUT|PATCH|DELETE)/i.test(src), `${f}: só leitura`);
  }
  const page = readFileSync(path.join(pasta, "page.tsx"), "utf8");
  for (const s of ["<Assuntos", "<Pendencias", "<Decisoes", "<NotasDoDia", "<Reunioes", "<Contextos", "Filtrar por área"]) assert.ok(page.includes(s), s);
  const secoes = readFileSync(path.join(pasta, "Secoes.tsx"), "utf8");
  assert.ok(secoes.includes("Onde parou") && secoes.includes("pendente de validação") && secoes.includes("área: "));
  const rotas = readdirSync(path.join(HERE, "../app/api"), { recursive: true }).map(String).filter((f) => f.endsWith("route.ts"));
  assert.deepEqual(rotas.filter((f) => f.includes("segundo-cerebro")), ["segundo-cerebro/route.ts"], "nenhum endpoint novo do Segundo Cérebro");
});
