// node --test tests/second-brain-full.test.mjs — fontes novas, estados, dono, privacidade, atualização. Só dados fictícios.
import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, rmSync, symlinkSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadSecondBrain, redact, MAX_BYTES } from "../lib/second-brain.mjs";
import { criarFixture, escrever, ficha, rotina, SENTINELA, FORA_DA_LISTA } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-18T12:00:00Z");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const comFixture = async (fn, opts) => { const root = criarFixture(opts); try { await fn(root); } finally { rmSync(root, { recursive: true, force: true }); } };
const hashes = (dir) => Object.fromEntries(readdirSync(dir, { recursive: true }).filter((e) => statSync(path.join(dir, e)).isFile()).map((e) => [e, createHash("sha256").update(readFileSync(path.join(dir, e))).digest("hex")]));
const fonte = (b, id) => b.sources.find((s) => s.id === id);

test("todas as fontes da allowlist entram com proveniência por item e nada fora dela", () => comFixture(async (root) => {
  const antes = hashes(root);
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b.sources.map((s) => [s.id, s.estado]), [["decisoes", "ok"], ["perfil", "ok"], ["fios", "ok"], ["contexto", "ok"], ["rotinas", "ok"], ["projetos", "ok"], ["documentos", "ok"], ["reunioes", "sem_contrato"], ["daily", "sem_contrato"]]);
  assert.deepEqual(b.warnings, []);
  assert.equal(b.contexts.length, 2);
  assert.deepEqual(b.routines.map((r) => [r.id, r.dono]), [["orquestrar-a0-hermes-openclaw", "matheus"], ["melhorias-bom-dia-radar-reunioes-e-candidatos-maps", null]]);
  assert.deepEqual(b.projects.map((p) => p.id), ["meta-nexos"]);
  assert.equal(b.documents.length, 6);
  assert.deepEqual(b.meetings, []);
  assert.deepEqual(b.daily, []);
  for (const lista of [b.decisions, b.threads, b.profile, b.contexts, b.routines, b.projects, b.documents]) {
    for (const item of lista) {
      const p = item.proveniencia;
      assert.ok(p && p.fonte && p.fonteRotulo && p.localizador && p.dono && p.arquivoAtualizadoEm, JSON.stringify(p));
    }
  }
  const json = JSON.stringify(b);
  assert.ok(!json.includes(SENTINELA), "nada de outra pessoa, nem do ruído dos fios");
  assert.ok(!json.includes(FORA_DA_LISTA), "nada fora da allowlist (outro chat, skill não listada, projeto sem dono, não listado)");
  assert.ok(!json.includes(root), "sem caminho absoluto da raiz");
  assert.deepEqual(hashes(root), antes, "nenhuma escrita");
}));

test("ids, vigência, substituição e estado dos fios seguem o contrato", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b.decisions.map((d) => [d.id, d.estadoEfetivo, d.vigente]), [["1", "ativa", true], ["2", "ativa", true], ["3", "substituida", false], ["4", "ativa", true], ["5", "revogada", false]]);
  assert.equal(b.decisions[3].substitui, "3");
  assert.equal(b.decisions[2].substituida_por, "4");
  assert.equal(b.decisions[4].motivo, "mudou de ideia");
  assert.equal(b.decisions[0].proveniencia.localizador, "decisoes[id=1]");
  assert.deepEqual(b.threads.map((f) => [f.id, f.emAberto]), [["a1", true], ["b2", true], ["c3", false], ["d4", true]], "adiado com data vencida volta a contar");
  assert.deepEqual(b.profile.map((f) => f.numero), [1, 2]);
  const r = b.routines[0];
  assert.match(r.versao, /^[0-9a-f]{12}$/, "versão = sha256[:12] como rotinas.hash_de");
  assert.deepEqual(r.passos, ["Ler o arquivo sintético", "Conferir o total"]);
  assert.equal(r.aprovacao, "Antes de enviar qualquer coisa a terceiros.");
  assert.equal(r.verificar, "O total confere com o arquivo.");
  assert.equal(r.entregar, "Resumo de uma linha.");
  assert.deepEqual(r.secoesAusentes, []);
  assert.deepEqual(b.contexts[0].linhas, [1, 4]);
}));

test("dono comprovado: projeto sem dono.txt, de outra pessoa ou fora da lista não aparece; lacuna avisada", () => comFixture(async (root) => {
  escrever(root, "skills/orquestrar-a0-hermes-openclaw/SKILL.md", rotina(SENTINELA, { tags: ["rotina", "fernanda"] }));
  const b = await loadSecondBrain({ root, now: NOW });
  const p = fonte(b, "projetos");
  assert.deepEqual(p.arquivos, [{ chave: "meta-nexos", codigo: "ok" }, { chave: "saude", codigo: "outro_dono" }, { chave: "carreira", codigo: "dono_nao_comprovado" }]);
  assert.equal(p.excluidos, 2);
  assert.ok(b.gaps.some((g) => g.fonte === "projetos" && /dono\.txt/.test(g.motivo)));
  assert.deepEqual(fonte(b, "rotinas").arquivos.map((a) => a.codigo), ["outro_dono", "ok"], "rotina com login de outra pessoa na tag fica de fora");
  assert.ok(!JSON.stringify(b).includes(SENTINELA));
  assert.equal(b.coverage.excluidosPorDono, 3);
}));

test("estados distintos: ausente, link, grande, inválida, formato antigo, vazia e parcial", () => comFixture(async (root) => {
  rmSync(path.join(root, "chats/uMqjehmr/contexto.md"));
  symlinkSync(path.join(root, "chats/outroChat/contexto.md"), path.join(root, "chats/uMqjehmr/contexto.md"));
  writeFileSync(path.join(root, "memoria/usuarios/matheus.md"), "# Perfil antigo\n- texto livre de antes da migração\n");
  writeFileSync(path.join(root, "fios/matheus.json"), JSON.stringify({ fios: [] }));
  writeFileSync(path.join(root, "memoria/decisoes/matheus.json"), "x".repeat(MAX_BYTES + 1));
  writeFileSync(path.join(root, "projects/meta-nexos/.a0proj/project.json"), "{ quebrado");
  rmSync(path.join(root, "workdir/videos"), { recursive: true });
  const b = await loadSecondBrain({ root, now: NOW });
  const estado = (id) => [fonte(b, id).estado, fonte(b, id).codigo];
  assert.deepEqual(estado("contexto"), ["indisponivel", "link"]);
  assert.deepEqual(estado("perfil"), ["indisponivel", "formato_antigo"]);
  assert.deepEqual(estado("fios"), ["vazia", "vazia"]);
  assert.deepEqual(estado("decisoes"), ["indisponivel", "grande"]);
  assert.deepEqual(estado("projetos"), ["indisponivel", "invalida"], "o único projeto com dono tem JSON inválido; os outros não têm dono");
  assert.deepEqual(fonte(b, "projetos").arquivos[0], { chave: "meta-nexos", codigo: "invalida" });
  assert.deepEqual(estado("documentos"), ["ok", "parcial"]);
  assert.deepEqual(b.warnings.map((w) => [w.fonte, w.codigo]), [["decisoes", "grande"], ["perfil", "formato_antigo"], ["contexto", "link"], ["projetos", "invalida"], ["documentos", "parcial"]]);
  assert.equal(b.profile.length, 0, "formato antigo: nada projetado, como o helper");
  assert.ok(!JSON.stringify(b).includes(SENTINELA));
}));

test("link simbólico nas fontes novas é recusado em qualquer nível", () => comFixture(async (root) => {
  rmSync(path.join(root, "skills"), { recursive: true });
  mkdirSync(path.join(root, "outro-lugar/orquestrar-a0-hermes-openclaw"), { recursive: true });
  writeFileSync(path.join(root, "outro-lugar/orquestrar-a0-hermes-openclaw/SKILL.md"), rotina(SENTINELA));
  symlinkSync(path.join(root, "outro-lugar"), path.join(root, "skills"));
  rmSync(path.join(root, "projects/meta-nexos/.a0proj/dono.txt"));
  symlinkSync(path.join(root, "projects/saude/.a0proj/dono.txt"), path.join(root, "projects/meta-nexos/.a0proj/dono.txt"));
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual([fonte(b, "rotinas").estado, fonte(b, "rotinas").codigo], ["indisponivel", "link"]);
  assert.deepEqual(fonte(b, "projetos").arquivos[0], { chave: "meta-nexos", codigo: "link" });
  assert.ok(!JSON.stringify(b).includes(SENTINELA));
}));

test("dados pessoais e segredos são redigidos antes da projeção", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  const json = JSON.stringify(b);
  for (const proibido of ["teste@exemplo.com.br", "98765-4321", "123.456.789-09", "sk-abcdefghijklmnopqrstuvwxyz123", "abc123def456", "segredo123", "naoMostrar123"]) assert.ok(!json.includes(proibido), proibido);
  assert.ok(json.includes("[e-mail removido]") && json.includes("[telefone removido]") && json.includes("[documento removido]"));
  assert.equal(redact("CNPJ 12.345.678/0001-90 cartão 4111 1111 1111 1111"), "CNPJ [documento removido] cartão [número removido]");
  assert.equal(redact("ligue +55 71 98765-4321 ou 71 98765-4321"), "ligue [telefone removido] ou [telefone removido]");
  assert.equal(redact("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"), "[chave privada removida]");
  assert.equal(redact("https://user:pw@host/x"), "https://[removido]@host/x");
  assert.equal(redact("tok AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"), "tok [removido]");
  // Não estraga o que não é segredo: hash hexadecimal minúsculo, número de chamado, data e hora.
  const comum = "sha 46c5d2c372c39377c63b7dc52ce716733be911d5 chamado 34938963 loja 4199543 em 17/10/2026 11:35";
  assert.equal(redact(comum), comum);
}));

test("texto longo é cortado e contado; lista acima do limite vira fonte truncada", () => comFixture(async (root) => {
  const muitas = Array.from({ length: 2001 }, (_, i) => ({ id: i + 1, tema: `t.${i}`, tipo: "decisao", valor: i === 0 ? "v".repeat(5000) : "valor", estado: "ativa", em: 1790000000 }));
  writeFileSync(path.join(root, "memoria/decisoes/matheus.json"), JSON.stringify({ decisoes: muitas }));
  const b = await loadSecondBrain({ root, now: NOW });
  const d = fonte(b, "decisoes");
  assert.deepEqual([d.estado, d.codigo, d.registros], ["ok", "truncada", 2000]);
  assert.ok(d.truncados >= 1);
  assert.ok(b.decisions[0].valor.endsWith("…") && b.decisions[0].valor.length === 4001);
  assert.ok(b.warnings.some((w) => w.fonte === "decisoes" && w.codigo === "truncada"));
}));

test("cada carga relê a fonte: mudança aparece na próxima leitura, com nova impressão", () => comFixture(async (root) => {
  const a = await loadSecondBrain({ root, now: NOW });
  const dados = JSON.parse(readFileSync(path.join(root, "fios/matheus.json"), "utf8"));
  dados.fios.push({ id: "e5", titulo: "Fio novo sintético", estado: "aberto", criado: 1790000600, atualizado: 1790000600 });
  writeFileSync(path.join(root, "fios/matheus.json"), JSON.stringify(dados));
  const b = await loadSecondBrain({ root, now: NOW });
  assert.notEqual(fonte(a, "fios").impressao, fonte(b, "fios").impressao);
  assert.equal(fonte(a, "decisoes").impressao, fonte(b, "decisoes").impressao);
  assert.ok(b.threads.some((f) => f.id === "e5") && !a.threads.some((f) => f.id === "e5"));
}));

test("conflito só com evidência estruturada; assunto parecido não é conflito", () => comFixture(async (root) => {
  const b0 = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b0.conflicts, [], "a1 e c3 falam de lançamento, mas isso não é conflito");
  const d = JSON.parse(readFileSync(path.join(root, "memoria/decisoes/matheus.json"), "utf8"));
  d.decisoes.push({ id: 6, tema: "teste.tom", tipo: "preferencia", valor: "Responder longo", estado: "ativa", em: 1790000500 });
  d.decisoes.push({ id: 7, tema: "teste.x", tipo: "decisao", valor: "Aponta para inexistente", estado: "ativa", substitui: 99 });
  writeFileSync(path.join(root, "memoria/decisoes/matheus.json"), JSON.stringify(d));
  writeFileSync(path.join(root, "memoria/usuarios/matheus.md"), ficha(["Mora numa cidade fictícia", "mora numa cidade FICTÍCIA!"]));
  const b = await loadSecondBrain({ root, now: NOW });
  assert.deepEqual(b.conflicts.map((c) => [c.tipo, c.registros]), [["decisoes_ativas_mesmo_tema", ["decisao:1", "decisao:6"]], ["ficha_entrada_duplicada", ["fato:perfil-1", "fato:perfil-2"]]]);
  assert.ok(b.conflicts.every((c) => c.autoritativo === false && c.regra));
  assert.deepEqual(b.diagnostics.map((x) => x.tipo), ["referencia_quebrada"]);
}));

test("onboarding: 7 seções de negócio e 6 pessoais com estado honesto, nada aprovado nem promovido", () => comFixture(async (root) => {
  const b = await loadSecondBrain({ root, now: NOW });
  const o = b.proposals.onboarding;
  assert.equal(o.negocio.length, 7);
  assert.equal(o.pessoal.length, 6);
  assert.deepEqual(o.negocio.map((x) => x.estado), ["pendente", "pendente", "pendente", "pendente", "pendente", "parcial", "pendente"]);
  assert.deepEqual(o.pessoal.map((x) => x.estado), ["parcial", "pendente", "pendente", "pendente", "parcial", "pendente"]);
  for (const x of [...o.negocio, ...o.pessoal]) {
    assert.equal(x.aprovado, false);
    assert.equal(x.promovido, false);
    for (const ref of x.evidencias) assert.match(ref, /^(rotina|fato|decisao):/);
  }
  assert.deepEqual(o.pessoal[4].evidencias, ["decisao:1", "decisao:2"], "só tipo preferência/permissão/proibição vigente, pelo campo tipo");
}));

test("os módulos novos não gravam nem varrem pastas", () => {
  for (const f of ["second-brain.mjs", "brain-graph.mjs", "brain-query.mjs", "brain-cli.mjs"]) {
    const src = readFileSync(path.join(HERE, "../lib", f), "utf8");
    assert.ok(!/writeFile|appendFile|\bunlink|\brm\(|mkdir|readdir|glob|rename\(/.test(src), f);
  }
  for (const f of ["brain-graph.mjs", "brain-query.mjs"]) assert.ok(!/node:/.test(readFileSync(path.join(HERE, "../lib", f), "utf8")), `${f} é puro (roda no navegador)`);
});

test("interface inteira: sem HTML cru, sem guardar chave, sem recurso externo e sem endpoint novo", () => {
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
  const rotas = readdirSync(path.join(HERE, "../app/api"), { recursive: true }).map(String).filter((f) => f.endsWith("route.ts"));
  assert.deepEqual(rotas.filter((f) => f.includes("segundo-cerebro")), ["segundo-cerebro/route.ts"], "nenhum endpoint novo do Segundo Cérebro");
});
