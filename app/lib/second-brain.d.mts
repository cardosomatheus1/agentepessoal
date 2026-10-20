export type FonteId = "regras" | "contexto" | "perfil" | "decisoes" | "pendencias" | "assuntos" | "reunioes" | "notas" | "documentos" | "projetos";

export interface Proveniencia {
  fonte: FonteId;
  fonteRotulo: string;
  dono: string;
  localizador?: string | null;
  citacao?: string | null;
  origem?: string | null;
  em?: string | null;
  linha?: number;
  arquivoAtualizadoEm: string | null;
}

/** Campos que todo item da Pasta carrega. */
export interface ItemPasta {
  /** tipo:id, a referência usada em `liga`, no mapa e na consulta. */
  ref: string;
  /** Pasta/arquivo (sem .md): o alvo de um [[link]]. */
  nota: string | null;
  area: string;
}

export interface Decisao extends ItemPasta {
  id: string;
  tema: string | null;
  tipo: string | null;
  valor: string | null;
  citacao: string | null;
  origem: string | null;
  por: string | null;
  em: string | null;
  estado: string;
  valido_ate: string | null;
  estadoEfetivo: string;
  vigente: boolean;
  fim_em: string | null;
  substitui: string | null;
  substituida_por: string | null;
  motivo: string | null;
  liga: string[];
  proveniencia: Proveniencia;
}

export interface Ligacao {
  alvo: string;
  rotulo: string | null;
}

/** Pendência (o que falta o Matheus fazer). */
export interface Fio extends ItemPasta {
  id: string;
  titulo: string | null;
  detalhe: string | null;
  fontes: string[];
  dono: string | null;
  prazo: string | null;
  prioridade: string | null;
  proximo_passo: string | null;
  ligacoes: Ligacao[];
  estado: string | null;
  adiar_ate: string | null;
  emAberto: boolean;
  criado: string | null;
  atualizado: string | null;
  liga: string[];
  proveniencia: Proveniencia;
}
export type Pendencia = Fio;

export interface Assunto extends ItemPasta {
  id: string;
  titulo: string;
  onde_parou: string | null;
  estado: string;
  emAndamento: boolean;
  citacao: string | null;
  origem: string | null;
  criado: string | null;
  atualizado: string | null;
  historico: { em: string | null; nota: string | null }[];
  liga: string[];
  proveniencia: Proveniencia;
}

export interface FatoPerfil {
  id: string;
  numero: number;
  texto: string;
  area: string;
  proveniencia: Proveniencia;
}

export interface Secao {
  titulo: string | null;
  linha: number;
  itens: string[];
}

export interface SecaoContexto extends ItemPasta {
  id: string;
  titulo: string;
  rotulo: string;
  estado: "validado" | "pendente";
  secoes: Secao[];
  resumo: string | null;
  aprovado: string | null;
  validadoEm: string | null;
  proveniencia: Proveniencia;
}

/** Nota livre: reunião, nota do dia, documento ou projeto. */
export interface Nota extends ItemPasta {
  id: string;
  titulo: string;
  data: string | null;
  resumo: string | null;
  secoes: Secao[];
  bytes: number;
  linhas: number;
  sha256: string;
  liga: string[];
  proveniencia: Proveniencia;
}
export type Documento = Nota;
export type Projeto = Nota;

export interface Link {
  de: string;
  para: string;
  vias: ("liga" | "wiki" | "ligacoes")[];
  alvo: string | null;
  resolvido: boolean;
  evidencia: { fonte: string; registro: string; campo: string; localizador: string | null };
}

export interface Conexoes {
  nodes: { id: string; tipo: string; rotulo: string }[];
  edges: { de: string; para: string; rotulo: string | null; evidencia: { fonte: string; registro: string; campo: string } }[];
}

export type CodigoFonte = "ok" | "vazia" | "pendente" | "ausente" | "link" | "grande" | "erro" | "invalida" | "ilegivel" | "formato_antigo" | "truncada" | "parcial" | "orcamento";

export interface Fonte {
  id: FonteId;
  rotulo: string;
  dono: string;
  estado: "ok" | "vazia" | "indisponivel";
  codigo: CodigoFonte;
  localizador: string | null;
  arquivoAtualizadoEm: string | null;
  registros: number;
  excluidos: number;
  truncados: number;
  impressao: string | null;
  /** Só os arquivos com problema (ou fora do padrão de nome). */
  arquivos: { chave: string | null; codigo: string }[];
  lidos?: number;
}

export interface Aviso {
  fonte: string;
  codigo: string;
  mensagem: string;
}

export interface Lacuna {
  id: string;
  fonte: FonteId | null;
  motivo: string;
}

export interface Diagnostico {
  tipo: string;
  fonte: string;
  registros: string[];
  regra: string;
  detalhe: string;
  autoritativo: false;
}

export interface Cobertura {
  fontes: number;
  fontesOk: number;
  fontesIndisponiveis: number;
  registros: number;
  excluidos: number;
  textosCortados: number;
  ligacoes: number;
  nota: string;
}

export interface SegundoCerebro {
  owner: "matheus";
  fetchedAt: string;
  pasta: { migrada: boolean };
  rules: { titulo: string | null; regras: string[]; proveniencia: Proveniencia } | null;
  areas: string[];
  decisions: Decisao[];
  threads: Fio[];
  subjects: Assunto[];
  profile: FatoPerfil[];
  contexts: SecaoContexto[];
  meetings: Nota[];
  daily: Nota[];
  documents: Nota[];
  projects: Nota[];
  /** Pasta/arquivo -> tipo:id, para seguir um [[link]]. */
  index: Record<string, string>;
  links: Link[];
  connections: Conexoes;
  sources: Fonte[];
  warnings: Aviso[];
  gaps: Lacuna[];
  conflicts: Diagnostico[];
  diagnostics: Diagnostico[];
  coverage: Cobertura;
}

export interface AdapterReply {
  status: number;
  body: SegundoCerebro | { erro: string };
  headers: Record<string, string>;
}

export const OWNER: "matheus";
export const DEFAULT_DATA_ROOT: string;
export const PASTA: readonly string[];
export const MAX_BYTES: number;
export const MAX_ARQUIVOS: number;
export const MAX_TOTAL_BYTES: number;
export const FICHA_MARCA: string;
export const PENDENTE: string;
export const MARCA_MIGRADO: string;
export const OCULTA: string;
export const CONTEXTO: readonly (readonly [string, string])[];
export const SECURITY_HEADERS: Readonly<Record<string, string>>;
export class Ilegivel extends Error {}
export function redact(value: unknown): string;
export function parseFrontmatter(conteudo: string, nome?: string): { campos: Record<string, unknown>; corpo: string };
export function wikiLinks(conteudo: string): string[];
export function checkBearer(authorization: string | null | undefined, digestHex: string): boolean;
export function loadSecondBrain(opts: { root: string; now?: Date }): Promise<SegundoCerebro>;
export function handleSecondBrainRequest(
  request: Request,
  env?: Record<string, string | undefined>,
  now?: Date,
): Promise<AdapterReply>;
