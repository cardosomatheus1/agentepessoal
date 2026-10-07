import { store as celularStore } from "/plugins/celular_tela/webui/celular-store.js";

export default async function registerCelularSurface(surfaces) {
  surfaces.registerSurface({
    id: "celular",
    title: "Celular",
    icon: "smartphone",
    order: 21,
    modalPath: "/plugins/celular_tela/webui/main.html",
    async open() {
      await celularStore.load();
    },
    async close() {},
  });
}
