// Phone navigation fixes over Agent Zero's screen (layout rules live in
// extensions/webui/page-head/interface-celular.html):
// - picking or creating a chat closes the chat menu instead of leaving it over the chat;
// - the tools column opens from the top-bar button and closes after a pick or a tap outside;
// - the "go to the end" button shows only while the chat is scrolled up;
// - the main labels appear in Portuguese.
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
]);
const ATRIBUTOS = ["placeholder", "title", "aria-label"];

function traduzirTexto(no) {
  const valor = no.nodeValue;
  const chave = valor && valor.trim();
  if (chave && TEXTOS.has(chave)) no.nodeValue = valor.replace(chave, TEXTOS.get(chave));
}

function traduzirElemento(el) {
  for (const nome of ATRIBUTOS) {
    const valor = el.getAttribute?.(nome);
    if (valor && TEXTOS.has(valor.trim())) el.setAttribute(nome, TEXTOS.get(valor.trim()));
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
        for (const no of r.addedNodes) if (no.tagName === "BUTTON") traduzirArvore(no);
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
