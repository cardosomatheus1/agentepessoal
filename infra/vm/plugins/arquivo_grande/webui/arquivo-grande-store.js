import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import { store as inputStore } from "/components/chat/input/input-store.js";

const fmt = (n) => (n >= 1024 ** 3 ? (n / 1024 ** 3).toFixed(1) + " GB" : (n / 1024 ** 2).toFixed(1) + " MB");

const model = {
  envios: [], // {nome, pct, estado}

  escolher() {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.onchange = () => [...input.files].forEach((f) => this.enviar(f));
    input.click();
  },

  async enviar(file) {
    const context = globalThis.getContext?.();
    if (!context) {
      globalThis.toastFrontendError?.("Abra uma conversa antes de enviar.", "Arquivo grande");
      return;
    }
    const item = { nome: file.name, pct: 0, estado: "preparando" };
    this.envios = [...this.envios, item];
    const atualizar = (patch) => {
      Object.assign(item, patch);
      this.envios = [...this.envios];
    };
    try {
      const prep = await callJsonApi("/plugins/arquivo_grande/preparar", { context, name: file.name, size: file.size });
      if (!prep?.url) throw new Error(prep?.error || "não consegui preparar o envio");
      atualizar({ estado: "enviando" });
      await new Promise((ok, fail) => {
        const x = new XMLHttpRequest();
        x.open("PUT", prep.url);
        x.upload.onprogress = (e) => e.lengthComputable && atualizar({ pct: Math.round((e.loaded * 100) / e.total) });
        x.onload = () => (x.status < 300 ? ok() : fail(new Error("erro " + x.status)));
        x.onerror = () => fail(new Error("a conexão caiu"));
        x.send(file);
      });
      atualizar({ pct: 100, estado: "entregando na conversa" });
      let fim = null;
      for (let i = 0; i < 60 && !fim; i++) {
        const r = await callJsonApi("/plugins/arquivo_grande/concluir", { context, name: prep.name });
        if (r?.ok) fim = r;
        else await new Promise((res) => setTimeout(res, 3000));
      }
      if (!fim) throw new Error("enviado, mas ainda não chegou na conversa — tente de novo em instantes");
      atualizar({ estado: "pronto" });
      const linha = `📎 Enviei o arquivo "${prep.name}" (${fmt(fim.size)}), está em ${fim.path}`;
      inputStore.message = inputStore.message ? inputStore.message.trimEnd() + "\n" + linha : linha;
      globalThis.toastFrontendSuccess?.(`${prep.name} está na conversa`, "Arquivo grande");
      setTimeout(() => (this.envios = this.envios.filter((e) => e !== item)), 8000);
    } catch (e) {
      atualizar({ estado: "erro: " + e.message });
      globalThis.toastFrontendError?.(`${file.name}: ${e.message}`, "Arquivo grande");
    }
  },
};

export const store = createStore("arquivoGrande", model);
