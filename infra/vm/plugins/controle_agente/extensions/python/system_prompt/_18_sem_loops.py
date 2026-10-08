"""Rules for every agent, subordinates included, against the loops seen in practice.

A subordinate comparing 7 report pages with 5 photos looped for 15+ minutes: with the image
cap, loading the second batch evicted the first ("embedded data removed"), so it reloaded the
first, which evicted the second, and so on.
"""

from agent import LoopData
from helpers.extension import Extension

REGRAS = """## Evite loops (vale para você e para subagentes)
- **Imagens:** com mais de ~5 imagens use a ferramenta **`analisar_imagens`** (analisa uma a uma e devolve texto + arquivo de notas) e compare pelas notas. `vision_load` é para olhar poucas imagens: cabem no máximo 30 na conversa e as mais antigas são removidas ("embedded data removed"). **Nunca recarregue imagens que já analisou** — releia as notas.
- **`parallel`:** nunca coloque `browser` dentro dele — as abas abertas pertencem à conversa principal e o trabalho paralelo não as enxerga ("Browser N is not open"). Use o paralelo só para buscas/consultas independentes; mexa no navegador antes ou depois.
- **Subagentes:** enquanto um subagente trabalha, você fica parado e o usuário não recebe resposta às mensagens dele. Delegue só tarefas objetivas e curtas (peça resposta concisa, poucas fontes) e evite pesquisas longas quando o usuário está esperando você agir.
- **Subagente limpo:** cada passo de um subagente relê todo o histórico dele. Para uma tarefa **nova e independente**, chame `call_subordinate` com `reset: true` e mande na mensagem tudo o que ele precisa (objetivo, URLs, ids, critério de pronto). Use `reset: false` só para continuar **a mesma** tarefa que ele estava fazendo. Navegação longa (mais de ~10 passos no navegador) vai para um subagente limpo, e ele devolve só o resultado.
- Um detector pausa a tarefa se a mesma ação se repetir com o mesmo resultado. Se você repetir a mesma ação (mesma ferramenta com os mesmos arquivos/argumentos) pela 2ª vez sem avanço, **pare**: responda dizendo onde travou e qual outro caminho propõe.
"""


class SemLoops(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        system_prompt.append(REGRAS)
