#!/usr/bin/env node
// Consulta local do Segundo Cérebro, só leitura, sempre sobre as fontes canônicas de /a0/usr (dono fixo matheus).
//   node lib/brain-cli.mjs <funcao> [--fonte F] [--registro tipo:id] [--termo T] [--json | --resumo]
// Cada execução relê as fontes (carga), consulta, monta o roteiro e relê de novo para verificar.
// Não aceita caminho, raiz, dono nem variável de ambiente de dados.
import { pathToFileURL } from "node:url";
import { DEFAULT_DATA_ROOT, loadSecondBrain } from "./second-brain.mjs";
import { FUNCOES, consultar, roteiro, verificar } from "./brain-query.mjs";

const AJUDA = `Uso: node lib/brain-cli.mjs <funcao> [--fonte F] [--registro tipo:id] [--termo T] [--json | --resumo]
Funções: ${Object.keys(FUNCOES).join(", ")}`;

export function lerArgumentos(argv) {
  const [funcao, ...resto] = argv;
  const consulta = { funcao };
  let saida = "texto";
  for (let i = 0; i < resto.length; i++) {
    const a = resto[i];
    if (a === "--json") saida = "json";
    else if (a === "--resumo") saida = "resumo";
    else if (["--fonte", "--registro", "--termo"].includes(a) && i + 1 < resto.length) consulta[a.slice(2)] = resto[++i];
    else return { erro: `Argumento não aceito: ${a}` };
  }
  return { consulta, saida };
}

// `carregar` é injetável só para testes; o CLI usa sempre a raiz fixa.
export async function executarConsulta(consulta, carregar = () => loadSecondBrain({ root: DEFAULT_DATA_ROOT })) {
  const antes = await carregar();
  const resultado = consultar(antes, consulta);
  if (!resultado.ok) return { ok: false, erro: resultado.erro };
  const etapas = roteiro(antes, resultado);
  const verificacao = verificar(resultado, await carregar());
  etapas[etapas.length - 1] = { ...etapas[etapas.length - 1], estado: verificacao.estado, evidencias: verificacao.fontes.map((f) => `${f.id}: ${f.antes ?? "—"} → ${f.depois ?? "—"}${f.igual ? " (igual)" : " (mudou)"}`), detalhe: `${etapas[etapas.length - 1].detalhe} ${verificacao.detalhe}` };
  return { ok: true, resultado, roteiro: etapas, verificacao };
}

export function resumir(r) {
  if (!r.ok) return { ok: false, erro: r.erro };
  return {
    ok: true,
    funcao: r.resultado.consulta.funcao,
    estado: r.resultado.estado,
    itens: r.resultado.itens.length,
    porTipo: r.resultado.itens.reduce((m, i) => ({ ...m, [i.tipo]: (m[i.tipo] ?? 0) + 1 }), {}),
    bloqueios: r.resultado.bloqueios.length,
    proximosPassos: r.resultado.proximosPassos.length,
    aprovacoes: r.roteiro[1].aprovacoes.length,
    etapas: r.roteiro.map((e) => `${e.etapa}:${e.estado}`),
    verificacao: `${r.verificacao.estado} ${r.verificacao.registros.presentes}/${r.verificacao.registros.citados}`,
  };
}

function texto(r) {
  if (!r.ok) return `Erro: ${r.erro}\n${AJUDA}`;
  const x = r.resultado;
  const linhas = [`# ${x.rotulo} — ${x.estado}`, x.resumo, ""];
  for (const i of x.itens) linhas.push(`- [${i.ref}] ${i.rotulo}${i.trecho ? `: ${i.trecho}` : ""}\n  porquê: ${i.porque}${i.proveniencia?.localizador ? ` · origem: ${i.proveniencia.fonteRotulo ?? i.proveniencia.fonte} ${i.proveniencia.localizador}` : ""}`);
  if (x.bloqueios.length) linhas.push("", "Bloqueios:", ...x.bloqueios.map((b) => `- ${b.motivo}`));
  linhas.push("", "Roteiro:");
  for (const e of r.roteiro) {
    linhas.push(`- ${e.etapa}: ${e.estado} — ${e.detalhe}`);
    for (const p of e.proposta ?? []) linhas.push(`    • ${p}`);
    for (const a of e.aprovacoes ?? []) linhas.push(`    aprovação [${a.ref}]: ${a.texto}`);
  }
  return linhas.join("\n");
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const args = lerArgumentos(process.argv.slice(2));
  if (args.erro || !args.consulta.funcao) {
    console.error(args.erro ?? AJUDA);
    process.exitCode = 2;
  } else {
    const r = await executarConsulta(args.consulta);
    if (args.saida === "json") console.log(JSON.stringify(r, null, 2));
    else if (args.saida === "resumo") console.log(JSON.stringify(resumir(r)));
    else console.log(texto(r));
    if (!r.ok) process.exitCode = 2;
  }
}
