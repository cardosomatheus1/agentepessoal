"""Rules for every agent, subordinates included, against the loops seen in practice.

A subordinate comparing 7 report pages with 5 photos looped for 15+ minutes: with the image
cap, loading the second batch evicted the first ("embedded data removed"), so it reloaded the
first, which evicted the second, and so on.
"""

from agent import LoopData
from helpers.extension import Extension

REGRAS = """## Evite loops (vale para você e para subagentes)
- **Imagens:** cabem no máximo 30 no contexto; as mais antigas são removidas e aparecem como "embedded data removed". Antes de carregar outro lote, escreva em texto (num arquivo de notas, ex.: notas_imagens.md) o que viu em cada imagem. **Nunca recarregue imagens que já descreveu** — releia as suas notas. Para comparar muitas imagens, analise em lotes pequenos e compare as notas, não as imagens de novo.
- Se você repetir a mesma ação (mesma ferramenta com os mesmos arquivos/argumentos) pela 2ª vez sem avanço, **pare**: responda dizendo onde travou e qual outro caminho propõe.
"""


class SemLoops(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        system_prompt.append(REGRAS)
