import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const fmt = (n) => (n >= 1024 ** 3 ? (n / 1024 ** 3).toFixed(1) + " GB" : (n / 1024 ** 2).toFixed(1) + " MB");

const model = {
  envios: [], // {nome, pct, estado} — shown under the composer while uploading

  /** Upload one File straight to S3 and deliver it into the chat's anexos/. Returns a note line. */
  async enviarArquivo(file, context) {
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
      setTimeout(() => (this.envios = this.envios.filter((e) => e !== item)), 6000);
      return `📎 Arquivo "${prep.name}" (${fmt(fim.size)}) anexado em ${fim.path}`;
    } catch (e) {
      atualizar({ estado: "erro: " + e.message });
      setTimeout(() => (this.envios = this.envios.filter((x) => x !== item)), 15000);
      throw e;
    }
  },
};

export const store = createStore("arquivoGrande", model);
