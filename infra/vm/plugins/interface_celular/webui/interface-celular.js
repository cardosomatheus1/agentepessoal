// Phone navigation fixes over Agent Zero's screen (layout rules live in
// extensions/webui/page-head/interface-celular.html):
// - picking or creating a chat closes the chat menu instead of leaving it over the chat;
// - the tools column opens from the top-bar button and closes after a pick or a tap outside;
// - the "go to the end" button shows only while the chat is scrolled up;
// - the labels, hints, status lines and the new-chat greeting appear in Portuguese.
import { store as sidebarStore } from "/components/sidebar/sidebar-store.js";
import { store as chatsStore } from "/components/sidebar/chats/chats-store.js";

const celular = () => window.innerWidth <= 768;

function fecharMenuDepois(nome) {
  const original = chatsStore[nome];
  if (typeof original !== "function" || original.__interfaceCelular) return;
  const envolvida = async function (...args) {
    const resultado = await original.apply(this, args);
    if (celular()) sidebarStore.close();
    return resultado;
  };
  envolvida.__interfaceCelular = true;
  chatsStore[nome] = envolvida;
}

function ferramentas(abrir) {
  document.body.classList.toggle("ic-ferramentas", abrir);
}

globalThis.interfaceCelular = {
  alternarFerramentas() {
    ferramentas(!document.body.classList.contains("ic-ferramentas"));
  },
};

document.addEventListener("click", (e) => {
  if (!document.body.classList.contains("ic-ferramentas")) return;
  if (e.target.closest?.(".ic-ferramentas-btn")) return;
  // A pick opens the tool in its own window; a tap anywhere else just closes the column.
  ferramentas(false);
}, true);

function acompanharRolagem() {
  const historico = document.getElementById("chat-history");
  if (!historico || historico.__interfaceCelular) return !!historico;
  historico.__interfaceCelular = true;
  let agendado = false;
  const medir = () => {
    agendado = false;
    const longe = historico.scrollHeight - historico.scrollTop - historico.clientHeight > 600;
    document.body.classList.toggle("ic-longe-do-fim", longe);
  };
  historico.addEventListener("scroll", () => {
    if (!agendado) {
      agendado = true;
      requestAnimationFrame(medir);
    }
  }, { passive: true });
  return true;
}

// Exact labels only (after trimming); the chat content itself is never translated.
const TEXTOS = new Map([
  ["Chats", "Conversas"],
  ["Tasks", "Tarefas"],
  ["Preferences", "Preferências"],
  ["Projects", "Projetos"],
  ["No project", "Sem projeto"],
  ["Dashboard", "Início"],
  ["Show more", "Mostrar mais"],
  ["Show less", "Mostrar menos"],
  ["Loading chat", "Carregando conversa"],
  ["Ask anything to start a new chat", "Pergunte algo para começar uma conversa"],
  ["Type your message here...", "Escreva sua mensagem…"],
  ["Press Enter to send queued messages", "Enter envia as mensagens da fila"],
  ["Waiting for input", "Aguardando você"],
  ["Scroll to bottom", "Ir para o fim"],
  ["Scroll to top", "Ir para o início"],
  ["New chat", "Nova conversa"],
  ["Settings", "Configurações"],
  ["Cancel", "Cancelar"],
  ["Save", "Salvar"],
  ["Delete", "Apagar"],
  ["Rename", "Renomear"],
  ["Close", "Fechar"],
  ["Copy", "Copiar"],
  ["Files", "Arquivos"],
  ["History", "Histórico"],
  ["Memory", "Memória"],
  ["Browser", "Navegador"],
  ["Desktop", "Computador"],
  ["Customize canvas", "Personalizar ferramentas"],
  ["Close canvas", "Fechar"],
  ["Pause Agent", "Pausar"],
  ["Resume Agent", "Continuar"],
  ["Nudge", "Destravar"],
  // home screen
  ["Hello! I'm Agent Zero", "Olá! Sou o seu agente"],
  ["How can I help you today?", "Como posso ajudar hoje?"],
  ["Quick Actions", "Atalhos"],
  ["Organize and track your work.", "Organize e acompanhe seu trabalho."],
  ["Access saved context and knowledge.", "O que o agente guardou e aprendeu."],
  ["View and manage your tasks.", "Veja e gerencie suas tarefas."],
  ["Search and manage your files.", "Busque e gerencie seus arquivos."],
  ["Configure Agent Zero to your preferences.", "Ajuste o agente do seu jeito."],
  ["Extend Agent Zero with integrations.", "Amplie o agente com integrações."],
  ["Visit Website", "Visitar o site"],
  ["Explore Agent Zero online and resources.", "Conheça o Agent Zero e seus recursos."],
  ["Your AI accounts", "Suas contas de IA"],
  ["Use your subscription-backed logins for model access.", "Use os logins das suas assinaturas para acessar modelos."],
  ["Connect accounts", "Conectar contas"],
  ["Available", "Disponível"],
  ["Connect Channels", "Conectar canais"],
  ["Extend Agent Zero across your favorite platforms.", "Leve o agente para as plataformas que você usa."],
  ["Connect Telegram", "Conectar Telegram"],
  ["Connect Email", "Conectar e-mail"],
  ["Connect WhatsApp", "Conectar WhatsApp"],
  ["System Resources", "Recursos do sistema"],
  ["Disk", "Disco"],
  ["Net (since boot)", "Rede (desde que ligou)"],
  ["Load (1/5/15)", "Carga (1/5/15)"],
  // chat and input
  ["Compact", "Compactar"],
  ["Loading earlier messages", "Carregando mensagens anteriores"],
  ["History compression stalled", "O resumo do histórico travou"],
  ["Building prompt", "Preparando…"],
  ["Calling LLM...", "Pensando…"],
  ["Send message", "Enviar"],
  ["Stop agent", "Parar o agente"],
  ["New Chat", "Nova conversa"],
  ["Start a new chat", "Nova conversa"],
  ["Expand input", "Ampliar o campo"],
  ["Microphone standby", "Microfone"],
  ["Message", "Mensagem"],
  ["Upload Files", "Enviar arquivos"],
  ["Branch chat", "Criar ramificação"],
  ["Speak", "Ouvir"],
  ["Stop Speech", "Parar a voz"],
  ["Context window usage", "Uso da memória da conversa"],
  ["Toggle Sidebar", "Mostrar/ocultar o menu"],
  ["Sidebar view options", "Opções da lista"],
  ["More actions", "Mais ações"],
  ["More chat actions", "Mais ações da conversa"],
  ["More task actions", "Mais ações da tarefa"],
  ["More options", "Mais opções"],
  ["More controls", "Mais controles"],
  ["Expand chat children", "Mostrar sub-conversas"],
  ["Pinned", "Fixadas"],
  ["View details", "Ver detalhes"],
  ["Search", "Buscar"],
  ["Close search", "Fechar a busca"],
  ["Create new", "Criar"],
  // preferences
  ["Dark mode", "Modo escuro"],
  ["Detail", "Detalhes"],
  ["Speech", "Voz"],
  ["Show utility messages", "Mostrar mensagens internas"],
  ["Show verbose tool calls", "Mostrar ferramentas em detalhe"],
  // tools (browser, files, editor)
  ["Annotate", "Anotar"],
  ["Back", "Voltar"],
  ["Go back", "Voltar"],
  ["Forward", "Avançar"],
  ["Go forward", "Avançar"],
  ["Reload", "Recarregar"],
  ["New Browser", "Nova aba"],
  ["Open Browser", "Abrir o navegador"],
  ["Browser settings", "Configurações do navegador"],
  ["Clear annotations", "Limpar anotações"],
  ["Send annotations", "Enviar anotações"],
  ["Open as window", "Abrir em janela"],
  ["Open", "Abrir"],
  ["Name", "Nome"],
  ["Size", "Tamanho"],
  ["Modified", "Modificado"],
  ["New file", "Novo arquivo"],
  ["New folder", "Nova pasta"],
  ["Download file", "Baixar arquivo"],
  ["Open file", "Abrir arquivo"],
  ["Filter files...", "Filtrar arquivos…"],
  ["Undo", "Desfazer"],
  ["Redo", "Refazer"],
  ["Preview", "Visualizar"],
  ["Text", "Texto"],
  ["Width", "Largura"],
  ["Save As", "Salvar como"],
  ["Delete item", "Apagar item"],
  ["Delete selected items", "Apagar selecionados"],
  ["Clear selection", "Limpar seleção"],
  ["Next match", "Próximo"],
  ["Previous match", "Anterior"],
  ["Bold", "Negrito"],
  ["Italic", "Itálico"],
  ["List", "Lista"],
  ["Numbered list", "Lista numerada"],
  ["Table", "Tabela"],
  ["Refresh System Resources", "Atualizar"],
  ["File actions", "Ações do arquivo"],
  ["Folder actions", "Ações da pasta"],
  ["Toggle file tree", "Mostrar/ocultar pastas"],
  ["New Markdown", "Novo texto (Markdown)"],
  ["Parent folders", "Pastas acima"],
  ["Open text files", "Abrir arquivos de texto"],
  ["Directory path", "Pasta"],
  ["Edit directory path", "Editar pasta"],
  ["Edit document", "Editar documento"],
  ["Apply document edit", "Aplicar edição"],
  ["Cancel document edit", "Cancelar edição"],
  ["File Browser Settings", "Configurações de arquivos"],
  ["Search preview", "Buscar na visualização"],
]);

// Status lines and labels that carry a value ("A0: Using tool 'browser'", "Close #3 Instagram").
const FERRAMENTAS = [
  [/search_engine|pesquisar|busca_modelo|web_search/i, "Pesquisando na web"],
  [/browser/i, "Usando o navegador"],
  [/code_execution|terminal/i, "Rodando comandos"],
  [/call_subordinate|parallel/i, "Pedindo ajuda a ajudantes"],
  [/gmail|e-?mail/i, "Lendo e-mails"],
  [/whatsapp|telegram/i, "Enviando mensagem"],
  [/scheduler/i, "Agendando"],
  [/memory|memoriz/i, "Consultando a memória"],
  [/response/i, "Escrevendo a resposta"],
];
const REGRAS = [
  [/^A\d+: Calling LLM\.*$/, () => "Pensando…"],
  [/^A\d+: (?:Using (?:MCP )?(?:tool )?)?(.+?)\.*$/, (_, f) => (FERRAMENTAS.find(([re]) => re.test(f)) || [, `Usando ${f.replace(/['"]/g, "")}`])[1]],
  [/^Context window ([\d.]+)% used$/, (_, n) => `Memória da conversa: ${n}% usada`],
  [/^Close (#\d+ .*)$/, (_, t) => `Fechar ${t}`],
  [/^Dismiss .+$/, () => "Dispensar"],
  [/^Edit (.+)$/, (_, t) => `Editar ${t}`],
];

function traducao(chave) {
  if (TEXTOS.has(chave)) return TEXTOS.get(chave);
  for (const [re, fn] of REGRAS) {
    const m = chave.match(re);
    if (m) return fn(...m);
  }
  return null;
}

// The greeting at the top of each new chat.
const SAUDACAO = /^Hello! 👋,? I'm Agent Zero, your AI assistant\. How can I help you today\?$/;
function traduzirSaudacao(raiz) {
  for (const el of raiz.querySelectorAll?.(".msg-content") || []) {
    if (SAUDACAO.test(el.textContent.trim())) el.innerHTML = "<p><strong>Olá! 👋</strong> Sou o seu agente. Como posso ajudar hoje?</p>";
  }
}
const ATRIBUTOS = ["placeholder", "data-placeholder", "title", "aria-label"];

function traduzirTexto(no) {
  const valor = no.nodeValue;
  const chave = valor && valor.trim();
  const novo = chave && traducao(chave);
  if (novo && novo !== chave) no.nodeValue = valor.replace(chave, novo);
}

function traduzirElemento(el) {
  for (const nome of ATRIBUTOS) {
    const valor = el.getAttribute?.(nome);
    const novo = valor && traducao(valor.trim());
    if (novo && novo !== valor.trim()) el.setAttribute(nome, novo);
  }
}

function traduzirArvore(raiz) {
  if (raiz.nodeType === Node.TEXT_NODE) return traduzirTexto(raiz);
  if (raiz.nodeType !== Node.ELEMENT_NODE) return;
  traduzirElemento(raiz);
  const passeio = document.createTreeWalker(raiz, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  for (let no = passeio.nextNode(); no; no = passeio.nextNode()) {
    if (no.nodeType === Node.TEXT_NODE) traduzirTexto(no);
    else traduzirElemento(no);
  }
}

function traduzir() {
  const historico = () => document.getElementById("chat-history");
  // Inside the chat only the "Show more/less" buttons are looked at: walking every streamed
  // step would cost exactly the smoothness this plugin is after.
  const noChat = (no) => {
    const h = historico();
    return !!h && h.contains(no);
  };
  const observador = new MutationObserver((registros) => {
    for (const r of registros) {
      if (noChat(r.target)) {
        if (r.target.tagName === "BUTTON") traduzirArvore(r.target);
        for (const no of r.addedNodes) {
          if (no.tagName === "BUTTON") traduzirArvore(no);
          else if (no.nodeType === Node.ELEMENT_NODE) traduzirSaudacao(no);
        }
        continue;
      }
      if (r.type === "attributes") traduzirElemento(r.target);
      else if (r.type === "characterData") traduzirTexto(r.target);
      else for (const no of r.addedNodes) traduzirArvore(no);
    }
  });
  observador.observe(document.body, {
    childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: ATRIBUTOS,
  });
  traduzirArvore(document.body); // at start the chat is still empty
  traduzirSaudacao(document.body);
}

function iniciar() {
  fecharMenuDepois("selectChat");
  fecharMenuDepois("newChat");
  if (!acompanharRolagem()) {
    const espera = setInterval(() => acompanharRolagem() && clearInterval(espera), 500);
  }
  traduzir();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar, { once: true });
else iniciar();
