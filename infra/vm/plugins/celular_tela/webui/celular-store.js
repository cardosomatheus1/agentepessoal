import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const PLAYERS = { broadway: "Compatível", mse: "Alta qualidade (H.264)", tinyh264: "Leve" };

const model = {
  base: "",
  status: "carregando",
  player: "broadway",  // software decoder: works in any browser
  players: PLAYERS,
  nonce: 0,

  async load() {
    this.status = "carregando";
    try {
      const r = await callJsonApi("/plugins/celular_tela/celular_url", {});
      this.base = r?.url || "";
      this.status = this.base ? "ok" : "sem-url";
    } catch (e) {
      this.status = "erro";
    }
  },

  // Direct ws-scrcpy stream link for the phone (adb serial android:5555), skipping its device list.
  get streamUrl() {
    if (!this.base) return "";
    const u = new URL(this.base);
    const ws = `wss://${u.host}/?action=proxy-adb&remote=tcp%3A8886&udid=android%3A5555`;
    const q = new URLSearchParams({ action: "stream", udid: "android:5555", player: this.player, ws, fitToScreen: "true" });
    return `${u.origin}/?n=${this.nonce}#!${q.toString()}`;
  },

  setPlayer(p) {
    this.player = p;
    this.reload();
  },

  reload() {
    this.nonce += 1;
  },
};

export const store = createStore("celular", model);
