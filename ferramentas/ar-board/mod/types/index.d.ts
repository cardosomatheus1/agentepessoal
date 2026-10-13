export type Voto = { v: 'A' | 'R'; c: string; em: number }

declare module 'claude-code' {
  interface PluginState {
    'ar-board': { idx: number; aviso: string; versao: number; rid: string }
  }
}
