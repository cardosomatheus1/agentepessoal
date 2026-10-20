// Adaptador do Segundo Cérebro (servidor, Node puro, somente leitura).
// Uma única identidade fixa (matheus) e uma lista fixa de arquivos (allowlist do servidor); nenhum caminho vem do
// usuário, nenhuma pasta é varrida e nada é gravado. É uma projeção dos contratos canônicos, não uma base própria.

import { createHash, timingSafeEqual } from "node:crypto";
import { constants as FS, promises as fsp } from "node:fs";
import path from "node:path";

export const OWNER = "matheus";
export const DEFAULT_DATA_ROOT = "/a0/usr";
export const MAX_BYTES = 1024 * 1024;
const IDENTITY_HEADERS = ["x-user", "x-login", "x-tenant"];
const MAX_TEXT = 4000;
const MAX_ITEMS = 2000;

// Contratos lidos (estáticos, sem importar os helpers Python):
// - memoria_pessoal/helpers/decisoes.py: memoria/decisoes/<login>.json, {decisoes:[{id,tema,tipo,valor,citacao,origem,
//   por,em,estado,valido_ate?,fim_em?,fim_por?,substitui?,substituida_por?,motivo?}]}; vigente = ativa e não vencida.
// - memoria_pessoal/helpers/ficha.py: memoria/usuarios/<login>.md; uma entrada por linha "- "; sem a MARCA nas
//   primeiras 400 letras é o formato antigo (o helper recusa ler entradas).
// - fios_soltos/helpers/fios.py: fios/<login>.json, {fios:[{id,titulo,detalhe,fontes,dono,prazo,prioridade,
//   proximo_passo,ligacoes,estado,adiar_ate,criado,atualizado}], ruido:[...]}; em aberto = aberto ou adiado vencido.
// - rotinas/helpers/rotinas.py: skills/<slug>/SKILL.md com tag "rotina" (e o login de quem salvou); seções fixas;
//   versão = sha256(texto)[:12].
// - helpers/projects.py + login_usuarios/helpers/separacao.py: projects/<nome>/.a0proj/{project.json,dono.txt}.
export const FICHA_MARCA = "Mantida pela ferramenta `ficha`";
export const CONTEXTO_CHAT = "uMqjehmr";
export const PROJETOS_PERMITIDOS = Object.freeze(["meta-nexos", "saude", "carreira"]);
export const ROTINAS_PERMITIDAS = Object.freeze(["orquestrar-a0-hermes-openclaw", "melhorias-bom-dia-radar-reunioes-e-candidatos-maps"]);
const TERCEIRO = "terceiro (Playbook Lab), material público";
export const DOCUMENTOS_PERMITIDOS = Object.freeze([
  { chave: "requisitos", rotulo: "Requisitos e referências do Segundo Cérebro", dono: "matheus (documento deste pedido)", partes: ["workdir", "segundo_cerebro_correto", "REQUISITOS_REFERENCIAS.md"] },
  { chave: "setup", rotulo: "O Setup inicial do OS (página, texto verificado)", dono: TERCEIRO, partes: ["workdir", "segundo_cerebro_correto", "atual", "setup_verified.txt"] },
  { chave: "optimizer", rotulo: "OS Optimizer (página, texto verificado)", dono: TERCEIRO, partes: ["workdir", "segundo_cerebro_correto", "atual", "optimizer_verified.txt"] },
  { chave: "onboarding", rotulo: "Skill de onboarding de contexto", dono: TERCEIRO, partes: ["workdir", "segundo_cerebro", "downloads", "onboarding-contexto.md"] },
  { chave: "optimizer-skill", rotulo: "Skill OS Optimizer (SKILL.md do pacote)", dono: TERCEIRO, partes: ["workdir", "segundo_cerebro", "extraidos", "optimizer", "skills", "optimizer", "SKILL.md"] },
  { chave: "video", rotulo: "Descrição do vídeo 3cUQxnCMD2Y", dono: "terceiro (descrição automática de vídeo público)", partes: ["workdir", "videos", "descricao_completa_3cUQxnCMD2Y.md"] },
]);

export const SOURCES = Object.freeze({
  decisoes: { id: "decisoes", rotulo: "Memória de decisões", partes: ["memoria", "decisoes", "matheus.json"] },
  perfil: { id: "perfil", rotulo: "Ficha (fatos do Matheus)", partes: ["memoria", "usuarios", "matheus.md"] },
  fios: { id: "fios", rotulo: "Fios (próximos passos)", partes: ["fios", "matheus.json"] },
  contexto: { id: "contexto", rotulo: `Contexto da conversa ${CONTEXTO_CHAT}`, partes: ["chats", CONTEXTO_CHAT, "contexto.md"] },
  rotinas: { id: "rotinas", rotulo: "Rotinas (skills com tag rotina)", partes: ["skills"] },
  projetos: { id: "projetos", rotulo: "Projetos cadastrados no Agent Zero", partes: ["projects"] },
  documentos: { id: "documentos", rotulo: "Documentos autorizados deste pedido", partes: [] },
  reunioes: { id: "reunioes", rotulo: "Reuniões", partes: null },
  daily: { id: "daily", rotulo: "Registros do dia (daily)", partes: null },
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

// ---------- leitura segura ----------

async function readFixed(root, partes) {
  // Recusa link simbólico em qualquer nível abaixo da raiz e arquivo não regular.
  let ancestor = path.parse(root).root;
  for (const segment of root.slice(ancestor.length).split(path.sep).filter(Boolean)) {
    ancestor = path.join(ancestor, segment);
    try {
      const st = await fsp.lstat(ancestor);
      if (st.isSymbolicLink()) return { status: "link" };
      if (!st.isDirectory()) return { status: "erro" };
    } catch { return { status: "ausente" }; }
  }
  let atual = root;
  for (let i = 0; i < partes.length; i++) {
    atual = path.join(atual, partes[i]);
    let st;
    try {
      st = await fsp.lstat(atual);
    } catch (e) {
      if (e && (e.code === "ENOENT" || e.code === "ENOTDIR")) return { status: "ausente" };
      return { status: "erro" };
    }
    if (st.isSymbolicLink()) return { status: "link" };
    if (i < partes.length - 1 && !st.isDirectory()) return { status: "ausente" };
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
    const buf = Buffer.alloc(MAX_BYTES + 1);
    const { bytesRead } = await fh.read(buf, 0, MAX_BYTES + 1, 0);
    if (bytesRead > MAX_BYTES) return { status: "grande" };
    return { status: "ok", conteudo: buf.subarray(0, bytesRead).toString("utf8"), mtime: st.mtime.toISOString() };
  } catch {
    return { status: "erro" };
  } finally {
    await fh.close().catch(() => {});
  }
}

const AVISOS = {
  ausente: "Fonte indisponível: arquivo não encontrado.",
  link: "Fonte recusada: o arquivo é um link simbólico.",
  grande: "Fonte recusada: arquivo maior que 1 MB.",
  erro: "Fonte indisponível: não foi possível ler o arquivo.",
  invalida: "Fonte indisponível: conteúdo em formato inválido.",
  formato_antigo: "Fonte no formato antigo (texto livre): o helper da ficha recusa ler entradas até o operador migrar.",
  truncada: "Fonte lida em parte: mais registros que o limite de leitura; os excedentes não aparecem.",
  parcial: "Fonte lida em parte: alguns arquivos da lista não puderam ser lidos.",
};

// ---------- normalização ----------

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

export function normalizeThreads(data, src, mtime, now = new Date(), cortes = { n: 0 }) {
  if (!data || typeof data !== "object" || !Array.isArray(data.fios)) return null;
  const hoje = now.toISOString().slice(0, 10);
  return data.fios
    .slice(0, MAX_ITEMS)
    .filter((f) => f && typeof f === "object" && !Array.isArray(f))
    .map((f, i) => {
      const id = text(f.id, 120) ?? `fio-${i + 1}`;
      const estado = text(f.estado, 40);
      const adiar_ate = text(f.adiar_ate, 40);
      // fios.abertos(): aberto (estado ausente conta como aberto) ou adiado cujo adiar_ate já chegou.
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
        proveniencia: provenance(src, { localizador: `fios[id=${id}]`, em: dateText(f.atualizado) ?? dateText(f.criado), arquivoAtualizadoEm: mtime }),
      };
    });
}

// Ficha: só o formato do helper (MARCA no topo, entradas "- "). Formato antigo => null (fonte não projetada).
export function normalizeProfile(md, src, mtime, cortes = { n: 0 }) {
  if (!md.slice(0, 400).includes(FICHA_MARCA)) return { formatoAntigo: true, fatos: [] };
  const fatos = [];
  md.split(/\r?\n/).forEach((linha, idx) => {
    if (!linha.startsWith("- ") || fatos.length >= MAX_ITEMS) return;
    const t = texto(linha.slice(2).replace(/\s+/g, " "), 1000, cortes);
    if (!t) return;
    const numero = fatos.length + 1;
    fatos.push({ id: `perfil-${numero}`, numero, texto: t, proveniencia: provenance(src, { localizador: `entrada ${numero} (linha ${idx + 1})`, linha: idx + 1, arquivoAtualizadoEm: mtime }) });
  });
  return { formatoAntigo: false, fatos };
}

// contexto.md: seções "# Título" com itens "- ". Cada seção é um registro com o intervalo de linhas de origem.
export function normalizeContext(md, src, mtime, cortes = { n: 0 }) {
  const secoes = [];
  let atual = null;
  md.split(/\r?\n/).forEach((linha, idx) => {
    const h = /^#{1,3}\s+(.+)$/.exec(linha);
    if (h) {
      atual = { inicio: idx + 1, fim: idx + 1, titulo: texto(h[1], 200, cortes) ?? "(sem título)", itens: [] };
      secoes.push(atual);
      return;
    }
    if (!linha.trim()) return;
    if (!atual) {
      atual = { inicio: idx + 1, fim: idx + 1, titulo: "(sem título)", itens: [] };
      secoes.push(atual);
    }
    atual.fim = idx + 1;
    const t = texto(linha.replace(/^\s*[-*]\s+/, ""), 1200, cortes);
    if (t) atual.itens.push({ linha: idx + 1, texto: t });
  });
  return secoes.slice(0, MAX_ITEMS).map((s) => ({
    id: `${CONTEXTO_CHAT}-L${s.inicio}`,
    titulo: s.titulo,
    itens: s.itens,
    linhas: [s.inicio, s.fim],
    proveniencia: provenance(src, { localizador: `contexto.md linhas ${s.inicio}–${s.fim}`, linha: s.inicio, arquivoAtualizadoEm: mtime, autorizacao: "allowlist do servidor (único contexto autorizado)" }),
  }));
}

function frontMatter(t) {
  if (!t.startsWith("---")) return {};
  const bloco = t.slice(3).split("\n---", 1)[0];
  const dados = { trigger_patterns: [] };
  let lista = null;
  for (const linha of bloco.split("\n")) {
    if (lista && /^\s+- /.test(linha)) { dados[lista].push(linha.split("- ").slice(1).join("- ").trim().replace(/^"|"$/g, "")); continue; }
    lista = null;
    const m = /^(\w+):\s*(.*)$/.exec(linha);
    if (!m) continue;
    if (m[1] === "trigger_patterns" && !m[2]) lista = "trigger_patterns";
    else dados[m[1]] = m[2].trim().replace(/^"|"$/g, "");
  }
  let tags = [];
  try {
    const parsed = JSON.parse(dados.tags ?? "[]");
    tags = Array.isArray(parsed) ? parsed.map(String) : [String(parsed)];
  } catch {
    tags = String(dados.tags ?? "").replace(/[[\]"]/g, "").split(",").map((x) => x.trim()).filter(Boolean);
  }
  return { ...dados, tags };
}

const SECOES_ROTINA = {
  "Quando usar": "quando_usar",
  "Entradas e acessos": "entradas",
  Passos: "passos",
  "Como verificar que deu certo": "verificar",
  "O que entregar": "entregar",
  "Precisa de aprovação do usuário": "aprovacao",
};

// SKILL.md salvo pelo helper das rotinas. Dono = login na tag (sem login: rotina compartilhada do agente).
export function normalizeRoutine(slug, md, src, mtime, cortes = { n: 0 }) {
  const fm = frontMatter(md);
  if (!fm.tags || !fm.tags.includes("rotina")) return { naoRotina: true };
  const logins = fm.tags.filter((t) => t !== "rotina");
  if (logins.length && !logins.includes(OWNER)) return { outroDono: true };
  const secoes = {};
  const correcoes = [];
  let chave = null;
  md.split(/\r?\n/).forEach((linha, idx) => {
    const h = /^## (.+)$/.exec(linha);
    if (h) {
      const nome = h[1].trim();
      chave = nome.startsWith("Correções do usuário") ? "correcoes" : (SECOES_ROTINA[nome] ?? null);
      if (chave && chave !== "correcoes") secoes[chave] = { linha: idx + 1, linhas: [] };
      return;
    }
    if (!chave) return;
    if (chave === "correcoes") {
      const m = /^- (?:(\d{2}\/\d{2}\/\d{4})(?: \(por ([^)]*)\))?: )?(.+)$/.exec(linha);
      if (m) correcoes.push({ linha: idx + 1, data: m[1] ?? null, por: text(m[2], 120), texto: texto(m[3], 1000, cortes) });
      return;
    }
    if (linha.trim()) secoes[chave].linhas.push(linha);
  });
  const corpo = (k) => (secoes[k] ? texto(secoes[k].linhas.join("\n"), 3000, cortes) : null);
  const passos = secoes.passos
    ? secoes.passos.linhas.map((l) => texto(l.replace(/^\s*\d+[.)]\s+/, ""), 1000, cortes)).filter(Boolean)
    : [];
  const titulo = /^# (.+)$/m.exec(md)?.[1];
  return {
    id: slug,
    nome: texto(titulo ?? fm.name ?? slug, 200, cortes),
    descricao: texto(fm.description, 600, cortes),
    gatilhos: textList(fm.trigger_patterns, cortes),
    dono: logins.includes(OWNER) ? OWNER : null,
    donoNota: logins.includes(OWNER) ? "login matheus na tag" : "sem login na tag: rotina compartilhada do agente (contrato das rotinas)",
    versao: createHash("sha256").update(md, "utf8").digest("hex").slice(0, 12),
    quando_usar: corpo("quando_usar"),
    entradas: corpo("entradas"),
    passos,
    verificar: corpo("verificar"),
    entregar: corpo("entregar"),
    aprovacao: corpo("aprovacao"),
    secoesAusentes: Object.values(SECOES_ROTINA).filter((k) => !secoes[k]),
    correcoes,
    pedeReescrita: correcoes.length >= 8,
    proveniencia: provenance(src, { localizador: `skills/${slug}/SKILL.md`, arquivoAtualizadoEm: mtime, versao: createHash("sha256").update(md, "utf8").digest("hex").slice(0, 12), dono: logins.includes(OWNER) ? OWNER : "agente (compartilhada)" }),
  };
}

export function normalizeProject(nome, json, src, mtime, cortes = { n: 0 }) {
  if (!json || typeof json !== "object" || Array.isArray(json)) return null;
  return {
    id: nome,
    titulo: texto(json.title, 200, cortes) ?? nome,
    descricao: texto(json.description, 1200, cortes),
    instrucoes: texto(json.instructions, 1500, cortes),
    cor: text(json.color, 20),
    proveniencia: provenance(src, { localizador: `projects/${nome}/.a0proj/project.json`, arquivoAtualizadoEm: mtime, donoProva: "dono.txt = matheus" }),
  };
}

const CABECALHO = /^(?:(#{1,4})\s+(.+)|\s*\[(page|header|sub_header|sub_sub_header)\]\s+(.+))$/;
export function normalizeDocument(doc, conteudo, src, mtime, cortes = { n: 0 }) {
  const secoes = [];
  conteudo.split(/\r?\n/).forEach((linha, idx) => {
    const m = CABECALHO.exec(linha);
    if (m && secoes.length < 80) secoes.push({ linha: idx + 1, titulo: texto(m[2] ?? m[4], 200, cortes) });
  });
  return {
    id: doc.chave,
    titulo: doc.rotulo,
    dono: doc.dono,
    bytes: Buffer.byteLength(conteudo, "utf8"),
    linhas: conteudo.split(/\r?\n/).length,
    sha256: createHash("sha256").update(conteudo, "utf8").digest("hex"),
    secoes: secoes.filter((s) => s.titulo),
    citaDocumentos: [],
    proveniencia: { fonte: src.id, fonteRotulo: src.rotulo, dono: doc.dono, localizador: doc.partes.join("/"), arquivoAtualizadoEm: mtime },
  };
}

// Grafo legado (seção "ligações dos fios"): só o que está em fios[].ligacoes. Alvo que não é um fio vira nó
// textual separado e rotulado; nada é inferido.
export function buildConnections(threads) {
  const nodes = new Map();
  const edges = [];
  const ids = new Set(threads.map((t) => t.id));
  for (const t of threads) {
    for (const l of t.ligacoes) {
      if (!nodes.has(`fio:${t.id}`)) nodes.set(`fio:${t.id}`, { id: `fio:${t.id}`, tipo: "fio", rotulo: t.titulo ?? t.id });
      let destino;
      if (ids.has(l.alvo)) {
        destino = `fio:${l.alvo}`;
        const alvo = threads.find((x) => x.id === l.alvo);
        if (!nodes.has(destino)) nodes.set(destino, { id: destino, tipo: "fio", rotulo: alvo?.titulo ?? l.alvo });
      } else {
        destino = `texto:${l.alvo}`;
        if (!nodes.has(destino)) nodes.set(destino, { id: destino, tipo: "texto", rotulo: l.alvo });
      }
      edges.push({
        de: `fio:${t.id}`,
        para: destino,
        rotulo: l.rotulo,
        evidencia: { fonte: "fios", fioId: t.id, em: t.atualizado ?? t.criado },
      });
    }
  }
  return { nodes: [...nodes.values()], edges };
}

// ---------- diagnósticos (não autoritativos) ----------

const chaveTexto = (s) => String(s ?? "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9@]+/g, " ").trim();

// Só invariantes explícitos dos contratos: nunca semelhança de palavras entre registros diferentes.
export function diagnose({ decisions, threads, profile, routines }) {
  const conflitos = [];
  const diagnosticos = [];
  const porTema = new Map();
  for (const d of decisions) if (d.vigente && d.tema) porTema.set(d.tema, [...(porTema.get(d.tema) ?? []), d.id]);
  for (const [tema, ids] of porTema) {
    if (ids.length > 1) {
      conflitos.push({ tipo: "decisoes_ativas_mesmo_tema", fonte: "decisoes", registros: ids.map((id) => `decisao:${id}`), regra: "decisoes.py: uma decisão ativa por tema", detalhe: `${ids.length} decisões vigentes no tema "${tema}"`, autoritativo: false });
    }
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
  const idsFio = new Map();
  for (const t of threads) idsFio.set(t.id, (idsFio.get(t.id) ?? 0) + 1);
  for (const [id, n] of idsFio) if (n > 1) conflitos.push({ tipo: "fio_id_repetido", fonte: "fios", registros: [`fio:${id}`], regra: "fios.py: id único por fio", detalhe: `${n} fios com o mesmo id`, autoritativo: false });
  for (const r of routines) {
    if (r.pedeReescrita) diagnosticos.push({ tipo: "rotina_pede_reescrita", fonte: "rotinas", registros: [`rotina:${r.id}`], regra: "rotinas.py: LIMITE = 8 correções", detalhe: `${r.correcoes.length} correções acumuladas`, autoritativo: false });
    if (r.secoesAusentes.length) diagnosticos.push({ tipo: "rotina_secoes_ausentes", fonte: "rotinas", registros: [`rotina:${r.id}`], regra: "rotinas.py salvar(): seções fixas", detalhe: `faltam: ${r.secoesAusentes.join(", ")}`, autoritativo: false });
  }
  return { conflitos, diagnosticos };
}

// ---------- onboarding: estado honesto das 7 + 6 seções (proposta, nunca gravada) ----------

export const ONBOARDING = Object.freeze({
  negocio: [
    ["negocio", "Seu negócio", "organization.md"],
    ["clientes", "Seus clientes", "icp.md"],
    ["posicionamento", "Seu posicionamento", "organization.md + icp.md"],
    ["marca", "Sua marca e voz", "brand.md"],
    ["estrategia", "Seus objetivos e sua estratégia", "strategy.md"],
    ["operacao", "Sua operação e ferramentas", "organization.md"],
    ["pessoas", "Pessoas-chave", "pessoas-chave.md"],
  ],
  pessoal: [
    ["sobre", "Sobre você", "Profile.md"],
    ["trajetoria", "Sua trajetória profissional", "Profile.md"],
    ["experiencia", "Sua experiência e seu ponto de vista", "Profile.md"],
    ["estilo", "Seu estilo de trabalho", "Profile.md"],
    ["claude", "Como você quer que o Claude trabalhe com você", "CLAUDE.md"],
    ["sucesso", "Como é o sucesso", "Profile.md"],
  ],
});

export function onboardingState({ decisions, profile, routines, sources }) {
  const fonte = (id) => sources.find((s) => s.id === id);
  const fichaOk = fonte("perfil")?.estado === "ok";
  const decOk = fonte("decisoes")?.estado === "ok";
  const vigentes = decisions.filter((d) => d.vigente);
  const comoTrabalhar = vigentes.filter((d) => ["preferencia", "proibicao", "permissao"].includes(d.tipo ?? ""));
  const base = { aprovado: false, promovido: false, proposta: "Retomar só esta seção com o Matheus; gravar pela ferramenta canônica depois da aprovação dele." };
  const negocio = ONBOARDING.negocio.map(([id, titulo, publicado]) => {
    if (id === "operacao" && routines.length) {
      return { ...base, id, titulo, publicado, estado: "parcial", destino: "rotinas (processos repetíveis) + contexto empresarial a definir", evidencias: routines.map((r) => `rotina:${r.id}`), motivo: `${routines.length} rotina(s) registradas descrevem processos; não há descrição da operação nem das ferramentas.` };
    }
    return { ...base, id, titulo, publicado, estado: "pendente", destino: "contexto empresarial (não existe contrato canônico; definir com o Matheus)", evidencias: [], motivo: "Sem fonte canônica de contexto empresarial com dono comprovado. O único contexto autorizado é registro de uma conversa, não onboarding." };
  });
  const pessoal = ONBOARDING.pessoal.map(([id, titulo, publicado]) => {
    if (id === "sobre" && fichaOk && profile.length) {
      return { ...base, id, titulo, publicado, estado: "parcial", destino: "ficha (fatos)", evidencias: profile.map((f) => `fato:${f.id}`), motivo: `${profile.length} fato(s) na ficha; a ficha não separa as seções do onboarding, então não dá para dizer quais perguntas estão respondidas.` };
    }
    if (id === "claude" && decOk && comoTrabalhar.length) {
      return { ...base, id, titulo, publicado, estado: "parcial", destino: "decisões (preferências, permissões e proibições)", evidencias: comoTrabalhar.map((d) => `decisao:${d.id}`), motivo: `${comoTrabalhar.length} decisão(ões) vigentes de tipo preferência/permissão/proibição (campo tipo do contrato).` };
    }
    const destino = id === "claude" ? "decisões (preferências, permissões e proibições)" : "ficha (fatos) — preferências vão em decisões";
    const motivo = (id === "sobre" && !fichaOk) || (id === "claude" && !decOk) ? "Fonte de destino indisponível." : "Sem evidência estruturada desta seção nas fontes canônicas.";
    return { ...base, id, titulo, publicado, estado: "pendente", destino, evidencias: [], motivo };
  });
  return { negocio, pessoal, nota: "Proposta de retomada: nada aqui foi aprovado nem promovido a dado canônico." };
}

// ---------- carga ----------

const vazioOuOk = (n) => (n === 0 ? "vazia" : "ok");

export async function loadSecondBrain({ root, now = new Date() }) {
  const warnings = [];
  const sources = [];
  const res = { decisions: [], threads: [], profile: [], contexts: [], routines: [], projects: [], documents: [] };

  function registrar(src, extra) {
    const s = { id: src.id, rotulo: src.rotulo, dono: OWNER, localizador: src.partes ? src.partes.join("/") || "(lista fixa)" : null, arquivoAtualizadoEm: null, registros: 0, excluidos: 0, truncados: 0, impressao: null, arquivos: [], ...extra };
    s.estado = ["ok", "vazia", "sem_contrato"].includes(s.codigo) ? s.codigo : (s.codigo === "truncada" || s.codigo === "parcial") ? "ok" : "indisponivel";
    sources.push(s);
    if (!["ok", "vazia", "sem_contrato"].includes(s.codigo)) warnings.push({ fonte: src.id, codigo: s.codigo, mensagem: `${src.rotulo}: ${AVISOS[s.codigo]}` });
    return s;
  }

  async function arquivoUnico(src, parse, chave) {
    const r = await readFixed(root, src.partes);
    if (r.status !== "ok") return registrar(src, { codigo: r.status });
    const cortes = { n: 0 };
    let saida = null;
    try { saida = parse(r.conteudo, r.mtime, cortes); } catch { saida = null; }
    if (saida && saida.formatoAntigo) return registrar(src, { codigo: "formato_antigo", arquivoAtualizadoEm: r.mtime, impressao: impressao(r.conteudo) });
    const itens = saida && !Array.isArray(saida) && saida.fatos ? saida.fatos : saida;
    if (!itens) return registrar(src, { codigo: "invalida", arquivoAtualizadoEm: r.mtime, impressao: impressao(r.conteudo) });
    res[chave] = itens;
    const excedeu = itens.length >= MAX_ITEMS;
    return registrar(src, { codigo: excedeu ? "truncada" : vazioOuOk(itens.length), arquivoAtualizadoEm: r.mtime, registros: itens.length, truncados: cortes.n, impressao: impressao(r.conteudo) });
  }

  await arquivoUnico(SOURCES.decisoes, (c, m, k) => normalizeDecisions(JSON.parse(c), SOURCES.decisoes, m, now, k), "decisions");
  await arquivoUnico(SOURCES.perfil, (c, m, k) => normalizeProfile(c, SOURCES.perfil, m, k), "profile");
  await arquivoUnico(SOURCES.fios, (c, m, k) => normalizeThreads(JSON.parse(c), SOURCES.fios, m, now, k), "threads");
  await arquivoUnico(SOURCES.contexto, (c, m, k) => normalizeContext(c, SOURCES.contexto, m, k), "contexts");

  // Fontes de vários arquivos: só os nomes da allowlist; cada arquivo tem o próprio estado.
  async function lista(src, chave, entradas) {
    const arquivos = [];
    const cortes = { n: 0 };
    const hash = createHash("sha256");
    let ultimo = null;
    let excluidos = 0;
    for (const e of entradas) {
      const r = await e.ler();
      if (r.status === "ok") {
        hash.update(`${e.chave}\0${r.conteudo}\0`);
        if (r.mtime && (!ultimo || r.mtime > ultimo)) ultimo = r.mtime;
      }
      const item = r.status === "ok" ? e.normalizar(r, cortes) : null;
      if (item && item.excluido) { excluidos++; arquivos.push({ chave: e.chave, codigo: item.excluido }); continue; }
      if (r.status === "ok" && !item) { arquivos.push({ chave: e.chave, codigo: "invalida" }); continue; }
      arquivos.push({ chave: e.chave, codigo: r.status === "ok" ? "ok" : r.codigo ?? r.status });
      if (item) res[chave].push(item);
    }
    const oks = arquivos.filter((a) => a.codigo === "ok").length;
    const falhas = arquivos.filter((a) => !["ok", "outro_dono", "dono_nao_comprovado", "nao_rotina"].includes(a.codigo));
    let codigo;
    // Sem nenhum arquivo bom e com falha: a fonte está indisponível (excluídos por dono não contam como falha).
    if (falhas.length && oks === 0) codigo = falhas.every((f) => f.codigo === falhas[0].codigo) ? falhas[0].codigo : "erro";
    else if (falhas.length) codigo = "parcial";
    else codigo = vazioOuOk(oks);
    return registrar(src, { codigo, arquivoAtualizadoEm: ultimo, registros: res[chave].length, excluidos, truncados: cortes.n, impressao: ultimo ? hash.digest("hex").slice(0, 16) : null, arquivos });
  }

  await lista(SOURCES.rotinas, "routines", ROTINAS_PERMITIDAS.map((slug) => ({
    chave: slug,
    ler: () => readFixed(root, ["skills", slug, "SKILL.md"]),
    normalizar: (r, cortes) => {
      const x = normalizeRoutine(slug, r.conteudo, SOURCES.rotinas, r.mtime, cortes);
      if (x.naoRotina) return { excluido: "nao_rotina" };
      if (x.outroDono) return { excluido: "outro_dono" };
      return x;
    },
  })));

  await lista(SOURCES.projetos, "projects", PROJETOS_PERMITIDOS.map((nome) => ({
    chave: nome,
    // Dono primeiro (login_usuarios: .a0proj/dono.txt). Sem dono.txt o contrato atribui ao dono padrão, mas isso
    // não é prova: o projeto fica de fora e a ausência aparece na cobertura.
    ler: async () => {
      const dono = await readFixed(root, ["projects", nome, ".a0proj", "dono.txt"]);
      if (dono.status === "ausente") {
        const cabecalho = await readFixed(root, ["projects", nome, ".a0proj", "project.json"]);
        return cabecalho.status === "ausente" ? cabecalho : { status: "ok", conteudo: "", mtime: null, semDono: true };
      }
      if (dono.status !== "ok") return dono;
      if (dono.conteudo.trim().toLowerCase() !== OWNER) return { status: "ok", conteudo: "", mtime: null, outroDono: true };
      const r = await readFixed(root, ["projects", nome, ".a0proj", "project.json"]);
      return r;
    },
    normalizar: (r, cortes) => {
      if (r.semDono) return { excluido: "dono_nao_comprovado" };
      if (r.outroDono) return { excluido: "outro_dono" };
      try { return normalizeProject(nome, JSON.parse(r.conteudo), SOURCES.projetos, r.mtime, cortes); } catch { return null; }
    },
  })));

  await lista(SOURCES.documentos, "documents", DOCUMENTOS_PERMITIDOS.map((doc) => ({
    chave: doc.chave,
    ler: () => readFixed(root, doc.partes),
    normalizar: (r, cortes) => {
      const d = normalizeDocument(doc, r.conteudo, SOURCES.documentos, r.mtime, cortes);
      // Citação explícita: o texto contém o caminho completo de outro documento da lista.
      d.citaDocumentos = DOCUMENTOS_PERMITIDOS.filter((o) => o.chave !== doc.chave && r.conteudo.includes(`${DEFAULT_DATA_ROOT}/${o.partes.join("/")}`)).map((o) => o.chave);
      return d;
    },
  })));

  registrar(SOURCES.reunioes, { codigo: "sem_contrato", localizador: null });
  registrar(SOURCES.daily, { codigo: "sem_contrato", localizador: null });

  const { conflitos, diagnosticos } = diagnose(res);
  const lacunas = [
    { id: "reunioes", fonte: "reunioes", motivo: "Não há plugin nem arquivo canônico de reuniões com dono; nada é mostrado como reunião." },
    { id: "daily", fonte: "daily", motivo: "Não há contrato canônico de registros do dia; nada é mostrado como daily." },
    { id: "pessoas-chave", fonte: null, motivo: "Não há fonte de pessoas-chave com papéis confirmados; pautas ficam sem responsáveis." },
    { id: "contexto-empresarial", fonte: null, motivo: "Não há fonte canônica de organização, marca, estratégia ou ICP; ver onboarding." },
  ];
  for (const s of sources) {
    if (s.id === "projetos") for (const a of s.arquivos) if (a.codigo === "dono_nao_comprovado") lacunas.push({ id: `projeto-sem-dono-${lacunas.length}`, fonte: "projetos", motivo: "Um projeto da lista não tem dono.txt; sem prova de dono ele não é mostrado." });
    if (s.estado === "indisponivel") lacunas.push({ id: `fonte-${s.id}`, fonte: s.id, motivo: `${s.rotulo}: ${AVISOS[s.codigo] ?? "indisponível"}` });
  }

  const coverage = {
    fontes: sources.length,
    fontesOk: sources.filter((s) => s.estado === "ok" || s.estado === "vazia").length,
    fontesIndisponiveis: sources.filter((s) => s.estado === "indisponivel").length,
    fontesSemContrato: sources.filter((s) => s.estado === "sem_contrato").length,
    registros: Object.values(res).reduce((n, l) => n + l.length, 0),
    excluidosPorDono: sources.reduce((n, s) => n + s.excluidos, 0),
    textosCortados: sources.reduce((n, s) => n + s.truncados, 0),
    nota: "Contagens só das fontes da allowlist. Fora dela nada é lido; total não significa base completa.",
  };

  return {
    owner: OWNER,
    fetchedAt: now.toISOString(),
    decisions: res.decisions,
    threads: res.threads,
    profile: res.profile,
    contexts: res.contexts,
    documents: res.documents,
    projects: res.projects,
    routines: res.routines,
    meetings: [],
    daily: [],
    connections: buildConnections(res.threads),
    sources,
    warnings,
    gaps: lacunas,
    conflicts: conflitos,
    diagnostics: diagnosticos,
    proposals: { onboarding: onboardingState({ ...res, sources }) },
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
