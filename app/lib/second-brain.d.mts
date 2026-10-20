export type FonteId = "decisoes" | "perfil" | "fios" | "contexto" | "rotinas" | "projetos" | "documentos" | "reunioes" | "daily";

export interface Proveniencia {
  fonte: FonteId;
  fonteRotulo: string;
  dono: string;
  localizador?: string;
  citacao?: string | null;
  origem?: string | null;
  em?: string | null;
  linha?: number;
  versao?: string;
  autorizacao?: string;
  donoProva?: string;
  arquivoAtualizadoEm: string | null;
}

export interface Decisao {
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
  proveniencia: Proveniencia;
}

export interface Ligacao {
  alvo: string;
  rotulo: string | null;
}

export interface Fio {
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
  proveniencia: Proveniencia;
}

export interface FatoPerfil {
  id: string;
  numero: number;
  texto: string;
  proveniencia: Proveniencia;
}

export interface SecaoContexto {
  id: string;
  titulo: string;
  itens: { linha: number; texto: string }[];
  linhas: [number, number];
  proveniencia: Proveniencia;
}

export interface Rotina {
  id: string;
  nome: string | null;
  descricao: string | null;
  gatilhos: string[];
  dono: string | null;
  donoNota: string;
  versao: string;
  quando_usar: string | null;
  entradas: string | null;
  passos: string[];
  verificar: string | null;
  entregar: string | null;
  aprovacao: string | null;
  secoesAusentes: string[];
  correcoes: { linha: number; data: string | null; por: string | null; texto: string | null }[];
  pedeReescrita: boolean;
  proveniencia: Proveniencia;
}

export interface Projeto {
  id: string;
  titulo: string;
  descricao: string | null;
  instrucoes: string | null;
  cor: string | null;
  proveniencia: Proveniencia;
}

export interface Documento {
  id: string;
  titulo: string;
  dono: string;
  bytes: number;
  linhas: number;
  sha256: string;
  secoes: { linha: number; titulo: string | null }[];
  citaDocumentos: string[];
  proveniencia: Proveniencia;
}

export interface Conexoes {
  nodes: { id: string; tipo: "fio" | "texto"; rotulo: string }[];
  edges: { de: string; para: string; rotulo: string | null; evidencia: { fonte: "fios"; fioId: string; em: string | null } }[];
}

export type CodigoFonte = "ok" | "vazia" | "ausente" | "link" | "grande" | "erro" | "invalida" | "formato_antigo" | "truncada" | "parcial" | "sem_contrato";

export interface Fonte {
  id: FonteId;
  rotulo: string;
  dono: string;
  estado: "ok" | "vazia" | "indisponivel" | "sem_contrato";
  codigo: CodigoFonte;
  localizador: string | null;
  arquivoAtualizadoEm: string | null;
  registros: number;
  excluidos: number;
  truncados: number;
  impressao: string | null;
  arquivos: { chave: string; codigo: string }[];
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
  fonte: FonteId;
  registros: string[];
  regra: string;
  detalhe: string;
  autoritativo: false;
}

export interface SecaoOnboarding {
  id: string;
  titulo: string;
  publicado: string;
  estado: "pendente" | "parcial";
  destino: string;
  evidencias: string[];
  motivo: string;
  proposta: string;
  aprovado: false;
  promovido: false;
}

export interface Cobertura {
  fontes: number;
  fontesOk: number;
  fontesIndisponiveis: number;
  fontesSemContrato: number;
  registros: number;
  excluidosPorDono: number;
  textosCortados: number;
  nota: string;
}

export interface SegundoCerebro {
  owner: "matheus";
  fetchedAt: string;
  decisions: Decisao[];
  threads: Fio[];
  profile: FatoPerfil[];
  contexts: SecaoContexto[];
  documents: Documento[];
  projects: Projeto[];
  routines: Rotina[];
  meetings: never[];
  daily: never[];
  connections: Conexoes;
  sources: Fonte[];
  warnings: Aviso[];
  gaps: Lacuna[];
  conflicts: Diagnostico[];
  diagnostics: Diagnostico[];
  proposals: { onboarding: { negocio: SecaoOnboarding[]; pessoal: SecaoOnboarding[]; nota: string } };
  coverage: Cobertura;
}

export interface AdapterReply {
  status: number;
  body: SegundoCerebro | { erro: string };
  headers: Record<string, string>;
}

export const OWNER: "matheus";
export const DEFAULT_DATA_ROOT: string;
export const MAX_BYTES: number;
export const FICHA_MARCA: string;
export const CONTEXTO_CHAT: string;
export const PROJETOS_PERMITIDOS: readonly string[];
export const ROTINAS_PERMITIDAS: readonly string[];
export const DOCUMENTOS_PERMITIDOS: readonly { chave: string; rotulo: string; dono: string; partes: string[] }[];
export const SECURITY_HEADERS: Readonly<Record<string, string>>;
export function redact(value: unknown): string;
export function checkBearer(authorization: string | null | undefined, digestHex: string): boolean;
export function buildConnections(threads: Fio[]): Conexoes;
export function loadSecondBrain(opts: { root: string; now?: Date }): Promise<SegundoCerebro>;
export function handleSecondBrainRequest(
  request: Request,
  env?: Record<string, string | undefined>,
  now?: Date,
): Promise<AdapterReply>;
