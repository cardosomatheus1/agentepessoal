// Vigia do Google para o agente pessoal.
// Roda na sua conta Google (script.google.com), a cada 10 min: e-mails novos e mudanças na agenda dos
// próximos 3 dias vão para o gatilho do agente, que acorda a máquina e cuida (rascunho, conta, briefing).
// E-mails importantes (caixa principal) e mudanças na agenda vão na hora; os de "Atualizações"
// (faturas, avisos) vão juntos no máximo 1 vez por hora. Nada é enviado quando não há novidade.
// Para instalar: cole tudo, salve, escolha a função "instalar" e clique em Executar (autorize uma vez).

const URL_GATILHO = '__URL_GATILHO__';

function instalar() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('vigiar').timeBased().everyMinutes(10).create();
  const p = PropertiesService.getScriptProperties();
  p.setProperty('desde', String(Math.floor(Date.now() / 1000) - 3600));
  p.setProperty('ultimoLote', '0');
  vigiar();
}

function _emails(consulta, desde) {
  const itens = [];
  GmailApp.search(consulta + ' after:' + desde, 0, 25).forEach(function (th) {
    th.getMessages().forEach(function (m) {
      if (m.getDate().getTime() / 1000 < desde || m.isDraft()) return;
      const de = m.getFrom();
      if (de.indexOf(Session.getActiveUser().getEmail()) >= 0) return; // os seus próprios
      itens.push('- De: ' + de + ' | Assunto: ' + m.getSubject() + ' | ' +
        Utilities.formatDate(m.getDate(), 'America/Bahia', 'dd/MM HH:mm') + ' | id: ' + m.getId() +
        '\n  ' + m.getPlainBody().replace(/\s+/g, ' ').slice(0, 300));
    });
  });
  return itens;
}

function _agenda(p) {
  const agora = new Date(), fim = new Date(agora.getTime() + 3 * 86400000);
  const atual = {};
  CalendarApp.getDefaultCalendar().getEvents(agora, fim).forEach(function (e) {
    if (e.isAllDayEvent()) return;
    atual[e.getId()] = [e.getTitle(), Utilities.formatDate(e.getStartTime(), 'America/Bahia', "yyyy-MM-dd'T'HH:mm:ssXXX"),
      Utilities.formatDate(e.getEndTime(), 'America/Bahia', "yyyy-MM-dd'T'HH:mm:ssXXX"),
      e.getGuestList().map(function (g) { return g.getEmail(); }).join(', '), e.getLocation() || ''];
  });
  const antes = JSON.parse(p.getProperty('agenda') || '{}');
  const mudancas = [];
  Object.keys(atual).forEach(function (id) {
    const a = atual[id], b = antes[id];
    if (!b) mudancas.push('- NOVO: ' + a[0] + ' | ' + a[1] + ' até ' + a[2] + ' | convidados: ' + (a[3] || '-') + ' | local: ' + (a[4] || '-') + ' | id: ' + id);
    else if (a[1] !== b[1] || a[2] !== b[2] || a[0] !== b[0]) mudancas.push('- MUDOU: ' + a[0] + ' | agora ' + a[1] + ' até ' + a[2] + ' (antes ' + b[1] + ') | convidados: ' + (a[3] || '-') + ' | id: ' + id);
  });
  Object.keys(antes).forEach(function (id) {
    if (!atual[id] && new Date(antes[id][1]) > agora) mudancas.push('- CANCELADO/REMOVIDO: ' + antes[id][0] + ' | era ' + antes[id][1] + ' | id: ' + id);
  });
  p.setProperty('agenda', JSON.stringify(atual));
  return mudancas;
}

function vigiar() {
  const p = PropertiesService.getScriptProperties();
  const agora = Math.floor(Date.now() / 1000);
  const desde = Number(p.getProperty('desde') || agora - 900);
  const ultimoLote = Number(p.getProperty('ultimoLote') || 0);
  const importantes = _emails('in:inbox category:primary', desde);
  const loteVence = agora - ultimoLote >= 3600;
  const atualizacoes = loteVence ? _emails('in:inbox category:updates', Math.max(ultimoLote, desde - 3600)) : [];
  const agenda = _agenda(p);
  p.setProperty('desde', String(agora));
  if (loteVence) p.setProperty('ultimoLote', String(agora));
  if (!importantes.length && !atualizacoes.length && !agenda.length) return;
  const partes = [];
  if (importantes.length) partes.push('E-mails novos (caixa principal):\n' + importantes.join('\n'));
  if (atualizacoes.length) partes.push('E-mails novos (atualizações: faturas, avisos):\n' + atualizacoes.join('\n'));
  if (agenda.length) partes.push('Agenda (próximos 3 dias):\n' + agenda.join('\n'));
  UrlFetchApp.fetch(URL_GATILHO, { method: 'post', contentType: 'text/plain; charset=utf-8',
    payload: partes.join('\n\n').slice(0, 19000), muteHttpExceptions: true });
}
