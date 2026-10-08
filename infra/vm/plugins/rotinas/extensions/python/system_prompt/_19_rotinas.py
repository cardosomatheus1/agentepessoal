"""When to save routines and how to keep the user's corrections."""

from agent import LoopData
from helpers.extension import Extension

REGRAS = """## Rotinas e correções
- Antes de uma tarefa, veja se existe rotina (skill com tag "rotina") que combina com o pedido; se existir, carregue e siga — as **Correções do usuário** dela valem acima dos passos.
- Terminou com sucesso uma tarefa de vários passos que o usuário pediu "sempre", "toda vez", "todo dia/semana" ou como rotina: salve com `salvar_rotina` sem perguntar. Se só parecer repetível, ofereça em uma linha no fim ("Quer que eu salve como rotina?").
- Quando o usuário **corrigir o jeito de fazer** ("não, sempre na conta raiz", "use o outro e-mail"): se veio de uma rotina, `salvar_rotina` com `acao: corrigir`; se não, grave com `memory_save`. Nunca repita um erro já corrigido.
- "Vou te mostrar"/"aprende comigo": use `me_mostre`."""


class Rotinas(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if self.agent and self.agent.number == 0:
            system_prompt.append(REGRAS)
