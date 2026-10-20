// Fixture inteiramente sintético no formato da Pasta (infra/vm/plugins/cerebro/helpers/pasta.py): cabeçalho de linhas
// `chave: <JSON>` (com os separadores do json.dumps do Python), corpo Markdown com [[links]], índices, Contexto com
// seções pendentes e validadas, a ficha em Contexto/perfil.md. Sentinelas: Arquivo-morto, subpasta de projeto e os
// registros antigos (memoria/, fios/, chats/, skills/, projects/) nunca podem aparecer.
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { FICHA_MARCA, PENDENTE } from "../lib/second-brain.mjs";

export const SENTINELA = "ARQUIVO_MORTO_SENTINELA_7c1e";
export const FORA_DA_LISTA = "FONTE_ANTIGA_SENTINELA_42aa";
export const PASTA = "segundo_cerebro/pasta";

export function escrever(root, rel, data) {
  const dest = path.join(root, rel);
  mkdirSync(path.dirname(dest), { recursive: true });
  writeFileSync(dest, typeof data === "string" ? data : JSON.stringify(data));
}
export const naPasta = (root, rel, data) => escrever(root, `${PASTA}/${rel}`, data);

// json.dumps(v, ensure_ascii=False): separadores ", " e ": ".
export function pyJson(v) {
  if (Array.isArray(v)) return `[${v.map(pyJson).join(", ")}]`;
  if (v && typeof v === "object") return `{${Object.entries(v).map(([k, x]) => `${JSON.stringify(k)}: ${pyJson(x)}`).join(", ")}}`;
  return JSON.stringify(v);
}
export const frontmatter = (campos) => `---\n${Object.entries(campos).map(([k, v]) => `${k}: ${pyJson(v)}`).join("\n")}\n---\n`;

export function slug(t, n = 50) {
  const s = String(t ?? "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return s.slice(0, n).replace(/-+$/, "") || "item";
}
const prefixo = (id) => (/^\d+$/.test(String(id)) ? String(id).padStart(4, "0") : slug(id, 40));
const PASTAS = { decisao: "Decisoes", pendencia: "Pendencias", assunto: "Assuntos" };
const tituloDe = (x) => x.titulo ?? x.valor ?? x.tema ?? String(x.id);
export const stemDe = (tipo, x) => `${prefixo(x.id)}-${slug(tituloDe(x))}`;

export const ficha = (linhas) => `${frontmatter({ status: "validado", tags: ["contexto", "perfil"] })}# Sobre matheus\n\n> ${FICHA_MARCA} (add, patch, remove), uma entrada por linha, até 6000 caracteres. Não edite à mão.\n\n${linhas.map((l) => `- ${l}\n`).join("")}`;

// Escreve uma coleção como pasta.gravar: um arquivo por item (cabeçalho + corpo com [[links]]) e o indice.md.
export function colecao(root, tipo, itens, todos = {}) {
  const pasta = PASTAS[tipo];
  const link = (ref) => {
    const [t, id] = String(ref).split(":");
    const alvo = (todos[t] ?? []).find((x) => String(x.id) === id);
    return alvo ? `[[${PASTAS[t]}/${stemDe(t, alvo)}]]` : String(ref);
  };
  for (const x of itens) {
    const campos = { ...x, status: x.estado ?? "aberto", tags: [tipo, slug(x.area ?? "geral")] };
    const corpo = [`# ${tituloDe(x)}`, ""];
    if (tipo === "decisao") {
      corpo.push(x.valor ?? "", "");
      if (x.substitui) corpo.push(`- Substitui: ${link(`decisao:${x.substitui}`)}`);
      if (x.substituida_por) corpo.push(`- Substituída por: ${link(`decisao:${x.substituida_por}`)}`);
    } else if (tipo === "pendencia") corpo.push(x.detalhe ?? "", "", `- Estado: ${x.estado ?? "aberto"} · Área: ${x.area ?? "geral"}`);
    else corpo.push(`**Onde parou:** ${x.onde_parou ?? "(ainda nada)"}`, "");
    if (x.liga?.length) corpo.push("", "## Ligações", ...x.liga.map((r) => `- ${link(r)}`));
    naPasta(root, `${pasta}/${stemDe(tipo, x)}.md`, frontmatter(campos) + corpo.join("\n") + "\n");
  }
  naPasta(root, `${pasta}/indice.md`, `# ${pasta}\n\n${itens.map((x) => `- [[${pasta}/${stemDe(tipo, x)}]]`).join("\n")}\n`);
}

const contexto = (titulo, corpo, validado) =>
  validado
    ? `${frontmatter({ status: "validado", tags: ["contexto", slug(titulo)], aprovado: "ok, pode gravar", em: 1790000000 })}# ${titulo}\n\n${corpo}\n`
    : `${frontmatter({ status: "pendente", tags: ["contexto", slug(titulo)] })}# ${titulo}\n\n${PENDENTE}\n\nO que vai aqui: ${corpo}.\n`;

export const DECISOES = [
  { id: 1, tema: "teste.tom", tipo: "preferencia", valor: "Responder curto e direto", citacao: "fala curto", origem: "chat", por: "agente", em: 1790000000, estado: "ativa", area: "Raiz", liga: ["pendencia:a1"] },
  { id: 2, tema: "teste.envio", tipo: "proibicao", valor: "Nunca enviar sem aprovação", citacao: "", origem: "chat", por: "agente", em: 1790000100, estado: "ativa", area: "NEXOS" },
  { id: 3, tema: "teste.texto", tipo: "decisao", valor: "Texto antigo de teste", citacao: "", origem: "chat", por: "agente", em: 1790000200, estado: "substituida", fim_em: 1790000300, substituida_por: 4, area: "Raiz" },
  { id: 4, tema: "teste.texto", tipo: "decisao", valor: "Texto novo de teste", citacao: "", origem: "chat", por: "agente", em: 1790000300, estado: "ativa", substitui: 3, area: "Raiz" },
  { id: 5, tema: "outro.assunto", tipo: "decisao", valor: "Revogada de teste", citacao: "", origem: "chat", por: "agente", em: 1790000400, estado: "revogada", motivo: "mudou de ideia", area: "pessoal" },
];
export const PENDENCIAS = [
  { id: "a1", titulo: "Lançamento sintético", detalhe: "Organizar o lançamento", fontes: ["conversa sintética"], dono: "você", prioridade: "alta", proximo_passo: "Revisar o roteiro", ligacoes: "Depende do catálogo sintético", estado: "aberto", criado: 1790000000, atualizado: 1790000500, area: "Raiz", liga: ["assunto:s1"] },
  { id: "b2", titulo: "Catálogo sintético", detalhe: "Lista de produtos", fontes: [], dono: "agente", prioridade: "media", proximo_passo: "Montar a lista", ligacoes: ["a1"], estado: "aberto", criado: 1790000000, atualizado: 1790000400, area: "Orbyte" },
  { id: "c3", titulo: "Lançamento resolvido", detalhe: "Mesmo assunto, sem ligação", fontes: [], dono: "você", prioridade: "baixa", proximo_passo: "", ligacoes: "", estado: "resolvido", criado: 1790000000, atualizado: 1790000300, area: "Raiz" },
  { id: "d4", titulo: "Adiado vencido", detalhe: "Volta a contar como aberto", fontes: [], dono: "você", prioridade: "baixa", proximo_passo: "Retomar", ligacoes: "", estado: "adiado", adiar_ate: "2026-01-01", criado: 1790000000, atualizado: 1790000300, area: "pessoal" },
];
export const ASSUNTOS = [
  { id: "s1", titulo: "Fornecedor da loja", onde_parou: "Falta escolher entre os dois orçamentos", estado: "andamento", area: "Raiz", criado: 1790000000, atualizado: 1790000600, historico: [{ em: 1790000000, nota: "começou" }, { em: 1790000600, nota: "dois orçamentos na mesa" }], liga: ["decisao:1"] },
  { id: "s2", titulo: "Mudança de academia", onde_parou: "Decidiu ficar onde está", estado: "encerrado", area: "pessoal", criado: 1790000000, atualizado: 1790000100, historico: [] },
];

export function criarFixture({ migrada = true } = {}) {
  const root = mkdtempSync(path.join(tmpdir(), "sc-pasta-"));
  const todos = { decisao: DECISOES, pendencia: PENDENCIAS, assunto: ASSUNTOS };
  if (migrada) naPasta(root, ".migrado", "20/10/2026\n");
  naPasta(root, "CLAUDE.md", "# Segundo Cérebro do Matheus\n\nLeia isto antes.\n\n## Regras\n1. Leia `Contexto/` antes.\n2. Nunca invente: o que falta fica marcado.\n   Continua na linha de baixo.\n3. Nada se apaga.\n\n## Mapa\n| Pasta | O que tem |\n");
  naPasta(root, "Contexto/organizacao.md", contexto("Organização", "A Raiz vende sintético. Contato teste@exemplo.com.br, telefone (71) 98765-4321, CPF 123.456.789-09.\n\n## Ferramentas\n- Chave sk-abcdefghijklmnopqrstuvwxyz123 e token=abc123def456 no meio.\n- Decisão que vale: [[Decisoes/0001-responder-curto-e-direto]]", true));
  naPasta(root, "Contexto/marca.md", contexto("Marca e voz", "como cada marca fala", false));
  naPasta(root, "Contexto/estrategia.md", contexto("Estratégia", "## Metas\n- Lançar a loja sintética no trimestre", true));
  naPasta(root, "Contexto/cliente-ideal.md", contexto("Cliente ideal", "quem compra", false));
  naPasta(root, "Contexto/pessoas-chave.md", contexto("Pessoas-chave", "sócios e parceiros", false));
  naPasta(root, "Contexto/perfil.md", ficha(["Mora numa cidade fictícia", "Prefere respostas em português"]));
  naPasta(root, "Contexto/indice.md", "# Contexto\n\n- [[Contexto/organizacao]]\n");
  colecao(root, "decisao", DECISOES, todos);
  colecao(root, "pendencia", PENDENCIAS, todos);
  colecao(root, "assunto", ASSUNTOS, todos);
  naPasta(root, "Reunioes/2026-10-15-reuniao-raiz.md", `${frontmatter({ area: "Raiz", data: "2026-10-15" })}# Reunião da Raiz\n\n## Decidido\n- Seguir com [[Pendencias/a1-lancamento-sintetico]]\n- O que foi desfeito: [[Arquivo-morto/Decisoes/0009-${slug(SENTINELA)}]]\n`);
  naPasta(root, "Notas-do-dia/2026-10-18.md", `${frontmatter({ status: "fechada", tags: ["nota-do-dia", "2026-10"] })}# Nota do dia 18/10/2026\n\n## Decidido\n- [[Decisoes/0004-texto-novo-de-teste]] (Raiz)\n\n## Ficou para fazer\n- nada novo\n`);
  naPasta(root, "Notas-do-dia/2026-10-19.md", `${frontmatter({ status: "fechada", tags: ["nota-do-dia", "2026-10"] })}# Nota do dia 19/10/2026\n\n## Em discussão\n- [[Assuntos/s1-fornecedor-da-loja]]: parou em dois orçamentos\n`);
  naPasta(root, "Notas-do-dia/rascunho.md", "# não é uma nota do dia\n");
  naPasta(root, "Notas-do-dia/indice.md", "# Notas do dia\n\n- [[Notas-do-dia/2026-10-19]]\n");
  naPasta(root, "Documentos/auditoria-2026-10-20.md", "# Auditoria 20/10/2026\n\n## Achados\n- Contexto: [[Contexto/organizacao|organização]]\n- Falta: [[Documentos/inexistente]]\n");
  naPasta(root, "Projetos/loja-nova.md", `${frontmatter({ area: "Orbyte" })}# Loja nova\n\nProjeto sintético.\n`);
  naPasta(root, `Projetos/subprojeto/${slug(SENTINELA)}.md`, `# ${SENTINELA}\n`);
  naPasta(root, `Arquivo-morto/Decisoes/0009-${slug(SENTINELA)}.md`, `${frontmatter({ id: 9, tema: SENTINELA, estado: "ativa" })}# ${SENTINELA}\n`);
  naPasta(root, `Arquivo-morto/${SENTINELA}.md`, `# ${SENTINELA}\n`);
  // Registros antigos (antes da Pasta): nunca mais são lidos.
  escrever(root, "memoria/decisoes/matheus.json", { decisoes: [{ id: 99, tema: FORA_DA_LISTA, estado: "ativa" }] });
  escrever(root, "memoria/usuarios/matheus.md", `> ${FICHA_MARCA}\n- ${FORA_DA_LISTA}\n`);
  escrever(root, "fios/matheus.json", { fios: [{ id: "x", titulo: FORA_DA_LISTA }] });
  escrever(root, "chats/uMqjehmr/contexto.md", `# ${FORA_DA_LISTA}\n`);
  escrever(root, "skills/orquestrar-a0-hermes-openclaw/SKILL.md", `# ${FORA_DA_LISTA}\n`);
  escrever(root, "projects/meta-nexos/.a0proj/project.json", { title: FORA_DA_LISTA });
  return root;
}
