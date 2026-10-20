// Consulta seletiva sobre a projeção do Segundo Cérebro (pura: roda no navegador e no CLI). Fonte única: a Pasta.
// Interface fechada: função + fonte + registro + termo + área. Nada de caminho, dono ou parâmetro livre.
// Busca por palavra só ORDENA resultados ("busca textual"); vínculo só vem de ligação gravada (liga, [[link]]).
// Roteiro: captura → validação → consulta → execução (não executada: escopo só leitura) → verificação.
import { buildBrainGraph, neighborsOf, normalizar } from "./brain-graph.mjs";

export const FUNCOES = Object.freeze({
  retomar: "Retomar um assunto ou contexto",
  assuntos: "Assuntos em andamento (onde parou)",
  prioridades: "Prioridades de agora",
  pauta: "Preparar pauta",
  registro: "Abrir um registro",
  fonte: "Ver uma fonte",
  buscar: "Buscar em todos os registros",
  contexto: "Contexto validado e pendente",
});
export const FONTES = Object.freeze(["regras", "contexto", "perfil", "decisoes", "pendencias", "assuntos", "reunioes", "notas", "documentos", "projetos"]);
const CHAVES = ["funcao", "fonte", "registro", "termo", "area"];
const REGISTRO = /^(decisao|fato|pendencia|assunto|contexto|reuniao|nota|documento|projeto|fonte):[A-Za-z0-9._@([-][A-Za-z0-9 ._@()[\]-]{0,119}$/;
const PRIORIDADE = { alta: 0, media: 1, "média": 1, baixa: 2 };
const BUSCA = "busca textual: contém o termo (só ordena; não é vínculo)";

export function validarConsulta(q) {
  if (!q || typeof q !== "object" || Array.isArray(q)) return { ok: false, erro: "Consulta inválida." };
  const extras = Object.keys(q).filter((k) => !CHAVES.includes(k));
  if (extras.length) return { ok: false, erro: `Parâmetro não aceito: ${extras.join(", ")}.` };
  if (!Object.hasOwn(FUNCOES, q.funcao)) return { ok: false, erro: "Função desconhecida." };
  if (q.fonte !== undefined && q.fonte !== "" && !FONTES.includes(q.fonte)) return { ok: false, erro: "Fonte desconhecida." };
  if (q.registro !== undefined && q.registro !== "" && (typeof q.registro !== "string" || !REGISTRO.test(q.registro) || q.registro.includes(".."))) return { ok: false, erro: "Registro inválido (use tipo:id)." };
  if (q.termo !== undefined && (typeof q.termo !== "string" || q.termo.length > 80 || /[\u0000-\u001f]/.test(q.termo))) return { ok: false, erro: "Termo inválido (até 80 caracteres)." };
  if (q.area !== undefined && q.area !== "" && (typeof q.area !== "string" || q.area.length > 80 || /[\u0000-\u001f]/.test(q.area))) return { ok: false, erro: "Área inválida." };
  return { ok: true, consulta: { funcao: q.funcao, fonte: q.fonte || null, registro: q.registro || null, termo: (q.termo ?? "").trim() || null, area: (q.area ?? "").trim() || null } };
}

const contem = (alvo, termo) => !!termo && normalizar(alvo).includes(normalizar(termo));
const temaCanonico = (s) => normalizar(s).replace(/[^a-z0-9.]+/g, "-").replace(/^-+|-+$/g, "");
const textoSecoes = (secoes) => (secoes ?? []).flatMap((s) => [s.titulo ?? "", ...s.itens]).join(" ");

function item(ref, tipo, rotulo, trecho, proveniencia, porque, area = null) {
  return { ref, tipo, rotulo, trecho: trecho ? String(trecho).slice(0, 600) : null, area, proveniencia, porque };
}
const itemDecisao = (d, porque) => item(`decisao:${d.id}`, "decisao", d.tema ?? `decisão ${d.id}`, d.valor, d.proveniencia, porque, d.area);
const itemPendencia = (f, porque) => item(`pendencia:${f.id}`, "pendencia", f.titulo ?? f.id, f.proximo_passo ? `Próximo passo registrado: ${f.proximo_passo}` : f.detalhe, f.proveniencia, porque, f.area);
const itemAssunto = (a, porque) => item(`assunto:${a.id}`, "assunto", a.titulo, a.onde_parou ? `Onde parou: ${a.onde_parou}` : "Onde parou: (ainda nada)", a.proveniencia, porque, a.area);
const itemContexto = (c, porque) => item(`contexto:${c.id}`, "contexto", `${c.titulo} (${c.estado})`, textoSecoes(c.secoes) || c.resumo, c.proveniencia, porque, c.area);
const itemFato = (f, porque) => item(`fato:${f.id}`, "fato", `Perfil, entrada ${f.numero ?? f.id}`, f.texto, f.proveniencia, porque, f.area);
const itemNota = (tipo) => (n, porque) => item(`${tipo}:${n.id}`, tipo, n.titulo, n.resumo, n.proveniencia, porque, n.area);
const itemReuniao = itemNota("reuniao");
const itemDia = itemNota("nota");
const itemDocumento = itemNota("documento");
const itemProjeto = itemNota("projeto");

function fonteEstado(brain, id) {
  const s = (brain.sources ?? []).find((x) => x.id === id);
  return s ? { id, estado: s.estado, codigo: s.codigo, impressao: s.impressao ?? null } : { id, estado: "indisponivel", codigo: "ausente", impressao: null };
}
function exigirFonte(brain, id, bloqueios, para) {
  const s = fonteEstado(brain, id);
  if (s.estado === "indisponivel") bloqueios.push({ fonte: id, motivo: `${para}: fonte indisponível (${s.codigo}).` });
  return s;
}
const ordenarPorPrioridade = (a, b) =>
  (PRIORIDADE[(a.prioridade ?? "media").toLowerCase()] ?? 1) - (PRIORIDADE[(b.prioridade ?? "media").toLowerCase()] ?? 1) ||
  String(a.prazo ?? "9999").localeCompare(String(b.prazo ?? "9999"));

const LISTAS = { decisao: "decisions", fato: "profile", pendencia: "threads", assunto: "subjects", contexto: "contexts", reuniao: "meetings", nota: "daily", documento: "documents", projeto: "projects", fonte: "sources" };

export function acharRegistro(brain, ref) {
  const [tipo, ...resto] = ref.split(":");
  const id = resto.join(":");
  return (brain[LISTAS[tipo]] ?? []).find((x) => String(x.id) === id) ?? null;
}

export function consultar(brain, entrada) {
  const v = validarConsulta(entrada);
  if (!v.ok) return { ok: false, erro: v.erro };
  const q = v.consulta;
  const itens = [];
  const bloqueios = [];
  const usadas = new Map();
  const usar = (id, para) => { const s = exigirFonte(brain, id, bloqueios, para); usadas.set(id, s); return s; };
  // Área: filtra os itens das coleções e notas; Contexto e perfil não são filtrados (valem para todas as áreas).
  const naArea = (x) => !q.area || x.area === q.area;
  const lista = (k) => (brain[k] ?? []).filter(naArea);
  const decisoes = lista("decisions");
  const vigentes = decisoes.filter((d) => d.vigente);
  const naoVigentes = decisoes.filter((d) => !d.vigente).length;
  const abertos = lista("threads").filter((f) => f.emAberto);
  const assuntos = lista("subjects");
  const andamento = assuntos.filter((a) => a.emAndamento).sort((a, b) => String(b.atualizado ?? "").localeCompare(String(a.atualizado ?? "")));
  const contextos = brain.contexts ?? [];
  const ctx = (id) => contextos.find((c) => c.id === id);
  let resumo = "";
  let proximosPassos = [];

  if (q.funcao === "retomar") {
    if (!q.termo && !q.registro) return { ok: false, erro: "Retomar pede um termo ou um registro (assunto:…, contexto:… ou projeto:…)." };
    usar("assuntos", "Assuntos"); usar("contexto", "Contexto"); usar("decisoes", "Decisões"); usar("pendencias", "Pendências");
    if (q.registro) {
      const r = acharRegistro(brain, q.registro);
      const tipo = q.registro.split(":")[0];
      if (!r) bloqueios.push({ fonte: tipo, motivo: "Registro pedido não está na Pasta." });
      else {
        const f = { assunto: itemAssunto, contexto: itemContexto, projeto: itemProjeto, reuniao: itemReuniao, decisao: itemDecisao, pendencia: itemPendencia, documento: itemDocumento, nota: itemDia }[tipo];
        if (f) itens.push(f(r, "registro pedido"));
        const g = buildBrainGraph(brain);
        for (const n of neighborsOf(g, q.registro)) {
          if (n.edge.relacao === "proveniencia") continue;
          const outro = acharRegistro(brain, n.outro);
          if (outro && n.outro.startsWith("assunto:")) itens.push(itemAssunto(outro, `ligação gravada: ${n.edge.relacao}`));
          else if (outro && n.outro.startsWith("pendencia:") && outro.emAberto) itens.push(itemPendencia(outro, `ligação gravada: ${n.edge.relacao}`));
          else if (outro && n.outro.startsWith("decisao:") && outro.vigente) itens.push(itemDecisao(outro, `ligação gravada: ${n.edge.relacao}`));
        }
      }
    }
    if (q.termo) {
      for (const a of assuntos) if (contem(`${a.titulo} ${a.onde_parou} ${a.historico.map((h) => h.nota).join(" ")}`, q.termo)) itens.push(itemAssunto(a, `${BUSCA}; assunto ${a.estado}`));
      for (const c of contextos) if (contem(`${c.titulo} ${textoSecoes(c.secoes)}`, q.termo)) itens.push(itemContexto(c, BUSCA));
      const tema = temaCanonico(q.termo);
      for (const d of vigentes) {
        if (d.tema && (d.tema === tema || d.tema.startsWith(`${tema}.`))) itens.push(itemDecisao(d, `metadado: tema "${d.tema}" está no assunto "${tema}"`));
        else if (contem(`${d.tema} ${d.valor} ${d.citacao}`, q.termo)) itens.push(itemDecisao(d, BUSCA));
      }
      for (const f of abertos) if (contem(`${f.titulo} ${f.detalhe} ${f.proximo_passo}`, q.termo)) itens.push(itemPendencia(f, `${BUSCA}; pendência em aberto`));
      for (const p of lista("projects")) if (contem(`${p.titulo} ${textoSecoes(p.secoes)}`, q.termo)) itens.push(itemProjeto(p, BUSCA));
      for (const m of lista("meetings")) if (contem(`${m.titulo} ${textoSecoes(m.secoes)}`, q.termo)) itens.push(itemReuniao(m, BUSCA));
    }
    const unicos = new Map(itens.map((i) => [i.ref, i]));
    itens.splice(0, itens.length, ...unicos.values());
    proximosPassos = [
      ...itens.filter((i) => i.tipo === "assunto").map((i) => ({ ref: i.ref, texto: acharRegistro(brain, i.ref)?.onde_parou ? `Retomar de onde parou: ${acharRegistro(brain, i.ref).onde_parou}` : null })),
      ...itens.filter((i) => i.tipo === "pendencia").map((i) => ({ ref: i.ref, texto: acharRegistro(brain, i.ref)?.proximo_passo ?? null })),
    ].filter((p) => p.texto);
    resumo = `${itens.length} registro(s) para retomar; ${naoVigentes} decisão(ões) não vigentes ficaram de fora.`;
  } else if (q.funcao === "assuntos") {
    usar("assuntos", "Assuntos");
    for (const a of andamento) itens.push(itemAssunto(a, `assunto ${a.estado} (assuntos.py: não encerrado)`));
    proximosPassos = andamento.filter((a) => a.onde_parou).map((a) => ({ ref: `assunto:${a.id}`, texto: `Retomar de onde parou: ${a.onde_parou}` }));
    resumo = `${andamento.length} assunto(s) em andamento ou parados; ${assuntos.length - andamento.length} encerrado(s) ficaram de fora.`;
  } else if (q.funcao === "prioridades") {
    usar("pendencias", "Pendências"); usar("decisoes", "Decisões"); usar("contexto", "Contexto");
    for (const f of [...abertos].sort(ordenarPorPrioridade).slice(0, 8)) itens.push(itemPendencia(f, `pendência em aberto, prioridade ${f.prioridade ?? "média (padrão)"}${f.prazo ? `, prazo ${f.prazo}` : ""}`));
    for (const d of vigentes.filter((x) => x.tipo === "proibicao")) itens.push(itemDecisao(d, "metadado: proibição vigente (limite para qualquer prioridade)"));
    const estrategia = ctx("estrategia");
    if (estrategia?.estado === "validado") itens.push(itemContexto(estrategia, "Contexto/estrategia.md validado: as metas valem para ordenar"));
    else bloqueios.push({ fonte: "contexto", motivo: "Estratégia pendente de validação: a ordem vem só da prioridade e do prazo gravados nas pendências." });
    proximosPassos = [...abertos].sort(ordenarPorPrioridade).slice(0, 8).filter((f) => f.proximo_passo).map((f) => ({ ref: `pendencia:${f.id}`, texto: f.proximo_passo }));
    resumo = `${Math.min(8, abertos.length)} de ${abertos.length} pendência(s) em aberto, na ordem (prioridade, prazo).`;
  } else if (q.funcao === "pauta") {
    usar("pendencias", "Pendências"); usar("assuntos", "Assuntos"); usar("contexto", "Contexto"); usar("decisoes", "Decisões");
    const pend = q.termo ? abertos.filter((f) => contem(`${f.titulo} ${f.detalhe} ${f.proximo_passo}`, q.termo)) : abertos;
    for (const f of [...pend].sort(ordenarPorPrioridade)) itens.push(itemPendencia(f, q.termo ? `${BUSCA}; ponto em aberto` : "ponto em aberto (pendência)"));
    for (const a of andamento) if (!q.termo || contem(`${a.titulo} ${a.onde_parou}`, q.termo)) itens.push(itemAssunto(a, q.termo ? `${BUSCA}; assunto em discussão` : "assunto em discussão"));
    const pessoas = ctx("pessoas-chave");
    if (pessoas?.estado === "validado") itens.push(itemContexto(pessoas, "Contexto/pessoas-chave.md validado: quem participa"));
    else bloqueios.push({ fonte: "contexto", motivo: "Pessoas-chave pendente de validação: participantes e responsáveis ficam em aberto (o 'dono' da pendência é quem age, não um papel confirmado)." });
    resumo = `${itens.filter((i) => i.tipo === "pendencia").length} pendência(s) e ${itens.filter((i) => i.tipo === "assunto").length} assunto(s) na pauta.`;
  } else if (q.funcao === "registro") {
    if (!q.registro) return { ok: false, erro: "Abrir registro pede registro tipo:id." };
    const r = acharRegistro(brain, q.registro);
    if (!r) bloqueios.push({ fonte: q.registro.split(":")[0], motivo: "Registro não encontrado." });
    else {
      const tipo = q.registro.split(":")[0];
      const f = { decisao: itemDecisao, pendencia: itemPendencia, assunto: itemAssunto, contexto: itemContexto, fato: itemFato, reuniao: itemReuniao, nota: itemDia, documento: itemDocumento, projeto: itemProjeto }[tipo];
      if (f) itens.push(f(r, "registro pedido"));
      const g = buildBrainGraph(brain);
      for (const n of neighborsOf(g, q.registro)) itens.push(item(n.outro, n.outro.split(":")[0], g.nodes.find((x) => x.id === n.outro)?.rotuloCompleto ?? n.outro, null, n.edge.evidencia, `relação explícita: ${n.edge.relacao} (${n.direcao})`));
    }
  } else if (q.funcao === "fonte") {
    if (!q.fonte) return { ok: false, erro: "Ver fonte pede o nome da fonte." };
    const s = usar(q.fonte, "Fonte");
    const mapa = { decisoes: [decisoes, itemDecisao], perfil: [brain.profile, itemFato], pendencias: [lista("threads"), itemPendencia], assuntos: [assuntos, itemAssunto], contexto: [contextos, itemContexto], reunioes: [lista("meetings"), itemReuniao], notas: [lista("daily"), itemDia], documentos: [lista("documents"), itemDocumento], projetos: [lista("projects"), itemProjeto] }[q.fonte];
    if (mapa) for (const x of mapa[0] ?? []) itens.push(mapa[1](x, "registro desta fonte"));
    resumo = `Fonte ${q.fonte}: ${s.estado} (${s.codigo}), ${itens.length} registro(s)${q.area ? ` na área ${q.area}` : ""}.`;
  } else if (q.funcao === "buscar") {
    if (!q.termo) return { ok: false, erro: "Buscar pede um termo." };
    const todos = [
      ...decisoes.map((d) => [itemDecisao(d, BUSCA), `${d.tema} ${d.valor} ${d.citacao}`, d.tema]),
      ...lista("threads").map((f) => [itemPendencia(f, BUSCA), `${f.titulo} ${f.detalhe} ${f.proximo_passo}`, f.titulo]),
      ...assuntos.map((a) => [itemAssunto(a, BUSCA), `${a.titulo} ${a.onde_parou}`, a.titulo]),
      ...(brain.profile ?? []).map((f) => [itemFato(f, BUSCA), f.texto, ""]),
      ...contextos.map((c) => [itemContexto(c, BUSCA), `${c.titulo} ${textoSecoes(c.secoes)}`, c.titulo]),
      ...lista("meetings").map((m) => [itemReuniao(m, BUSCA), `${m.titulo} ${textoSecoes(m.secoes)}`, m.titulo]),
      ...lista("daily").map((n) => [itemDia(n, BUSCA), `${n.titulo} ${textoSecoes(n.secoes)}`, n.titulo]),
      ...lista("documents").map((d) => [itemDocumento(d, BUSCA), `${d.titulo} ${textoSecoes(d.secoes)}`, d.titulo]),
      ...lista("projects").map((p) => [itemProjeto(p, BUSCA), `${p.titulo} ${textoSecoes(p.secoes)}`, p.titulo]),
    ];
    const t = normalizar(q.termo);
    const pont = ([, alvo, titulo]) => (normalizar(titulo).includes(t) ? 10 : 0) + normalizar(alvo).split(t).length - 1;
    for (const x of todos.filter((x) => contem(x[1], q.termo)).sort((a, b) => pont(b) - pont(a) || a[0].ref.localeCompare(b[0].ref))) itens.push(x[0]);
    for (const id of FONTES) usadas.set(id, fonteEstado(brain, id));
    resumo = `${itens.length} registro(s) contêm "${q.termo}". Ordem por ocorrência; não indica relação entre eles.`;
  } else if (q.funcao === "contexto") {
    usar("contexto", "Contexto"); usar("perfil", "Perfil");
    for (const c of contextos) itens.push(itemContexto(c, c.estado === "validado" ? `validado${c.aprovado ? ` (ok dele: "${c.aprovado}")` : ""}` : "pendente de validação: retomar na entrevista"));
    const pend = contextos.filter((c) => c.estado === "pendente").length;
    resumo = `${contextos.length - pend} seção(ões) validada(s), ${pend} pendente(s) de validação.`;
  }

  const conflitos = (brain.conflicts ?? []).filter((c) => c.registros.some((r) => itens.some((i) => i.ref === r)));
  return { ok: true, consulta: q, rotulo: FUNCOES[q.funcao], estado: bloqueios.length ? (itens.length ? "parcial" : "bloqueado") : "ok", resumo, itens, proximosPassos, bloqueios, conflitos, fontesUsadas: [...usadas.values()], carregadoEm: brain.fetchedAt };
}

// Roteiro reutilizável. Neste escopo nunca executa: prepara a proposta, mostra o que exige aprovação e como verificar.
export function roteiro(brain, resultado) {
  if (!resultado?.ok) return null;
  const regras = (brain.decisions ?? []).filter((d) => d.vigente && (d.tipo === "proibicao" || d.tipo === "permissao"));
  const indisponiveis = resultado.fontesUsadas.filter((f) => f.estado !== "ok" && f.estado !== "vazia");
  const c = resultado.consulta;
  return [
    { etapa: "captura", estado: "feito", detalhe: `Pedido: ${resultado.rotulo}${c.termo ? ` · termo "${c.termo}"` : ""}${c.registro ? ` · ${c.registro}` : ""}${c.fonte ? ` · fonte ${c.fonte}` : ""}${c.area ? ` · área ${c.area}` : ""}.`, evidencias: [`carga da Pasta em ${resultado.carregadoEm}`] },
    {
      etapa: "validacao",
      estado: indisponiveis.length || resultado.conflitos.length || resultado.bloqueios.length ? "atencao" : "feito",
      detalhe: indisponiveis.length ? `Fontes que bloqueiam parte da resposta: ${indisponiveis.map((f) => `${f.id} (${f.codigo})`).join(", ")}.` : "Fontes usadas disponíveis; dono fixo matheus; só a Pasta.",
      evidencias: [...resultado.bloqueios.map((b) => b.motivo), ...resultado.conflitos.map((x) => `diagnóstico (não autoritativo): ${x.detalhe}`)],
      aprovacoes: regras.map((d) => ({ ref: `decisao:${d.id}`, texto: `${d.tipo === "proibicao" ? "Proibição" : "Permissão"} vigente: ${d.valor ?? d.tema}` })),
    },
    { etapa: "consulta", estado: resultado.itens.length ? "feito" : "vazio", detalhe: resultado.resumo, evidencias: resultado.itens.map((i) => i.ref) },
    {
      etapa: "execucao",
      estado: "nao_executado",
      detalhe: "Escopo somente leitura: nada foi enviado, gravado ou agendado. A proposta abaixo só vale depois da aprovação exigida, pelo canal canônico (o agente, no Telegram).",
      proposta: resultado.proximosPassos.map((p) => `${p.texto} (${p.ref})`),
      entrega: null,
    },
    { etapa: "verificacao", estado: "pendente", detalhe: "Reler a Pasta e conferir que as impressões não mudaram e os registros citados continuam lá.", evidencias: [] },
  ];
}

// Verificação real: compara a carga usada com uma nova leitura da Pasta.
export function verificar(resultado, recarga) {
  const fontes = resultado.fontesUsadas.map((f) => {
    const depois = fonteEstado(recarga, f.id);
    return { id: f.id, antes: f.impressao, depois: depois.impressao, igual: f.impressao === depois.impressao && f.estado === depois.estado };
  });
  const refs = resultado.itens.map((i) => i.ref).filter((r) => !r.startsWith("referencia:"));
  const presentes = refs.filter((r) => acharRegistro(recarga, r));
  const ok = fontes.every((f) => f.igual) && presentes.length === refs.length;
  return {
    estado: ok ? "verificado" : "divergente",
    detalhe: ok ? "Pasta relida sem mudança; todos os registros citados continuam presentes. Nada foi gravado." : "A Pasta mudou entre a consulta e a verificação: refaça a consulta antes de agir.",
    fontes,
    registros: { citados: refs.length, presentes: presentes.length },
    verificadoEm: recarga.fetchedAt,
  };
}
