import { describe, expect, test } from 'claude-code/testing'

const RODADA = '/home/user/agentepessoal/calibracao/.quadro/rodada.json'
const VOTOS = '/home/user/agentepessoal/calibracao/.quadro/vereditos.json'
const PANE = {
  component: 'Pane',
  requestId: 'ar-board',
  props: { title: 'AR Board', isFocused: true, bodyColumns: 96 },
  viewport: { columns: 100, rows: 40 },
} as const

const exemplo = {
  id: 'teste-1',
  agente: 'prospecção',
  titulo: 'Rodada de teste',
  itens: [
    { id: 'c1', titulo: 'Comentário 1', texto: 'Esse kit parece prático. Qual sabor sai mais?' },
    { id: 'c2', titulo: 'Comentário 2', texto: 'Tô conversando com donos aqui em Salvador.' },
  ],
}

function discoEmMemoria(on: any, inicial: Record<string, string>) {
  const arquivos = { ...inicial }
  on('fs.exists', async (_$: any, e: { path: string }) => ({ value: e.path in arquivos }))
  on('fs.read', async (_$: any, e: { path: string }) => {
    if (!(e.path in arquivos)) return { deny: 'ENOENT' }
    return { value: arquivos[e.path] }
  })
  on('fs.write', async (_$: any, e: { path: string; text: string }) => {
    arquivos[e.path] = e.text
    return { value: undefined }
  })
  const prompts: string[] = []
  on('prompt.submit', async (_$: any, e: { text: string }) => {
    prompts.push(e.text)
    return { text: e.text }
  })
  return { arquivos, prompts }
}

describe('AR Board', () => {
  test('sem rodada, o painel diz que não há nada para julgar', async ($, on) => {
    discoEmMemoria(on, {})
    for (const surface of ['terminal', 'desktop'] as const) {
      const ui = await $.ui.mount({ plugin: 'ar-board', surface, ...PANE })
      expect(await ui.find({ type: 'Text', text: /Nenhuma rodada/ })).toBeDefined()
      await ui.unmount()
    }
  })

  test('aprovar e rejeitar gravam o veredito, e Terminei avisa a conversa', async ($, on) => {
    const disco = discoEmMemoria(on, {})
    for (const surface of ['terminal', 'desktop'] as const) {
      const rid = `teste-${surface}`
      disco.arquivos[RODADA] = JSON.stringify({ ...exemplo, id: rid })
      disco.arquivos[VOTOS] = '{}'
      disco.prompts.length = 0
      const ui = await $.ui.mount({ plugin: 'ar-board', surface, ...PANE })
      expect(await ui.find({ type: 'Text', text: /Caso 1 de 2/ })).toBeDefined()

      await ui.press({ key: 'aprovar' })
      await ui.press({ key: 'rejeitar' })
      const votos = JSON.parse(disco.arquivos[VOTOS])[rid].votos
      expect(votos.c1.v).toBe('A')
      expect(votos.c2.v).toBe('R')
      expect(await ui.find({ type: 'Text', text: /2 de 2 julgados · 1 aprovados/ })).toBeDefined()

      await ui.input({ key: `comentario-${rid}-c2`, text: 'não é de Salvador' })
      expect(JSON.parse(disco.arquivos[VOTOS])[rid].votos.c2.c).toBe('não é de Salvador')

      await ui.press({ key: 'terminei' })
      expect(JSON.parse(disco.arquivos[VOTOS])[rid].terminada_em).toBeGreaterThan(0)
      expect(disco.prompts.join(' ')).toMatch(new RegExp(`terminei a rodada ${rid}`))
      await ui.unmount()
    }
  })
})
