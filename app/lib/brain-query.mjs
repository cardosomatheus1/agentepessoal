// Consulta seletiva sobre a projeção do Segundo Cérebro (pura: roda no navegador e no CLI).
// Interface fechada: função + fonte + registro + termo. Nada de caminho, dono ou parâmetro livre.
// Busca por palavra só ORDENA resultados ("busca textual"); vínculo só vem de metadado explícito.
// Roteiro: captura → validação → consulta → execução (não executada: escopo só leitura) → verificação.
import { buildBrainGraph, neighborsOf, normalizar } from "./brain-graph.mjs";

export const FUNCOES = Object.freeze({
  retomar: "Retomar contexto ou projeto",
  rotina: "Consultar uma rotina",
  prioridades: "Prioridades de agora",
  pauta: "Preparar pauta",
  registro: "Abrir um registro",
  fonte: "Ver uma fonte",
  buscar: "Buscar em todos os registros",
  onboarding: "Estado do onboarding",
});
export const FONTES = Object.freeze(["decisoes", "perfil", "fios", "contexto", "rotinas", "projetos", "documentos", "reunioes", "daily"]);
const CHAVES = ["funcao", "fonte", "registro", "termo"];
const REGISTRO = /^(decisao|fato|fio|contexto|documento|rotina|projeto|fonte):[A-Za-z0-9._@-]{1,120}$/;
const PRIORIDADE = { alta: 0, media: 1, "média": 1, baixa: 2 };
const BUSCA = "busca textual: contém o termo (só ordena; não é vínculo)";

export function validarConsulta(q) {
  if (!q || typeof q !== "object" || Array.isArray(q)) return { ok: false, erro: "Consulta inválida." };
  const extras = Object.keys(q).filter((k) => !CHAVES.includes(k));
  if (extras.length) return { ok: false, erro: `Parâmetro não aceito: ${extras.join(", ")}.` };
  if (!Object.hasOwn(FUNCOES, q.funcao)) return { ok: false, erro: "Função desconhecida." };
  if (q.fonte !== undefined && q.fonte !== "" && !FONTES.includes(q.fonte)) return { ok: false, erro: "Fonte desconhecida." };
  if (q.registro !== undefined && q.registro !== "" && (typeof q.registro !== "string" || !REGISTRO.test(q.registro))) return { ok: false, erro: "Registro inválido (use tipo:id)." };
  if (q.termo !== undefined && (typeof q.termo !== "string" || q.termo.length > 80 || /[\u0000-\u001f]/.test(q.termo))) return { ok: false, erro: "Termo inválido (até 80 caracteres)." };
  return { ok: true, consulta: { funcao: q.funcao, fonte: q.fonte || null, registro: q.registro || null, termo: (q.termo ?? "").trim() || null } };
}

const contem = (alvo, termo) => !!termo && normalizar(alvo).includes(normalizar(termo));
const temaCanonico = (s) => normalizar(s).replace(/[^a-z0-9.]+/g, "-").replace(/^-+|-+$/g, "");

function item(ref, tipo, rotulo, trecho, proveniencia, porque) {
  return { ref, tipo, rotulo, trecho: trecho ? String(trecho).slice(0, 600) : null, proveniencia, porque };
}
const itemDecisao = (d, porque) => item(`decisao:${d.id}`, "decisao", d.tema ?? `decisão ${d.id}`, d.valor, d.proveniencia, porque);
const itemFio = (f, porque) => item(`fio:${f.id}`, "fio", f.titulo ?? f.id, f.proximo_passo ? `Próximo passo registrado: ${f.proximo_passo}` : f.detalhe, f.proveniencia, porque);
const itemContexto = (c, porque) => item(`contexto:${c.id}`, "contexto", c.titulo, c.itens.map((i) => i.texto).join(" · "), c.proveniencia, porque);
const itemRotina = (r, porque) => item(`rotina:${r.id}`, "rotina", r.nome, r.descricao, r.proveniencia, porque);
const itemProjeto = (p, porque) => item(`projeto:${p.id}`, "projeto", p.titulo, p.descricao, p.proveniencia, porque);
const itemFato = (f, porque) => item(`fato:${f.id}`, "fato", `Ficha, entrada ${f.numero ?? f.id}`, f.texto, f.proveniencia, porque);
const itemDocumento = (d, porque) => item(`documento:${d.id}`, "documento", d.titulo, `${d.secoes.length} seções · ${d.bytes} bytes · dono: ${d.dono}`, d.proveniencia, porque);

function fonteEstado(brain, id) {
  const s = (brain.sources ?? []).find((x) => x.id === id);
  return s ? { id, estado: s.estado, codigo: s.codigo, impressao: s.impressao ?? null } : { id, estado: "indisponivel", codigo: "ausente", impressao: null };
}
function exigirFonte(brain, id, bloqueios, para) {
  const s = fonteEstado(brain, id);
  if (s.estado === "indisponivel") bloqueios.push({ fonte: id, motivo: `${para}: fonte indisponível (${s.codigo}).` });
  if (s.estado === "sem_contrato") bloqueios.push({ fonte: id, motivo: `${para}: não existe fonte canônica (lacuna).` });
  return s;
}
const ordenarPorPrioridade = (a, b) =>
  (PRIORIDADE[(a.prioridade ?? "media").toLowerCase()] ?? 1) - (PRIORIDADE[(b.prioridade ?? "media").toLowerCase()] ?? 1) ||
  String(a.prazo ?? "9999").localeCompare(String(b.prazo ?? "9999"));

export function acharRegistro(brain, ref) {
  const [tipo, ...resto] = ref.split(":");
  const id = resto.join(":");
  const listas = { decisao: brain.decisions, fato: brain.profile, fio: brain.threads, contexto: brain.contexts, documento: brain.documents, rotina: brain.routines, projeto: brain.projects, fonte: brain.sources };
  return (listas[tipo] ?? []).find((x) => String(x.id) === id) ?? null;
}

export function consultar(brain, entrada) {
  const v = validarConsulta(entrada);
  if (!v.ok) return { ok: false, erro: v.erro };
  const q = v.consulta;
  const itens = [];
  const bloqueios = [];
  const usadas = new Map();
  const usar = (id, para) => { const s = exigirFonte(brain, id, bloqueios, para); usadas.set(id, s); return s; };
  const vigentes = (brain.decisions ?? []).filter((d) => d.vigente);
  const naoVigentes = (brain.decisions ?? []).filter((d) => !d.vigente).length;
  const abertos = (brain.threads ?? []).filter((f) => f.emAberto);
  let resumo = "";
  let proximosPassos = [];

  if (q.funcao === "retomar") {
    if (!q.termo && !q.registro) return { ok: false, erro: "Retomar pede um termo ou um registro (projeto:… ou contexto:…)." };
    usar("contexto", "Contexto"); usar("decisoes", "Decisões"); usar("fios", "Fios"); usar("projetos", "Projetos"); usar("rotinas", "Rotinas");
    if (q.registro) {
      const r = acharRegistro(brain, q.registro);
      if (!r) bloqueios.push({ fonte: q.registro.split(":")[0], motivo: "Registro pedido não existe entre as fontes com dono comprovado." });
      else if (q.registro.startsWith("projeto:")) itens.push(itemProjeto(r, "registro pedido (projeto com dono.txt = matheus)"));
      else if (q.registro.startsWith("contexto:")) itens.push(itemContexto(r, "registro pedido (contexto autorizado)"));
    }
    if (q.termo) {
      for (const c of brain.contexts ?? []) if (contem(`${c.titulo} ${c.itens.map((i) => i.texto).join(" ")}`, q.termo)) itens.push(itemContexto(c, BUSCA));
      const tema = temaCanonico(q.termo);
      for (const d of vigentes) {
        if (d.tema && (d.tema === tema || d.tema.startsWith(`${tema}.`))) itens.push(itemDecisao(d, `metadado: tema "${d.tema}" está no assunto "${tema}"`));
        else if (contem(`${d.tema} ${d.valor} ${d.citacao}`, q.termo)) itens.push(itemDecisao(d, BUSCA));
      }
      for (const f of abertos) if (contem(`${f.titulo} ${f.detalhe} ${f.proximo_passo}`, q.termo)) itens.push(itemFio(f, `${BUSCA}; fio em aberto (contrato dos fios)`));
      for (const r of brain.routines ?? []) if (contem(`${r.nome} ${r.descricao}`, q.termo)) itens.push(itemRotina(r, BUSCA));
      for (const p of brain.projects ?? []) if (contem(`${p.titulo} ${p.descricao}`, q.termo)) itens.push(itemProjeto(p, BUSCA));
    }
    if (!(brain.projects ?? []).length) bloqueios.push({ fonte: "projetos", motivo: "Nenhum projeto com dono comprovado: retomada fica só no contexto e nos registros." });
    proximosPassos = itens.filter((i) => i.tipo === "fio").map((i) => ({ ref: i.ref, texto: acharRegistro(brain, i.ref)?.proximo_passo ?? null })).filter((p) => p.texto);
    resumo = `${itens.length} registro(s) para retomar; ${naoVigentes} decisão(ões) não vigentes ficaram de fora.`;
  } else if (q.funcao === "rotina") {
    usar("rotinas", "Rotinas");
    if (!q.registro || !q.registro.startsWith("rotina:")) return { ok: false, erro: "Consultar rotina pede registro rotina:<slug>." };
    const r = acharRegistro(brain, q.registro);
    if (!r) bloqueios.push({ fonte: "rotinas", motivo: "Rotina não encontrada na allowlist com dono aceito." });
    else {
      itens.push(itemRotina(r, "registro pedido"));
      resumo = `Rotina versão ${r.versao}: ${r.passos.length} passo(s), ${r.correcoes.length} correção(ões) do usuário.`;
      for (const k of r.secoesAusentes) bloqueios.push({ fonte: "rotinas", motivo: `Seção ausente na rotina: ${k}.` });
    }
  } else if (q.funcao === "prioridades") {
    usar("fios", "Fios"); usar("decisoes", "Decisões");
    for (const f of [...abertos].sort(ordenarPorPrioridade).slice(0, 8)) itens.push(itemFio(f, `contrato dos fios: em aberto, prioridade ${f.prioridade ?? "média (padrão)"}${f.prazo ? `, prazo ${f.prazo}` : ""}`));
    for (const d of vigentes.filter((x) => x.tipo === "proibicao")) itens.push(itemDecisao(d, "metadado: proibição vigente (limite para qualquer prioridade)"));
    bloqueios.push({ fonte: null, motivo: "Sem fonte de estratégia/objetivos: a ordem vem só da prioridade e do prazo gravados nos fios." });
    proximosPassos = abertos.sort(ordenarPorPrioridade).slice(0, 8).filter((f) => f.proximo_passo).map((f) => ({ ref: `fio:${f.id}`, texto: f.proximo_passo }));
    resumo = `${Math.min(8, abertos.length)} de ${abertos.length} fio(s) em aberto, na ordem do contrato (prioridade, prazo).`;
  } else if (q.funcao === "pauta") {
    usar("fios", "Fios"); usar("contexto", "Contexto"); usar("decisoes", "Decisões");
    const lista = q.termo ? abertos.filter((f) => contem(`${f.titulo} ${f.detalhe} ${f.proximo_passo}`, q.termo)) : abertos;
    for (const f of [...lista].sort(ordenarPorPrioridade)) itens.push(itemFio(f, q.termo ? `${BUSCA}; ponto em aberto` : "ponto em aberto (contrato dos fios)"));
    for (const c of brain.contexts ?? []) if (q.termo && contem(`${c.titulo} ${c.itens.map((i) => i.texto).join(" ")}`, q.termo)) itens.push(itemContexto(c, BUSCA));
    bloqueios.push({ fonte: null, motivo: "Sem fonte de pessoas-chave: participantes e responsáveis ficam pendentes (o campo 'dono' do fio é quem age, não um papel confirmado)." });
    resumo = `${itens.filter((i) => i.tipo === "fio").length} ponto(s) de pauta a partir dos fios em aberto.`;
  } else if (q.funcao === "registro") {
    if (!q.registro) return { ok: false, erro: "Abrir registro pede registro tipo:id." };
    const r = acharRegistro(brain, q.registro);
    if (!r) bloqueios.push({ fonte: q.registro.split(":")[0], motivo: "Registro não encontrado." });
    else {
      const tipo = q.registro.split(":")[0];
      const f = { decisao: itemDecisao, fio: itemFio, contexto: itemContexto, rotina: itemRotina, projeto: itemProjeto, fato: itemFato, documento: itemDocumento }[tipo];
      if (f) itens.push(f(r, "registro pedido"));
      const g = buildBrainGraph(brain);
      for (const n of neighborsOf(g, q.registro)) itens.push(item(n.outro, n.outro.split(":")[0], g.nodes.find((x) => x.id === n.outro)?.rotuloCompleto ?? n.outro, null, n.edge.evidencia, `relação explícita: ${n.edge.relacao} (${n.direcao})`));
    }
  } else if (q.funcao === "fonte") {
    if (!q.fonte) return { ok: false, erro: "Ver fonte pede o nome da fonte." };
    const s = usar(q.fonte, "Fonte");
    const mapa = { decisoes: [brain.decisions, itemDecisao], perfil: [brain.profile, itemFato], fios: [brain.threads, itemFio], contexto: [brain.contexts, itemContexto], rotinas: [brain.routines, itemRotina], projetos: [brain.projects, itemProjeto], documentos: [brain.documents, itemDocumento] }[q.fonte];
    if (mapa) for (const x of mapa[0] ?? []) itens.push(mapa[1](x, "registro desta fonte"));
    resumo = `Fonte ${q.fonte}: ${s.estado} (${s.codigo}), ${itens.length} registro(s).`;
  } else if (q.funcao === "buscar") {
    if (!q.termo) return { ok: false, erro: "Buscar pede um termo." };
    const todos = [
      ...(brain.decisions ?? []).map((d) => [itemDecisao(d, BUSCA), `${d.tema} ${d.valor} ${d.citacao}`, d.tema]),
      ...(brain.threads ?? []).map((f) => [itemFio(f, BUSCA), `${f.titulo} ${f.detalhe} ${f.proximo_passo}`, f.titulo]),
      ...(brain.profile ?? []).map((f) => [itemFato(f, BUSCA), f.texto, ""]),
      ...(brain.contexts ?? []).map((c) => [itemContexto(c, BUSCA), `${c.titulo} ${c.itens.map((i) => i.texto).join(" ")}`, c.titulo]),
      ...(brain.routines ?? []).map((r) => [itemRotina(r, BUSCA), `${r.nome} ${r.descricao} ${r.passos.join(" ")}`, r.nome]),
      ...(brain.projects ?? []).map((p) => [itemProjeto(p, BUSCA), `${p.titulo} ${p.descricao}`, p.titulo]),
      ...(brain.documents ?? []).map((d) => [itemDocumento(d, BUSCA), `${d.titulo} ${d.secoes.map((s) => s.titulo).join(" ")}`, d.titulo]),
    ];
    const t = normalizar(q.termo);
    const pont = ([, alvo, titulo]) => (normalizar(titulo).includes(t) ? 10 : 0) + normalizar(alvo).split(t).length - 1;
    for (const x of todos.filter((x) => contem(x[1], q.termo)).sort((a, b) => pont(b) - pont(a) || a[0].ref.localeCompare(b[0].ref))) itens.push(x[0]);
    for (const id of FONTES) usadas.set(id, fonteEstado(brain, id));
    resumo = `${itens.length} registro(s) contêm "${q.termo}". Ordem por ocorrência; não indica relação entre eles.`;
  } else if (q.funcao === "onboarding") {
    usar("perfil", "Ficha"); usar("decisoes", "Decisões"); usar("rotinas", "Rotinas");
    const o = brain.proposals?.onboarding;
    const todas = [...(o?.negocio ?? []), ...(o?.pessoal ?? [])];
    for (const s of todas) itens.push(item(`onboarding:${s.id}`, "onboarding", s.titulo, `${s.estado} · destino: ${s.destino} · ${s.motivo}`, null, "proposta não aprovada (nada foi promovido)"));
    resumo = `${todas.filter((s) => s.estado === "pendente").length} pendente(s), ${todas.filter((s) => s.estado === "parcial").length} parcial(is), 0 aprovada(s).`;
  }

  const conflitos = (brain.conflicts ?? []).filter((c) => c.registros.some((r) => itens.some((i) => i.ref === r)));
  return { ok: true, consulta: q, rotulo: FUNCOES[q.funcao], estado: bloqueios.length ? (itens.length ? "parcial" : "bloqueado") : "ok", resumo, itens, proximosPassos, bloqueios, conflitos, fontesUsadas: [...usadas.values()], carregadoEm: brain.fetchedAt };
}

// Roteiro reutilizável. Neste escopo nunca executa: prepara a proposta, mostra o que exige aprovação e como verificar.
export function roteiro(brain, resultado) {
  if (!resultado?.ok) return null;
  const rot = resultado.consulta.registro?.startsWith("rotina:") ? acharRegistro(brain, resultado.consulta.registro) : null;
  const regras = (brain.decisions ?? []).filter((d) => d.vigente && (d.tipo === "proibicao" || d.tipo === "permissao"));
  const indisponiveis = resultado.fontesUsadas.filter((f) => f.estado !== "ok" && f.estado !== "vazia");
  return [
    { etapa: "captura", estado: "feito", detalhe: `Pedido: ${resultado.rotulo}${resultado.consulta.termo ? ` · termo "${resultado.consulta.termo}"` : ""}${resultado.consulta.registro ? ` · ${resultado.consulta.registro}` : ""}${resultado.consulta.fonte ? ` · fonte ${resultado.consulta.fonte}` : ""}.`, evidencias: [`carga das fontes em ${resultado.carregadoEm}`] },
    {
      etapa: "validacao",
      estado: indisponiveis.length || resultado.conflitos.length || resultado.bloqueios.length ? "atencao" : "feito",
      detalhe: indisponiveis.length ? `Fontes que bloqueiam parte da resposta: ${indisponiveis.map((f) => `${f.id} (${f.codigo})`).join(", ")}.` : "Fontes usadas disponíveis; dono fixo matheus; nada fora da allowlist.",
      evidencias: [...resultado.bloqueios.map((b) => b.motivo), ...resultado.conflitos.map((c) => `diagnóstico (não autoritativo): ${c.detalhe}`)],
      aprovacoes: [
        ...(rot?.aprovacao ? [{ ref: `rotina:${rot.id}`, texto: rot.aprovacao }] : []),
        ...regras.map((d) => ({ ref: `decisao:${d.id}`, texto: `${d.tipo === "proibicao" ? "Proibição" : "Permissão"} vigente: ${d.valor ?? d.tema}` })),
      ],
    },
    { etapa: "consulta", estado: resultado.itens.length ? "feito" : "vazio", detalhe: resultado.resumo, evidencias: resultado.itens.map((i) => i.ref) },
    {
      etapa: "execucao",
      estado: "nao_executado",
      detalhe: "Escopo somente leitura: nada foi enviado, gravado ou agendado. A proposta abaixo só vale depois da aprovação exigida, pelo canal canônico.",
      proposta: rot ? rot.passos.map((p, i) => `${i + 1}. ${p}`) : resultado.proximosPassos.map((p) => `${p.texto} (${p.ref})`),
      entrega: rot?.entregar ?? null,
    },
    { etapa: "verificacao", estado: "pendente", detalhe: rot?.verificar ? `Critério da rotina: ${rot.verificar}` : "Recarregar as fontes e conferir que as impressões não mudaram e os registros citados continuam lá.", evidencias: [] },
  ];
}

// Verificação real: compara a carga usada com uma nova leitura das fontes canônicas.
export function verificar(resultado, recarga) {
  const fontes = resultado.fontesUsadas.map((f) => {
    const depois = fonteEstado(recarga, f.id);
    return { id: f.id, antes: f.impressao, depois: depois.impressao, igual: f.impressao === depois.impressao && f.estado === depois.estado };
  });
  const refs = resultado.itens.map((i) => i.ref).filter((r) => !r.startsWith("onboarding:"));
  const presentes = refs.filter((r) => acharRegistro(recarga, r));
  const ok = fontes.every((f) => f.igual) && presentes.length === refs.length;
  return {
    estado: ok ? "verificado" : "divergente",
    detalhe: ok ? "Fontes recarregadas sem mudança; todos os registros citados continuam presentes. Nada foi gravado." : "As fontes mudaram entre a consulta e a verificação: refaça a consulta antes de agir.",
    fontes,
    registros: { citados: refs.length, presentes: presentes.length },
    verificadoEm: recarga.fetchedAt,
  };
}
