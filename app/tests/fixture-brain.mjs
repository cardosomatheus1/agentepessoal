// Fixture inteiramente sintético no formato real dos contratos (decisoes.py, ficha.py, fios.py, rotinas.py,
// projects.py + dono.txt). Inclui sentinelas de outra pessoa e de arquivos fora da allowlist: nunca podem aparecer.
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { FICHA_MARCA, DOCUMENTOS_PERMITIDOS } from "../lib/second-brain.mjs";

export const SENTINELA = "OUTRA_PESSOA_SENTINELA_7c1e";
export const FORA_DA_LISTA = "FORA_DA_ALLOWLIST_SENTINELA_42aa";

export function escrever(root, rel, data) {
  const dest = path.join(root, rel);
  mkdirSync(path.dirname(dest), { recursive: true });
  writeFileSync(dest, typeof data === "string" ? data : JSON.stringify(data));
}

export const ficha = (linhas) => `# Sobre matheus\n\n> ${FICHA_MARCA} (add, patch, remove), uma entrada por linha. Não edite à mão.\n\n${linhas.map((l) => `- ${l}\n`).join("")}`;

export function rotina(nome, { tags = ["rotina", "matheus"], correcoes = [] } = {}) {
  return [
    "---", `name: ${nome}`, 'description: "Rotina sintética de teste"', "version: 1.0.0", `tags: ${JSON.stringify(tags)}`, "trigger_patterns:", '  - "rodar teste"', "---",
    `# ${nome}`, "", "Rotina salva em 01/10/2026 por matheus.", "",
    "## Quando usar", "Quando o teste pedir.", "",
    "## Entradas e acessos", "Arquivo sintético; senha: naoMostrar123", "",
    "## Passos", "1. Ler o arquivo sintético", "2. Conferir o total", "",
    "## Como verificar que deu certo", "O total confere com o arquivo.", "",
    "## O que entregar", "Resumo de uma linha.", "",
    "## Precisa de aprovação do usuário", "Antes de enviar qualquer coisa a terceiros.",
    ...(correcoes.length ? ["", "## Correções do usuário (valem acima dos passos)", ...correcoes.map((c, i) => `- 0${(i % 9) + 1}/10/2026 (por matheus): ${c}`)] : []),
    "",
  ].join("\n");
}

export function criarFixture({ semExtras = false } = {}) {
  const root = mkdtempSync(path.join(tmpdir(), "sc-brain-"));
  escrever(root, "memoria/decisoes/matheus.json", {
    decisoes: [
      { id: 1, tema: "teste.tom", tipo: "preferencia", valor: "Responder curto e direto", citacao: "fala curto", origem: "chat", por: "agente", em: 1790000000, estado: "ativa" },
      { id: 2, tema: "teste.envio", tipo: "proibicao", valor: "Nunca enviar sem aprovação", citacao: "", origem: "chat", por: "agente", em: 1790000100, estado: "ativa" },
      { id: 3, tema: "teste.texto", tipo: "decisao", valor: "Texto antigo de teste", citacao: "", origem: "chat", por: "agente", em: 1790000200, estado: "substituida", fim_em: 1790000300, substituida_por: 4 },
      { id: 4, tema: "teste.texto", tipo: "decisao", valor: "Texto novo de teste", citacao: "", origem: "chat", por: "agente", em: 1790000300, estado: "ativa", substitui: 3 },
      { id: 5, tema: "outro.assunto", tipo: "decisao", valor: "Revogada de teste", citacao: "", origem: "chat", por: "agente", em: 1790000400, estado: "revogada", motivo: "mudou de ideia" },
    ],
  });
  escrever(root, "memoria/usuarios/matheus.md", ficha(["Mora numa cidade fictícia", "Prefere respostas em português"]));
  escrever(root, "fios/matheus.json", {
    fios: [
      { id: "a1", titulo: "Lançamento sintético", detalhe: "Organizar o lançamento", fontes: ["conversa sintética"], dono: "você", prioridade: "alta", proximo_passo: "Revisar o roteiro", ligacoes: "Depende do catálogo sintético", estado: "aberto", criado: 1790000000, atualizado: 1790000500 },
      { id: "b2", titulo: "Catálogo sintético", detalhe: "Lista de produtos", fontes: [], dono: "agente", prioridade: "media", proximo_passo: "Montar a lista", ligacoes: ["a1"], estado: "aberto", criado: 1790000000, atualizado: 1790000400 },
      { id: "c3", titulo: "Lançamento resolvido", detalhe: "Mesmo assunto, sem ligação", fontes: [], dono: "você", prioridade: "baixa", proximo_passo: "", ligacoes: "", estado: "resolvido", criado: 1790000000, atualizado: 1790000300 },
      { id: "d4", titulo: "Adiado vencido", detalhe: "Volta a contar como aberto", fontes: [], dono: "você", prioridade: "baixa", proximo_passo: "Retomar", ligacoes: "", estado: "adiado", adiar_ate: "2026-01-01", criado: 1790000000, atualizado: 1790000300 },
    ],
    ruido: [SENTINELA],
  });
  escrever(root, "fios/fernanda.json", { fios: [{ id: "x", titulo: SENTINELA }] });
  escrever(root, "memoria/decisoes/fernanda.json", { decisoes: [{ id: 1, tema: SENTINELA, estado: "ativa" }] });
  escrever(root, "memoria/usuarios/fernanda.md", ficha([SENTINELA]));
  if (!semExtras) escreverExtras(root);
  return root;
}

// Contexto, rotinas, projetos e documentos sintéticos (as fontes novas), para quem já tem o próprio fixture.
export function escreverExtras(root) {
  escrever(root, "chats/uMqjehmr/contexto.md", "# Assunto sintético — 17/10/2026\n- Matheus autorizou o teste sintético.\n- Contato teste@exemplo.com.br, telefone (71) 98765-4321, CPF 123.456.789-09.\n- Chave sk-abcdefghijklmnopqrstuvwxyz123 e token=abc123def456 no meio.\n\n# Segundo assunto\n- Item com https://exemplo.com/?token=segredo123&x=1\n");
  escrever(root, "chats/outroChat/contexto.md", `# ${SENTINELA}\n- ${FORA_DA_LISTA}\n`);
  escrever(root, "skills/orquestrar-a0-hermes-openclaw/SKILL.md", rotina("Orquestrar teste"));
  escrever(root, "skills/melhorias-bom-dia-radar-reunioes-e-candidatos-maps/SKILL.md", rotina("Rotina compartilhada de teste", { tags: ["rotina"] }));
  escrever(root, "skills/fora-da-lista/SKILL.md", rotina(FORA_DA_LISTA));
  escrever(root, "projects/meta-nexos/.a0proj/dono.txt", "matheus\n");
  escrever(root, "projects/meta-nexos/.a0proj/project.json", { title: "Projeto sintético", description: "Descrição sintética", instructions: "Instruções sintéticas", color: "#fff", git_url: "", file_structure: {} });
  escrever(root, "projects/saude/.a0proj/dono.txt", "fernanda");
  escrever(root, "projects/saude/.a0proj/project.json", { title: SENTINELA, description: SENTINELA });
  escrever(root, "projects/carreira/.a0proj/project.json", { title: FORA_DA_LISTA, description: FORA_DA_LISTA });
  escrever(root, "projects/nao-listado/.a0proj/dono.txt", "matheus");
  escrever(root, "projects/nao-listado/.a0proj/project.json", { title: FORA_DA_LISTA });
  for (const d of DOCUMENTOS_PERMITIDOS) {
    const cita = d.chave === "requisitos" ? "\nVer /a0/usr/workdir/segundo_cerebro_correto/atual/setup_verified.txt.\n" : "\n";
    escrever(root, d.partes.join("/"), `# Documento sintético ${d.chave}\n\n## Seção A\ntexto${cita}## Seção B\nmais texto\n`);
  }
}
