"""Rules for every agent, subordinates included, against the loops seen in practice.

A subordinate comparing 7 report pages with 5 photos looped for 15+ minutes: with the image
cap, loading the second batch evicted the first ("embedded data removed"), so it reloaded the
first, which evicted the second, and so on.
"""

from agent import LoopData
from helpers.extension import Extension

REGRAS = """## Evite loops (vale para você e para subagentes)
- **Imagens:** com mais de ~5 imagens use a ferramenta **`analisar_imagens`** (analisa uma a uma e devolve texto + arquivo de notas) e compare pelas notas. `vision_load` é para olhar poucas imagens: cabem no máximo 30 na conversa e as mais antigas são removidas ("embedded data removed"). **Nunca recarregue imagens que já analisou** — releia as notas.
- Um detector pausa a tarefa se a mesma ação se repetir com o mesmo resultado. Se você repetir a mesma ação (mesma ferramenta com os mesmos arquivos/argumentos) pela 2ª vez sem avanço, **pare**: responda dizendo onde travou e qual outro caminho propõe.
"""


class SemLoops(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        system_prompt.append(REGRAS)
