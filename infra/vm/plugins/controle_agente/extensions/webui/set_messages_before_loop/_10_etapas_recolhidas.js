// Show the agent's steps collapsed by default (like Claude): each answer keeps a closed
// "steps" header that opens on click. Applied once per browser/app; afterwards the choice
// in Preferences → Detail mode wins. Agent Zero rewrites "detailMode" on every load, so a
// separate marker tells whether this default was already applied.
import { store as preferencesStore } from "/components/sidebar/bottom/preferences/preferences-store.js";

const MARCA = "agentepessoal.etapasRecolhidas.v1";

export default async function etapasRecolhidas() {
  try {
    if (localStorage.getItem(MARCA)) return;
    localStorage.setItem(MARCA, "1");
  } catch {
    return;
  }
  if (preferencesStore.detailMode !== "collapsed") preferencesStore.detailMode = "collapsed";
}
