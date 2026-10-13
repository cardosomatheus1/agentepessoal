import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Voto } from '../types'

// The current round and the verdicts live in files of the repository's calibration folder, so the board page,
// this pane and the session that reads them all meet in one place.
const PASTA = '/home/user/agentepessoal/calibracao/.quadro'
const RODADA = `${PASTA}/rodada.json`
const VOTOS = `${PASTA}/vereditos.json`
const QUADRO_WEB = 'https://claude.ai/artifact/7LFmwYACCRBHspUv9QGwcx'
const PANE = 'ar-board'

type Item = { id: string; tipo?: string; titulo?: string; contexto?: string; texto?: string }
type Rodada = { id: string; agente?: string; titulo?: string; instrucao?: string; itens: Item[] }
type Votos = Record<string, { votos: Record<string, Voto>; terminada_em?: number }>

const idx = atom({ plugin: 'ar-board', key: 'idx' } as const, 0)
const aviso = atom({ plugin: 'ar-board', key: 'aviso' } as const, '')
const versao = atom({ plugin: 'ar-board', key: 'versao' } as const, 0)
const ridAtual = atom({ plugin: 'ar-board', key: 'rid' } as const, '')

async function lerJson<T>($: any, path: string, vazio: T): Promise<T> {
  try {
    if (!(await $.fs.exists(path))) return vazio
    return JSON.parse(await $.fs.read(path)) as T
  } catch {
    return vazio
  }
}

async function rodada($: any): Promise<Rodada | null> {
  const r = await lerJson<Rodada | null>($, RODADA, null)
  return r && Array.isArray(r.itens) && r.itens.length ? r : null
}

// A new round starts at its first case without a verdict.
async function alinhar($: any, r: Rodada) {
  if ((await read($, ridAtual)) === r.id) return
  const todos = await lerJson<Votos>($, VOTOS, {})
  const votos = (todos[r.id] ?? { votos: {} }).votos
  const aberto = r.itens.findIndex(x => !votos[x.id])
  await update($, idx, () => (aberto >= 0 ? aberto : 0))
  await update($, ridAtual, () => r.id)
  await update($, aviso, () => '')
}

async function gravarVoto($: any, v: 'A' | 'R' | null, comentario?: string) {
  const r = await rodada($)
  if (!r) return
  // the pane already shows a new round at its first open case; align the state to what is on screen
  await alinhar($, r)
  const i = Math.min(await read($, idx), r.itens.length - 1)
  const item = r.itens[i]
  const todos = await lerJson<Votos>($, VOTOS, {})
  const daRodada = todos[r.id] ?? { votos: {} }
  const antes = daRodada.votos[item.id]
  if (v === null && !antes) {
    await update($, aviso, () => 'Escolha aprovar ou rejeitar antes de comentar.')
    return
  }
  daRodada.votos[item.id] = { v: v ?? antes!.v, c: comentario ?? antes?.c ?? '', em: Date.now() }
  todos[r.id] = daRodada
  await $.fs.write(VOTOS, JSON.stringify(todos, null, 1))
  if (v !== null) {
    const proximo = r.itens.findIndex((x, j) => j > i && !daRodada.votos[x.id])
    const algum = r.itens.findIndex(x => !daRodada.votos[x.id])
    const destino = proximo >= 0 ? proximo : algum >= 0 ? algum : i
    await update($, idx, () => destino)
  }
  await update($, aviso, () => (v === null ? 'Comentário salvo.' : v === 'A' ? 'Aprovado.' : 'Rejeitado.'))
  await update($, versao, n => n + 1)
}

async function terminar($: any) {
  const r = await rodada($)
  if (!r) return
  const todos = await lerJson<Votos>($, VOTOS, {})
  const daRodada = todos[r.id] ?? { votos: {} }
  daRodada.terminada_em = Date.now()
  todos[r.id] = daRodada
  await $.fs.write(VOTOS, JSON.stringify(todos, null, 1))
  const julgados = Object.keys(daRodada.votos).length
  await update($, aviso, () => 'Rodada terminada. Avisei a conversa.')
  await update($, versao, n => n + 1)
  void $.prompt.submit({ text: `terminei a rodada ${r.id} do AR Board (${julgados} de ${r.itens.length} julgados, pelo painel)` })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'ar', description: 'Abrir o AR Board: aprovar ou rejeitar os casos da rodada atual' })
    const atual = await rodada($)
    if (atual) {
      await alinhar($, atual)
      void $.ui.open({ id: PANE, title: 'AR Board' })
    }
    return next(e)
  })

  on('command.run', { command: 'ar' }, async $ => {
    const atual = await rodada($)
    if (atual) await alinhar($, atual)
    await update($, versao, n => n + 1)
    await $.ui.open({ id: PANE, title: 'AR Board' })
    return { text: (await rodada($)) ? 'AR Board aberto.' : 'Nenhuma rodada no AR Board agora. Peça uma ao Claude.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Input } = $.ui.resolve(e)
    await read($, versao)
    const r = await rodada($)
    if (!r) {
      return (
        <Box flexDirection="column" gap={1}>
          <Text bold>AR Board</Text>
          <Text dimColor>Nenhuma rodada para julgar agora. Quando o Claude montar uma, ela aparece aqui.</Text>
        </Box>
      )
    }
    const todos = await lerJson<Votos>($, VOTOS, {})
    const daRodada = todos[r.id] ?? { votos: {} }
    const mesma = (await read($, ridAtual)) === r.id
    const primeiroAberto = Math.max(0, r.itens.findIndex(x => !daRodada.votos[x.id]))
    const i = mesma ? Math.max(0, Math.min(await read($, idx), r.itens.length - 1)) : primeiroAberto
    const item = r.itens[i]
    const voto = daRodada.votos[item.id]
    const feitos = r.itens.filter(x => daRodada.votos[x.id]).length
    const aprovados = r.itens.filter(x => daRodada.votos[x.id]?.v === 'A').length
    const msg = await read($, aviso)
    const ir = (d: number) => () => {
      void (async () => {
        await update($, idx, n => Math.max(0, Math.min(r.itens.length - 1, n + d)))
        await update($, aviso, () => '')
      })()
    }

    return (
      <Box flexDirection="column" gap={1}>
        <Text dimColor>
          {(r.agente ?? 'agente').toUpperCase()} · {r.titulo ?? r.id}
        </Text>
        {r.instrucao && <Text dimColor wrap="wrap">{r.instrucao}</Text>}
        <Box gap={1} flexWrap="wrap">
          <Text key="posicao">{`Caso ${i + 1} de ${r.itens.length}${item.tipo ? ` · ${item.tipo}` : ''}`}</Text>
          <Text key="veredito" bold={!!voto} dimColor={!voto} color={voto ? (voto.v === 'A' ? 'success' : 'error') : undefined}>
            {voto ? (voto.v === 'A' ? 'APROVADO' : 'REJEITADO') : 'sem veredito'}
          </Text>
        </Box>
        <Text bold wrap="wrap">{item.titulo ?? `Caso ${i + 1}`}</Text>
        {item.contexto && <Text dimColor wrap="wrap">{item.contexto}</Text>}
        <Text wrap="wrap">{item.texto ?? ''}</Text>
        <Input
          key={`comentario-${r.id}-${item.id}`}
          label="Por quê: "
          placeholder="o que fez você aprovar ou rejeitar (Enter salva)"
          value={voto?.c ?? ''}
          submitLabel="salvar"
          onSubmit={valor => void gravarVoto($, null, valor.trim())}
        />
        <Box gap={1} flexWrap="wrap">
          <Button key="aprovar" variant="primary" hotkey="a" onPress={() => void gravarVoto($, 'A')}>
            ✅ Aprovar
          </Button>
          <Button key="rejeitar" hotkey="r" onPress={() => void gravarVoto($, 'R')}>
            ❌ Rejeitar
          </Button>
          <Button key="anterior" onPress={ir(-1)}>← Anterior</Button>
          <Button key="proximo" onPress={ir(1)}>Próximo →</Button>
        </Box>
        <Text key="progresso" dimColor>{`${feitos} de ${r.itens.length} julgados · ${aprovados} aprovados${msg ? ` · ${msg}` : ''}`}</Text>
        <Box gap={1} flexWrap="wrap">
          <Button key="terminei" onPress={() => void terminar($)}>
            Terminei esta rodada
          </Button>
          <Button key="web" onPress={press => void $.ui.copy({ text: QUADRO_WEB, surface: press.surface })}>
            Copiar link do quadro no navegador
          </Button>
        </Box>
      </Box>
    )
  })
}
