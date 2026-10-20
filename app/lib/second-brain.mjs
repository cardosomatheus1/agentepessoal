// Adaptador do Segundo Cérebro (servidor, Node puro, somente leitura). Lê só a Pasta (ADR 0001).
// Uma única identidade fixa (matheus); nenhum caminho vem do pedido; nada é gravado. A Pasta fica em
// <raiz>/segundo_cerebro/pasta e é escrita só pelo agente (infra/vm/plugins/cerebro/helpers/pasta.py). O site só mostra.
// Varredura só nas subpastas fixas abaixo: sem recursão, só *.md, só arquivo regular, sem link simbólico, com teto.

import { createHash, timingSafeEqual } from "node:crypto";
import { constants as FS, promises as fsp } from "node:fs";
import path from "node:path";

export const OWNER = "matheus";
export const DEFAULT_DATA_ROOT = "/a0/usr";
export const PASTA = Object.freeze(["segundo_cerebro", "pasta"]);
export const MAX_BYTES = 1024 * 1024; // por arquivo
export const MAX_ARQUIVOS = 1000; // por subpasta
export const MAX_TOTAL_BYTES = 24 * 1024 * 1024; // por carga, somando todos os arquivos
const MAX_TEXTO_NOTAS = 2_500_000; // caracteres de corpo de nota numa carga (a resposta passa pelo gateway, teto 8 MB)
const IDENTITY_HEADERS = ["x-user", "x-login", "x-tenant"];
const MAX_TEXT = 4000;
const MAX_ITEMS = 2000;

// Contrato lido (estático, sem importar o Python): pasta.py.
// - Decisoes/ Pendencias/ Assuntos/: um arquivo por item, cabeçalho "---" com linhas `chave: <valor JSON>` (os dados)
//   e corpo Markdown gerado a partir deles; indice.md é índice; `status` e `tags` são derivados (nunca lidos).
//   Item ilegível é erro (o helper recusa a coleção), nunca "não tem nada".
// - Contexto/: organizacao, marca, estrategia, cliente-ideal, pessoas-chave, perfil; "[PENDENTE DE VALIDAÇÃO]" no
//   texto = ainda não validado. perfil.md é a ficha (ficha.py): a MARCA nas 400 primeiras letras e uma entrada "- ".
// - Reunioes/ Notas-do-dia/ (AAAA-MM-DD.md) Documentos/ Projetos/: notas livres, cabeçalho opcional.
// - Arquivo-morto/: o que saiu. Nunca é lido nem mostrado; link para ele não vira nó.
// - Ligações: `liga` = ["decisao:35", "pendencia:ab12cd", "assunto:x1y2z3"]; no texto, [[Pasta/arquivo]].
export const FICHA_MARCA = "Mantida pela ferramenta `ficha`";
export const PENDENTE = "[PENDENTE DE VALIDAÇÃO]";
export const MARCA_MIGRADO = ".migrado";
const DERIVADOS = ["status", "tags"];
export const CONTEXTO = Object.freeze([
  ["organizacao", "Organização"],
  ["marca", "Marca e voz"],
  ["estrategia", "Estratégia"],
  ["cliente-ideal", "Cliente ideal"],
  ["pessoas-chave", "Pessoas-chave"],
  ["perfil", "Perfil do Matheus"],
]);
export const OCULTA = "Arquivo-morto";

const p = (...x) => [...PASTA, ...x];
export const SOURCES = Object.freeze({
  regras: { id: "regras", rotulo: "Regras da Pasta (CLAUDE.md)", partes: p("CLAUDE.md"), pasta: "" },
  contexto: { id: "contexto", rotulo: "Contexto", partes: p("Contexto"), pasta: "Contexto" },
  perfil: { id: "perfil", rotulo: "Perfil (ficha)", partes: p("Contexto", "perfil.md"), pasta: "Contexto" },
  decisoes: { id: "decisoes", rotulo: "Decisões", partes: p("Decisoes"), pasta: "Decisoes", tipo: "decisao" },
  pendencias: { id: "pendencias", rotulo: "Pendências", partes: p("Pendencias"), pasta: "Pendencias", tipo: "pendencia" },
  assuntos: { id: "assuntos", rotulo: "Assuntos", partes: p("Assuntos"), pasta: "Assuntos", tipo: "assunto" },
  reunioes: { id: "reunioes", rotulo: "Reuniões", partes: p("Reunioes"), pasta: "Reunioes", tipo: "reuniao" },
  notas: { id: "notas", rotulo: "Notas do dia", partes: p("Notas-do-dia"), pasta: "Notas-do-dia", tipo: "nota" },
  documentos: { id: "documentos", rotulo: "Documentos", partes: p("Documentos"), pasta: "Documentos", tipo: "documento" },
  projetos: { id: "projetos", rotulo: "Projetos", partes: p("Projetos"), pasta: "Projetos", tipo: "projeto" },
});

export const SECURITY_HEADERS = Object.freeze({
  "Cache-Control": "private, no-store",
  Vary: "Authorization",
  "X-Content-Type-Options": "nosniff",
  "Content-Type": "application/json; charset=utf-8",
});

// ---------- redação de segredos e dados pessoais ----------

const SECRET_PATTERNS = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)/g, "[chave privada removida]"],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, "Bearer [removido]"],
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g, "[removido]"],
  [/\bsk-[A-Za-z0-9_-]{16,}/g, "[removido]"],
  [/\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, "[removido]"],
  [/\bgh[pousr]_[A-Za-z0-9]{20,}/g, "[removido]"],
  [/\bxox[abprs]-[A-Za-z0-9-]{10,}/g, "[removido]"],
  [/\bAIza[0-9A-Za-z_-]{30,}/g, "[removido]"],
  [/([?&](?:token|key|apikey|api_key|access_token|secret|sig|signature|password|senha|code)=)[^&\s#]+/gi, "$1[removido]"],
  [/(\b(?:https?|ftp):\/\/)[^\s/:@]+:[^\s/@]+@/gi, "$1[removido]@"],
  [
    /\b(senha|password|passwd|pwd|token|secret|segredo|api[_ -]?key|chave(?:[_ -]de)?[_ -]?api|access[_ -]?key)(\s*[:=]\s*)("[^"]*"|'[^']*'|\S+)/gi,
    "$1$2[removido]",
  ],
  // Token genérico: 32+ caracteres com maiúscula, minúscula e dígito (um hash hexadecimal minúsculo fica).
  [/\b(?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*[a-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{32,}\b/g, "[removido]"],
  [/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[e-mail removido]"],
  [/\b\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}\b/g, "[documento removido]"],
  [/\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/g, "[documento removido]"],
  [/(?:\+\d{1,3}[\s.-]?)\(?\d{2,3}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}\b/g, "[telefone removido]"],
  [/\(\d{2}\)\s?9?\d{4}[\s.-]?\d{4}\b/g, "[telefone removido]"],
  [/\b\d{2}[\s.-]9\d{4}[\s.-]\d{4}\b/g, "[telefone removido]"],
  [/\b(?:\d[ -]?){13,19}\b/g, "[número removido]"],
  [/\b\d{11}\b/g, "[número removido]"],
];

export function redact(value) {
  let s = String(value);
  for (const [re, rep] of SECRET_PATTERNS) s = s.replace(re, rep);
  return s;
}

// Texto pronto para projeção: redigido, aparado e com o corte marcado em `cortes`.
function texto(v, max = MAX_TEXT, cortes) {
  if (v === null || v === undefined) return null;
  if (typeof v !== "string" && typeof v !== "number" && typeof v !== "boolean") return null;
  const s = redact(String(v)).trim();
  if (!s) return null;
  if (s.length > max) {
    if (cortes) cortes.n++;
    return s.slice(0, max) + "…";
  }
  return s;
}
const text = (v, max = MAX_TEXT) => texto(v, max);

function textList(v, cortes) {
  if (v === null || v === undefined) return [];
  const arr = Array.isArray(v) ? v : [v];
  return arr.slice(0, 50).map((x) => texto(x, 500, cortes)).filter(Boolean);
}

function dateText(v) {
  if (typeof v === "number" && Number.isFinite(v)) {
    const d = new Date(v * 1000);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }
  const s = text(v, 40);
  if (!s) return null;
  return Number.isNaN(Date.parse(s)) ? null : s;
}

const impressao = (conteudo) => createHash("sha256").update(conteudo, "utf8").digest("hex").slice(0, 16);
const area = (v) => text(v, 80) ?? "geral";

// ---------- leitura segura ----------

// Cada nível abaixo da raiz (e a própria raiz) tem que ser diretório de verdade, nunca link simbólico.
async function checarDiretorios(root, partes) {
  let ancestor = path.parse(root).root;
  for (const segment of root.slice(ancestor.length).split(path.sep).filter(Boolean)) {
    ancestor = path.join(ancestor, segment);
    try {
      const st = await fsp.lstat(ancestor);
      if (st.isSymbolicLink()) return "link";
      if (!st.isDirectory()) return "erro";
    } catch { return "ausente"; }
  }
  let atual = root;
  for (const parte of partes) {
    atual = path.join(atual, parte);
    let st;
    try {
      st = await fsp.lstat(atual);
    } catch (e) {
      if (e && (e.code === "ENOENT" || e.code === "ENOTDIR")) return "ausente";
      return "erro";
    }
    if (st.isSymbolicLink()) return "link";
    if (!st.isDirectory()) return "ausente";
  }
  return "ok";
}

async function readFixed(root, partes) {
  const dirs = await checarDiretorios(root, partes.slice(0, -1));
  if (dirs !== "ok") return { status: dirs };
  const atual = path.join(root, ...partes);
  try {
    if ((await fsp.lstat(atual)).isSymbolicLink()) return { status: "link" };
  } catch (e) {
    if (e && (e.code === "ENOENT" || e.code === "ENOTDIR")) return { status: "ausente" };
    return { status: "erro" };
  }
  let fh;
  try {
    fh = await fsp.open(atual, FS.O_RDONLY | (FS.O_NOFOLLOW ?? 0));
  } catch (e) {
    if (e && e.code === "ELOOP") return { status: "link" };
    if (e && e.code === "ENOENT") return { status: "ausente" };
    return { status: "erro" };
  }
  try {
    const st = await fh.stat();
    if (!st.isFile()) return { status: "erro" };
    if (st.size > MAX_BYTES) return { status: "grande" };
    const buf = Buffer.alloc(Math.min(MAX_BYTES + 1, st.size + 1));
    const { bytesRead } = await fh.read(buf, 0, buf.length, 0);
    if (bytesRead > MAX_BYTES) return { status: "grande" };
    return { status: "ok", conteudo: buf.subarray(0, bytesRead).toString("utf8"), mtime: st.mtime.toISOString(), bytes: bytesRead };
  } catch {
    return { status: "erro" };
  } finally {
    await fh.close().catch(() => {});
  }
}

// A única varredura: os nomes de uma subpasta fixa da Pasta. Sem recursão; só *.md que não começam com "." e não são
// o índice; entrada que é link simbólico é recusada (anotada), subpasta e outros tipos são ignorados.
async function listarPasta(root, partes) {
  const dirs = await checarDiretorios(root, partes);
  if (dirs !== "ok") return { status: dirs };
  let entradas;
  try {
    entradas = await fsp.readdir(path.join(root, ...partes), { withFileTypes: true });
  } catch (e) {
    return { status: e && e.code === "ENOENT" ? "ausente" : "erro" };
  }
  const nomes = [];
  const recusados = [];
  for (const e of entradas) {
    const n = e.name;
    if (!n.endsWith(".md") || n.startsWith(".") || n === "indice.md" || /[\u0000-\u001f/\\]/.test(n)) continue;
    if (e.isSymbolicLink()) { recusados.push(n); continue; }
    if (e.isFile()) nomes.push(n);
  }
  nomes.sort();
  return { status: "ok", nomes: nomes.slice(0, MAX_ARQUIVOS), excedeu: nomes.length > MAX_ARQUIVOS, recusados: recusados.sort() };
}

const AVISOS = {
  ausente: "Fonte indisponível: não encontrada na Pasta.",
  link: "Fonte recusada: é um link simbólico.",
  grande: "Fonte recusada: arquivo maior que 1 MB.",
  erro: "Fonte indisponível: não foi possível ler.",
  invalida: "Fonte indisponível: conteúdo em formato inválido.",
  ilegivel: "Coleção com item ilegível ou recusado: os itens legíveis aparecem, mas a lista NÃO está completa (o agente também não grava nesta coleção até alguém corrigir o arquivo).",
  formato_antigo: "Ficha no formato antigo (texto livre): o helper da ficha recusa ler entradas até o operador migrar.",
  truncada: "Fonte lida em parte: mais arquivos ou registros que o limite de leitura; os excedentes não aparecem.",
  parcial: "Fonte lida em parte: alguns arquivos não puderam ser lidos.",
  orcamento: "Fonte não lida: a carga passou do limite total de leitura.",
};
const SEM_AVISO = ["ok", "vazia", "pendente"];

// ---------- formato da Pasta ----------

export class Ilegivel extends Error {}

// Espelho de pasta.ler_frontmatter: começa com "---\n", fecha em "\n---\n", cada linha `chave: <JSON>`.
// Qualquer desvio é Ilegivel (nunca "sem dados"). `status`/`tags` são derivados e saem.
export function parseFrontmatter(conteudo, nome = "") {
  if (typeof conteudo !== "string" || !conteudo.startsWith("---\n")) throw new Ilegivel(`${nome}: sem cabeçalho`);
  const fim = conteudo.indexOf("\n---\n", 4);
  if (fim < 0) throw new Ilegivel(`${nome}: cabeçalho sem fim`);
  const campos = Object.create(null);
  for (const linha of conteudo.slice(4, fim).split("\n")) {
    if (!linha.trim()) continue;
    const i = linha.indexOf(": ");
    if (i < 0) throw new Ilegivel(`${nome}: linha sem valor`);
    const chave = linha.slice(0, i).trim();
    let valor;
    try { valor = JSON.parse(linha.slice(i + 2)); } catch { throw new Ilegivel(`${nome}: valor ilegível em ${chave}`); }
    if (["__proto__", "constructor", "prototype"].includes(chave)) continue;
    campos[chave] = valor;
  }
  for (const k of DERIVADOS) delete campos[k];
  return { campos, corpo: conteudo.slice(fim + 5) };
}

// Nota livre: cabeçalho opcional; se existe, tem que estar no formato (senão a nota é ilegível).
function cabecalhoOpcional(conteudo, nome) {
  return conteudo.startsWith("---\n") ? parseFrontmatter(conteudo, nome) : { campos: Object.create(null), corpo: conteudo };
}

// [[Pasta/arquivo]], [[Pasta/arquivo|apelido]], [[Pasta/arquivo#seção]] -> "Pasta/arquivo".
export function wikiLinks(conteudo) {
  const out = new Set();
  for (const m of String(conteudo ?? "").matchAll(/\[\[([^\]\n|#]{1,200})(?:[|#][^\]\n]*)?\]\]/g)) {
    const alvo = m[1].trim().replace(/^\.?\//, "").replace(/\.md$/i, "");
    if (alvo) out.add(alvo);
    if (out.size >= 200) break;
  }
  return [...out];
}

const TIPOS_REF = ["decisao", "pendencia", "assunto", "contexto", "reuniao", "nota", "documento", "projeto"];
const REF = new RegExp(`^(${TIPOS_REF.join("|")}):[^\\u0000-\\u001f]{1,120}$`);
function refs(v) {
  if (!Array.isArray(v)) return [];
  return [...new Set(v.slice(0, 50).filter((r) => typeof r === "string" || typeof r === "number").map((r) => String(r).trim()).filter((r) => REF.test(r)))];
}

const oculto = (alvo) => alvo.replace(/^\/+/, "").split("/")[0].toLowerCase() === OCULTA.toLowerCase();

// ---------- normalização (os mesmos formatos de antes, agora alimentados pela Pasta) ----------

function provenance(src, extra) {
  return { fonte: src.id, fonteRotulo: src.rotulo, dono: OWNER, ...extra };
}

export function normalizeDecisions(data, src, mtime, now, cortes = { n: 0 }) {
  if (!data || typeof data !== "object" || !Array.isArray(data.decisoes)) return null;
  const agora = now.getTime();
  return data.decisoes
    .slice(0, MAX_ITEMS)
    .filter((d) => d && typeof d === "object" && !Array.isArray(d))
    .map((d, i) => {
      const valido_ate = dateText(d.valido_ate);
      const estado = text(d.estado, 40) ?? "desconhecida";
      const expirou = valido_ate !== null && Date.parse(valido_ate) < agora;
      const estadoEfetivo = expirou ? "expirada" : estado.toLowerCase();
      const id = text(d.id, 120) ?? `decisao-${i + 1}`;
      return {
        id,
        tema: texto(d.tema, 300, cortes),
        tipo: text(d.tipo, 60),
        valor: texto(d.valor, MAX_TEXT, cortes),
        citacao: texto(d.citacao, MAX_TEXT, cortes),
        origem: texto(d.origem, 300, cortes),
        por: text(d.por, 120),
        em: dateText(d.em),
        estado,
        valido_ate,
        estadoEfetivo,
        vigente: estadoEfetivo === "ativa",
        fim_em: dateText(d.fim_em),
        substitui: text(d.substitui, 120),
        substituida_por: text(d.substituida_por, 120),
        motivo: texto(d.motivo, 300, cortes),
        proveniencia: provenance(src, { localizador: `decisoes[id=${id}]`, citacao: texto(d.citacao, MAX_TEXT), origem: text(d.origem, 300), em: dateText(d.em), arquivoAtualizadoEm: mtime }),
      };
    });
}

function normalizeLinks(v) {
  if (typeof v === "string") v = v.trim() ? [v] : [];
  if (!Array.isArray(v)) return [];
  const out = [];
  for (const l of v.slice(0, 100)) {
    if (typeof l === "string" || typeof l === "number") {
      const alvo = text(l, 300);
      if (alvo) out.push({ alvo, rotulo: null });
    } else if (l && typeof l === "object" && !Array.isArray(l)) {
      const alvo = text(l.id ?? l.para ?? l.alvo ?? l.fio, 300);
      if (alvo) out.push({ alvo, rotulo: text(l.rotulo ?? l.motivo ?? l.tipo, 200) });
    }
  }
  return out;
}

// Pendências (antigos fios): mesma regra de "em aberto" do fios.abertos().
export function normalizeThreads(data, src, mtime, now = new Date(), cortes = { n: 0 }) {
  if (!data || typeof data !== "object" || !Array.isArray(data.fios)) return null;
  const hoje = now.toISOString().slice(0, 10);
  return data.fios
    .slice(0, MAX_ITEMS)
    .filter((f) => f && typeof f === "object" && !Array.isArray(f))
    .map((f, i) => {
      const id = text(f.id, 120) ?? `pendencia-${i + 1}`;
      const estado = text(f.estado, 40);
      const adiar_ate = text(f.adiar_ate, 40);
      const emAberto = (estado ?? "aberto") === "aberto" || (estado === "adiado" && !!adiar_ate && adiar_ate <= hoje);
      return {
        id,
        titulo: texto(f.titulo, 300, cortes),
        detalhe: texto(f.detalhe, MAX_TEXT, cortes),
        fontes: textList(f.fontes, cortes),
        dono: text(f.dono, 80),
        prazo: dateText(f.prazo),
        prioridade: text(f.prioridade, 40),
        proximo_passo: texto(f.proximo_passo, 1000, cortes),
        ligacoes: normalizeLinks(f.ligacoes),
        estado,
        adiar_ate,
        emAberto,
        criado: dateText(f.criado),
        atualizado: dateText(f.atualizado),
        proveniencia: provenance(src, { localizador: `pendencias[id=${id}]`, em: dateText(f.atualizado) ?? dateText(f.criado), arquivoAtualizadoEm: mtime }),
      };
    });
}

// Assunto: tema em discussão com onde parou (assuntos.py: andamento | parado | encerrado).
export function normalizeSubject(a, src, mtime, cortes = { n: 0 }) {
  if (!a || typeof a !== "object" || Array.isArray(a)) return null;
  const id = text(a.id, 120);
  if (!id) return null;
  const estado = (text(a.estado, 40) ?? "andamento").toLowerCase();
  const historico = (Array.isArray(a.historico) ? a.historico : []).slice(-30)
    .filter((h) => h && typeof h === "object" && !Array.isArray(h))
    .map((h) => ({ em: dateText(h.em), nota: texto(h.nota, 600, cortes) }))
    .filter((h) => h.nota);
  return {
    id,
    titulo: texto(a.titulo, 300, cortes) ?? id,
    onde_parou: texto(a.onde_parou, 1500, cortes),
    estado,
    emAndamento: estado !== "encerrado",
    citacao: texto(a.citacao, 1000, cortes),
    origem: texto(a.origem, 300, cortes),
    criado: dateText(a.criado),
    atualizado: dateText(a.atualizado),
    historico,
    proveniencia: provenance(src, { localizador: `assuntos[id=${id}]`, em: dateText(a.atualizado) ?? dateText(a.criado), arquivoAtualizadoEm: mtime }),
  };
}

// Ficha: só o formato do helper (MARCA no topo, entradas "- "). Sem MARCA e com o marcador de pendente: a entrevista
// ainda não preencheu o perfil. Sem MARCA e sem marcador: formato antigo (o helper recusa ler).
export function normalizeProfile(md, src, mtime, cortes = { n: 0 }) {
  if (!md.slice(0, 400).includes(FICHA_MARCA)) return md.includes(PENDENTE) ? { pendente: true, fatos: [] } : { formatoAntigo: true, fatos: [] };
  const fatos = [];
  md.split(/\r?\n/).forEach((linha, idx) => {
    if (!linha.startsWith("- ") || fatos.length >= MAX_ITEMS) return;
    const t = texto(linha.slice(2).replace(/\s+/g, " "), 1000, cortes);
    if (!t) return;
    const numero = fatos.length + 1;
    fatos.push({ id: `perfil-${numero}`, numero, texto: t, area: "pessoal", proveniencia: provenance(src, { localizador: `Contexto/perfil.md entrada ${numero} (linha ${idx + 1})`, linha: idx + 1, arquivoAtualizadoEm: mtime }) });
  });
  return { formatoAntigo: false, fatos };
}

// Corpo Markdown -> título (# ) e seções (## …) com itens de texto. Orçamento da carga inteira para a resposta caber no gateway.
function secoesDe(corpo, cortes, orcamento) {
  let titulo = null;
  const secoes = [];
  let atual = null;
  let linhaN = 0;
  for (const linha of corpo.split(/\r?\n/)) {
    linhaN++;
    const h = /^(#{1,4})\s+(.+)$/.exec(linha);
    if (h) {
      if (h[1] === "#" && titulo === null) { titulo = texto(h[2], 200, cortes); continue; }
      if (secoes.length >= 80) break;
      atual = { titulo: texto(h[2], 200, cortes), linha: linhaN, itens: [] };
      secoes.push(atual);
      continue;
    }
    const limpo = linha.replace(/^\s*(?:[-*]\s+|>\s?)/, "");
    if (!limpo.trim() || limpo.trim() === PENDENTE) continue;
    if (!atual) { atual = { titulo: null, linha: linhaN, itens: [] }; secoes.push(atual); }
    if (atual.itens.length >= 200) continue;
    if (orcamento.texto <= 0) { cortes.n++; continue; }
    const t = texto(limpo, 1200, cortes);
    if (t) { atual.itens.push(t); orcamento.texto -= t.length; }
  }
  return { titulo, secoes: secoes.filter((s) => s.titulo || s.itens.length) };
}

const DATA = /^(\d{4}-\d{2}-\d{2})/;

// Nota livre (Reuniões, Notas do dia, Documentos, Projetos, Contexto).
export function normalizeNote(nome, conteudo, src, mtime, cortes = { n: 0 }, orcamento = { texto: MAX_TEXTO_NOTAS }) {
  const { campos, corpo } = cabecalhoOpcional(conteudo, nome);
  const stem = nome.replace(/\.md$/, "");
  const { titulo, secoes } = secoesDe(corpo, cortes, orcamento);
  const primeiro = secoes.flatMap((s) => s.itens)[0] ?? null;
  return {
    id: text(stem, 200),
    titulo: texto(campos.titulo, 300, cortes) ?? titulo ?? text(stem, 200),
    data: dateText(campos.data) ?? dateText(campos.em) ?? (DATA.exec(stem)?.[1] ?? null),
    area: area(campos.area),
    resumo: primeiro ? primeiro.slice(0, 300) : null,
    secoes,
    pendente: conteudo.includes(PENDENTE),
    bytes: Buffer.byteLength(conteudo, "utf8"),
    linhas: conteudo.split(/\r?\n/).length,
    sha256: createHash("sha256").update(conteudo, "utf8").digest("hex"),
    proveniencia: provenance(src, { localizador: `${src.pasta}/${nome}`, em: dateText(campos.em) ?? null, arquivoAtualizadoEm: mtime }),
    _campos: campos,
  };
}

// Regras e mapa da Pasta (CLAUDE.md): só os itens numerados de "## Regras".
export function normalizeRules(md, src, mtime, cortes = { n: 0 }) {
  const regras = [];
  let dentro = false;
  for (const linha of md.split(/\r?\n/)) {
    if (/^##\s+/.test(linha)) { dentro = /^##\s+Regras/i.test(linha); continue; }
    if (!dentro) continue;
    const m = /^\d+[.)]\s+(.+)$/.exec(linha);
    if (m) regras.push(m[1].trim());
    else if (/^\s+\S/.test(linha) && regras.length) regras[regras.length - 1] += ` ${linha.trim()}`;
  }
  return {
    titulo: texto(/^# (.+)$/m.exec(md)?.[1] ?? "Segundo Cérebro", 200, cortes),
    regras: regras.slice(0, 50).map((r) => texto(r, 1000, cortes)).filter(Boolean),
    proveniencia: provenance(src, { localizador: "CLAUDE.md", arquivoAtualizadoEm: mtime }),
  };
}

// ---------- ligações: `liga` + [[links]] (+ o texto livre de ligação das pendências) ----------

// Cada aresta tem origem num campo gravado. Destino que não está na Pasta vira referência textual (nunca inferida);
// destino no Arquivo-morto é omitido (e contado). Duplicatas do mesmo par se fundem com todas as vias.
export function buildLinks(itens) {
  const porRef = new Map(itens.map((i) => [i.ref, i]));
  const porNota = new Map();
  const porStem = new Map();
  for (const i of itens) {
    if (!i._nota) continue;
    porNota.set(i._nota, i.ref);
    const stem = i._nota.split("/").pop();
    porStem.set(stem, porStem.has(stem) ? null : i.ref);
  }
  const porPendencia = new Map(itens.filter((i) => i._tipo === "pendencia").map((i) => [i.id, i.ref]));
  const substituicao = new Set();
  for (const d of itens.filter((i) => i._tipo === "decisao")) {
    for (const outro of [d.substitui, d.substituida_por]) if (outro) { substituicao.add(`${d.ref}|decisao:${outro}`); substituicao.add(`decisao:${outro}|${d.ref}`); }
  }
  const arestas = new Map();
  let ocultas = 0;
  const add = (i, para, via, alvo, resolvido) => {
    if (para === i.ref) return;
    if (via === "wiki" && substituicao.has(`${i.ref}|${para}`)) return; // o corpo da decisão repete substitui/substituída
    const k = `${i.ref}|${para}`;
    const e = arestas.get(k);
    if (e) { if (!e.vias.includes(via)) e.vias.push(via); return; }
    arestas.set(k, { de: i.ref, para, vias: [via], alvo: text(alvo, 300), resolvido, evidencia: { fonte: i.proveniencia.fonte, registro: i.id, campo: via === "wiki" ? "[[link]] no texto" : via, localizador: i.proveniencia.localizador ?? null } });
  };
  for (const i of itens) {
    for (const r of i.liga ?? []) {
      if (porRef.has(r)) add(i, r, "liga", r, true);
      else add(i, `referencia:${r}`, "liga", r, false);
    }
    for (const w of i._wiki ?? []) {
      if (oculto(w)) { ocultas++; continue; }
      const alvo = porNota.get(w) ?? (w.includes("/") ? undefined : porStem.get(w) ?? undefined);
      if (alvo) add(i, alvo, "wiki", w, true);
      else add(i, `referencia:${w}`, "wiki", w, false);
    }
    for (const l of i.ligacoes ?? []) {
      const alvo = porPendencia.get(l.alvo);
      if (alvo) add(i, alvo, "ligacoes", l.alvo, true);
      else add(i, `referencia:${l.alvo}`, "ligacoes", l.alvo, false);
    }
  }
  return { links: [...arestas.values()], ocultas };
}

// Visão compacta (de/para/rotulo) das ligações, para o mapa simples de conexões.
export function buildConnections(links, rotulos = new Map()) {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) {
      const [tipo, ...resto] = id.split(":");
      nodes.set(id, { id, tipo: tipo === "referencia" ? "texto" : tipo, rotulo: rotulos.get(id) ?? text(resto.join(":"), 300) ?? id });
    }
  };
  const edges = [];
  for (const l of links) {
    node(l.de); node(l.para);
    edges.push({ de: l.de, para: l.para, rotulo: l.vias.join(" + "), evidencia: { fonte: l.evidencia.fonte, registro: l.evidencia.registro, campo: l.evidencia.campo } });
  }
  return { nodes: [...nodes.values()], edges };
}

// ---------- diagnósticos (não autoritativos) ----------

const chaveTexto = (s) => String(s ?? "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9@]+/g, " ").trim();

// Só invariantes explícitos dos contratos: nunca semelhança de palavras entre registros diferentes.
export function diagnose({ decisions, threads, subjects = [], profile, links = [] }) {
  const conflitos = [];
  const diagnosticos = [];
  const porTema = new Map();
  for (const d of decisions) if (d.vigente && d.tema) porTema.set(d.tema, [...(porTema.get(d.tema) ?? []), d.id]);
  for (const [tema, ids] of porTema) {
    if (ids.length > 1) conflitos.push({ tipo: "decisoes_ativas_mesmo_tema", fonte: "decisoes", registros: ids.map((id) => `decisao:${id}`), regra: "decisoes.py: uma decisão ativa por tema", detalhe: `${ids.length} decisões vigentes no tema "${tema}"`, autoritativo: false });
  }
  const idsDecisao = new Set(decisions.map((d) => d.id));
  for (const d of decisions) {
    for (const campo of ["substitui", "substituida_por"]) {
      if (d[campo] && !idsDecisao.has(d[campo])) diagnosticos.push({ tipo: "referencia_quebrada", fonte: "decisoes", registros: [`decisao:${d.id}`], regra: `campo ${campo} aponta para decisão inexistente`, detalhe: `${campo} = ${d[campo]}`, autoritativo: false });
    }
  }
  const vistos = new Map();
  for (const f of profile) {
    const k = chaveTexto(f.texto);
    if (vistos.has(k)) conflitos.push({ tipo: "ficha_entrada_duplicada", fonte: "perfil", registros: [`fato:${vistos.get(k)}`, `fato:${f.id}`], regra: "ficha.py: sem entradas duplicadas", detalhe: "duas entradas com o mesmo texto normalizado", autoritativo: false });
    else vistos.set(k, f.id);
  }
  for (const [lista, tipo, fonte] of [[threads, "pendencia", "pendencias"], [subjects, "assunto", "assuntos"], [decisions, "decisao", "decisoes"]]) {
    const ids = new Map();
    for (const t of lista) ids.set(t.id, (ids.get(t.id) ?? 0) + 1);
    for (const [id, n] of ids) if (n > 1) conflitos.push({ tipo: `${tipo}_id_repetido`, fonte, registros: [`${tipo}:${id}`], regra: "pasta.py: id único por item da coleção", detalhe: `${n} arquivos com o mesmo id`, autoritativo: false });
  }
  for (const l of links) {
    if (l.resolvido || !l.vias.includes("liga")) continue;
    diagnosticos.push({ tipo: "liga_quebrada", fonte: l.evidencia.fonte, registros: [l.de], regra: "liga aponta para item que não está na Pasta", detalhe: `liga = ${l.alvo}`, autoritativo: false });
  }
  return { conflitos, diagnosticos };
}

// ---------- carga ----------

const vazioOuOk = (n) => (n === 0 ? "vazia" : "ok");
const decrescente = (a, b) => String(b.data ?? "").localeCompare(String(a.data ?? "")) || String(b.id).localeCompare(String(a.id));

export async function loadSecondBrain({ root, now = new Date() }) {
  const warnings = [];
  const sources = [];
  const res = { decisions: [], threads: [], subjects: [], profile: [], contexts: [], meetings: [], daily: [], documents: [], projects: [] };
  const orcamento = { bytes: MAX_TOTAL_BYTES, texto: MAX_TEXTO_NOTAS };
  let rules = null;

  function registrar(src, extra) {
    const s = { id: src.id, rotulo: src.rotulo, dono: OWNER, localizador: src.partes.join("/"), arquivoAtualizadoEm: null, registros: 0, excluidos: 0, truncados: 0, impressao: null, arquivos: [], ...extra };
    s.estado = s.codigo === "pendente" ? "vazia" : ["ok", "vazia"].includes(s.codigo) ? s.codigo : ["truncada", "parcial"].includes(s.codigo) ? "ok" : "indisponivel";
    sources.push(s);
    if (!SEM_AVISO.includes(s.codigo)) {
      const quais = s.arquivos.filter((a) => a.codigo !== "ok").slice(0, 5).map((a) => `${a.chave} (${a.codigo})`);
      warnings.push({ fonte: src.id, codigo: s.codigo, mensagem: `${src.rotulo}: ${AVISOS[s.codigo]}${quais.length ? ` Arquivos: ${quais.join(", ")}.` : ""}` });
    }
    return s;
  }

  async function ler(partes) {
    if (orcamento.bytes <= 0) return { status: "orcamento" };
    const r = await readFixed(root, partes);
    if (r.status === "ok") orcamento.bytes -= r.bytes;
    return r;
  }

  // Marca da migração única (pasta.ativa): sem ela o agente ainda grava nos registros antigos.
  const marca = await readFixed(root, p(MARCA_MIGRADO));
  const migrada = marca.status === "ok";

  // CLAUDE.md
  {
    const src = SOURCES.regras;
    const r = await ler(src.partes);
    if (r.status !== "ok") registrar(src, { codigo: r.status === "orcamento" ? "truncada" : r.status });
    else {
      const cortes = { n: 0 };
      rules = normalizeRules(r.conteudo, src, r.mtime, cortes);
      registrar(src, { codigo: vazioOuOk(rules.regras.length), arquivoAtualizadoEm: r.mtime, registros: rules.regras.length, truncados: cortes.n, impressao: impressao(r.conteudo) });
    }
  }

  // Contexto: as seis seções fixas (nada de varrer a pasta). perfil.md também é a ficha.
  {
    const src = SOURCES.contexto;
    const arquivos = [];
    const cortes = { n: 0 };
    const hash = createHash("sha256");
    let ultimo = null;
    let perfilBruto = null;
    for (const [id, titulo] of CONTEXTO) {
      const nome = `${id}.md`;
      const r = await ler([...src.partes, nome]);
      if (r.status !== "ok") { arquivos.push({ chave: nome, codigo: r.status }); continue; }
      hash.update(`${nome}\0${r.conteudo}\0`);
      if (!ultimo || r.mtime > ultimo) ultimo = r.mtime;
      let n;
      try { n = normalizeNote(nome, r.conteudo, src, r.mtime, cortes, orcamento); } catch { arquivos.push({ chave: nome, codigo: "ilegivel" }); continue; }
      const c = n._campos;
      if (id === "perfil") { perfilBruto = r; n.secoes = []; n.resumo = "Os fatos da ficha aparecem em Perfil."; }
      res.contexts.push({
        id, titulo: n.titulo ?? titulo, rotulo: titulo, estado: n.pendente ? "pendente" : "validado", area: "geral", secoes: n.secoes, resumo: n.resumo,
        aprovado: texto(c.aprovado, 200, cortes), validadoEm: dateText(c.em), _nota: `Contexto/${id}`, _wiki: wikiLinks(r.conteudo),
        proveniencia: n.proveniencia,
      });
      arquivos.push({ chave: nome, codigo: "ok" });
    }
    const oks = arquivos.filter((a) => a.codigo === "ok").length;
    const falhas = arquivos.filter((a) => a.codigo !== "ok");
    const codigo = falhas.length && !oks ? (falhas.every((f) => f.codigo === falhas[0].codigo) ? falhas[0].codigo : "erro") : falhas.length ? "parcial" : vazioOuOk(oks);
    registrar(src, { codigo, arquivoAtualizadoEm: ultimo, registros: res.contexts.length, truncados: cortes.n, impressao: ultimo ? hash.digest("hex").slice(0, 16) : null, arquivos: falhas });

    const ps = SOURCES.perfil;
    const pr = perfilBruto ?? { status: arquivos.find((a) => a.chave === "perfil.md")?.codigo ?? "ausente" };
    if (pr.status !== "ok") registrar(ps, { codigo: pr.status === "orcamento" ? "truncada" : pr.status });
    else {
      const k = { n: 0 };
      const x = normalizeProfile(pr.conteudo, ps, pr.mtime, k);
      const extra = { arquivoAtualizadoEm: pr.mtime, impressao: impressao(pr.conteudo) };
      if (x.formatoAntigo) registrar(ps, { codigo: "formato_antigo", ...extra });
      else if (x.pendente) registrar(ps, { codigo: "pendente", ...extra });
      else {
        res.profile = x.fatos;
        registrar(ps, { codigo: x.fatos.length >= MAX_ITEMS ? "truncada" : vazioOuOk(x.fatos.length), registros: x.fatos.length, truncados: k.n, ...extra });
      }
    }
  }

  // Uma subpasta da Pasta: varredura fixa, um arquivo por item, estado por arquivo.
  // estrita = coleção de dados (frontmatter): item ilegível/recusado torna a coleção indisponível (como o helper).
  async function pasta(src, chave, normalizar, { estrita = false } = {}) {
    const lst = await listarPasta(root, src.partes);
    if (lst.status !== "ok") return registrar(src, { codigo: lst.status });
    const arquivos = lst.recusados.map((n) => ({ chave: text(n, 200), codigo: "link" }));
    const cortes = { n: 0 };
    const hash = createHash("sha256");
    let ultimo = null;
    let excluidos = 0;
    let estourou = lst.excedeu;
    let oks = 0;
    for (const nome of lst.nomes) {
      const r = await ler([...src.partes, nome]);
      if (r.status === "orcamento") { estourou = true; break; }
      if (r.status !== "ok") { arquivos.push({ chave: text(nome, 200), codigo: r.status }); continue; }
      hash.update(`${nome}\0${r.conteudo}\0`);
      if (!ultimo || r.mtime > ultimo) ultimo = r.mtime;
      let item = null;
      try { item = normalizar(nome, r.conteudo, r.mtime, cortes); } catch { item = null; }
      if (!item) { arquivos.push({ chave: text(nome, 200), codigo: "ilegivel" }); continue; }
      if (item.excluido) { excluidos++; arquivos.push({ chave: text(nome, 200), codigo: item.excluido }); continue; }
      const stem = nome.replace(/\.md$/, "");
      item._nota = `${src.pasta}/${stem}`;
      item._wiki = wikiLinks(r.conteudo);
      item.proveniencia.localizador = text(`${src.pasta}/${nome}`, 300);
      item.proveniencia.arquivoAtualizadoEm = r.mtime;
      res[chave].push(item);
      oks++;
    }
    const falhas = arquivos.filter((a) => a.codigo !== "nome_fora_do_padrao");
    let codigo;
    if (falhas.length && estrita) codigo = "ilegivel";
    else if (falhas.length && oks === 0) codigo = falhas.every((f) => f.codigo === falhas[0].codigo) ? falhas[0].codigo : "erro";
    else if (falhas.length) codigo = "parcial";
    else if (estourou) codigo = "truncada";
    else codigo = vazioOuOk(oks);
    return registrar(src, { codigo, arquivoAtualizadoEm: ultimo, registros: res[chave].length, excluidos, truncados: cortes.n, impressao: ultimo ? hash.digest("hex").slice(0, 16) : null, arquivos, lidos: oks });
  }

  // Item de coleção: frontmatter = dados (formato estrito), mapeado para o normalizador de sempre.
  const daColecao = (um) => (nome, conteudo, mtime, cortes) => {
    const { campos } = parseFrontmatter(conteudo, nome);
    const item = um(campos, mtime, cortes);
    if (!item) return null;
    return { ...item, area: area(campos.area), liga: refs(campos.liga) };
  };

  await pasta(SOURCES.decisoes, "decisions", daColecao((c, m, k) => normalizeDecisions({ decisoes: [c] }, SOURCES.decisoes, m, now, k)?.[0]), { estrita: true });
  await pasta(SOURCES.pendencias, "threads", daColecao((c, m, k) => normalizeThreads({ fios: [c] }, SOURCES.pendencias, m, now, k)?.[0]), { estrita: true });
  await pasta(SOURCES.assuntos, "subjects", daColecao((c, m, k) => normalizeSubject(c, SOURCES.assuntos, m, k)), { estrita: true });

  const nota = (src) => (nome, conteudo, mtime, cortes) => {
    const n = normalizeNote(nome, conteudo, src, mtime, cortes, orcamento);
    const { _campos: campos, pendente: _p, ...resto } = n;
    return { ...resto, liga: refs(campos.liga) };
  };
  await pasta(SOURCES.reunioes, "meetings", nota(SOURCES.reunioes));
  await pasta(SOURCES.notas, "daily", (nome, ...r) => (/^\d{4}-\d{2}-\d{2}\.md$/.test(nome) ? nota(SOURCES.notas)(nome, ...r) : { excluido: "nome_fora_do_padrao" }));
  await pasta(SOURCES.documentos, "documents", nota(SOURCES.documentos));
  await pasta(SOURCES.projetos, "projects", nota(SOURCES.projetos));
  res.meetings.sort(decrescente);
  res.daily.sort(decrescente);
  res.documents.sort(decrescente);

  // Ref canônica de cada item (tipo:id) e as ligações entre eles.
  const tipoDe = { decisions: "decisao", threads: "pendencia", subjects: "assunto", contexts: "contexto", meetings: "reuniao", daily: "nota", documents: "documento", projects: "projeto" };
  const todos = [];
  for (const [chave, tipo] of Object.entries(tipoDe)) for (const i of res[chave]) { i.ref = `${tipo}:${i.id}`; i._tipo = tipo; todos.push(i); }
  const { links, ocultas } = buildLinks(todos);
  const index = Object.create(null);
  const rotulos = new Map();
  for (const i of todos) {
    if (i._nota) { i.nota = text(i._nota, 300); index[i.nota] = i.ref; }
    rotulos.set(i.ref, i.titulo ?? i.tema ?? i.id);
    delete i._nota; delete i._wiki; delete i._tipo;
  }

  const { conflitos, diagnosticos } = diagnose({ ...res, links });
  const lacunas = [];
  if (!migrada) lacunas.push({ id: "pasta-nao-migrada", fonte: null, motivo: "A Pasta ainda não tem a marca da migração (.migrado): o agente ainda grava nos registros antigos e o que aparece aqui pode estar atrasado." });
  for (const c of res.contexts) if (c.estado === "pendente") lacunas.push({ id: `contexto-${c.id}`, fonte: "contexto", motivo: `${c.rotulo}: pendente de validação (a entrevista ainda não preencheu ou o Matheus não aprovou).` });
  if (ocultas) lacunas.push({ id: "arquivo-morto", fonte: null, motivo: `${ocultas} link(s) para o Arquivo-morto não aparecem (o que saiu não é mostrado).` });
  lacunas.push({ id: "projetos-subpastas", fonte: "projetos", motivo: "Só as notas soltas em Projetos/ são lidas; subpastas de projeto não são varridas." });
  for (const s of sources) if (s.estado === "indisponivel") lacunas.push({ id: `fonte-${s.id}`, fonte: s.id, motivo: `${s.rotulo}: ${AVISOS[s.codigo] ?? "indisponível"}` });
  if (!migrada) warnings.unshift({ fonte: "pasta", codigo: "nao_migrada", mensagem: lacunas[0].motivo });

  const areas = [...new Set([...todos, ...res.profile].map((i) => i.area).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR"));
  const coverage = {
    fontes: sources.length,
    fontesOk: sources.filter((s) => s.estado === "ok" || s.estado === "vazia").length,
    fontesIndisponiveis: sources.filter((s) => s.estado === "indisponivel").length,
    registros: Object.values(res).reduce((n, l) => n + l.length, 0),
    excluidos: sources.reduce((n, s) => n + s.excluidos, 0),
    textosCortados: sources.reduce((n, s) => n + s.truncados, 0),
    ligacoes: links.length,
    nota: "Só a Pasta do Segundo Cérebro é lida (subpastas fixas, sem Arquivo-morto). O que não está na Pasta não foi registrado.",
  };

  return {
    owner: OWNER,
    fetchedAt: now.toISOString(),
    pasta: { migrada },
    rules,
    areas,
    decisions: res.decisions,
    threads: res.threads,
    subjects: res.subjects,
    profile: res.profile,
    contexts: res.contexts,
    meetings: res.meetings,
    daily: res.daily,
    documents: res.documents,
    projects: res.projects,
    index,
    links,
    connections: buildConnections(links, rotulos),
    sources,
    warnings,
    gaps: lacunas,
    conflicts: conflitos,
    diagnostics: diagnosticos,
    coverage,
  };
}

// ---------- autenticação e requisição ----------

export function checkBearer(authorization, digestHex) {
  if (typeof authorization !== "string") return false;
  const m = /^Bearer ([^\s]+)$/.exec(authorization.trim());
  if (!m) return false;
  const esperado = Buffer.from(digestHex, "hex");
  const recebido = createHash("sha256").update(m[1], "utf8").digest();
  return esperado.length === recebido.length && timingSafeEqual(esperado, recebido);
}

function reply(status, body) {
  return { status, body, headers: { ...SECURITY_HEADERS } };
}

// request: Request da Web API (ou objeto com url, method e headers.get).
export async function handleSecondBrainRequest(request, env = process.env, now = new Date()) {
  if ((request.method ?? "GET").toUpperCase() !== "GET") return reply(405, { erro: "Método não permitido." });

  const digest = typeof env.SECOND_BRAIN_TOKEN_SHA256 === "string" ? env.SECOND_BRAIN_TOKEN_SHA256.trim() : "";
  const root = env.SECOND_BRAIN_DATA_ROOT ? String(env.SECOND_BRAIN_DATA_ROOT) : DEFAULT_DATA_ROOT;
  if (!/^[0-9a-fA-F]{64}$/.test(digest) || !path.isAbsolute(root)) {
    return reply(503, { erro: "Segundo Cérebro não configurado no servidor." });
  }

  let url;
  try {
    url = new URL(request.url, "http://localhost");
  } catch {
    return reply(400, { erro: "Endereço inválido." });
  }
  if (url.search !== "" || [...url.searchParams.keys()].length > 0) {
    return reply(400, { erro: "Parâmetros de consulta não são aceitos." });
  }
  for (const h of IDENTITY_HEADERS) {
    if (request.headers.get(h) !== null) return reply(403, { erro: "Seleção de identidade não é permitida." });
  }
  if (!checkBearer(request.headers.get("authorization"), digest)) {
    return reply(401, { erro: "Não autorizado." });
  }

  try {
    return reply(200, await loadSecondBrain({ root: path.resolve(root), now }));
  } catch {
    return reply(500, { erro: "Falha interna ao montar o Segundo Cérebro." });
  }
}
