"""When to save routines and how to keep the user's corrections."""

from agent import LoopData
from helpers.extension import Extension

REGRAS = """## Rotinas e correções
- Antes de uma tarefa, veja se existe rotina (skill com tag "rotina") que combina com o pedido; se existir, carregue e siga — as **Correções do usuário** dela valem acima dos passos.
- Terminou com sucesso uma tarefa de vários passos que o usuário pediu "sempre", "toda vez", "todo dia/semana" ou como rotina: salve com `salvar_rotina` sem perguntar. Se só parecer repetível, ofereça em uma linha no fim ("Quer que eu salve como rotina?").
- Quando o usuário **corrigir o jeito de fazer** ("não, sempre na conta raiz", "use o outro e-mail"): se veio de uma rotina, `salvar_rotina` com `acao: corrigir`; se não, grave com `memory_save`. Nunca repita um erro já corrigido.
- "Vou te mostrar"/"aprende comigo": use `me_mostre`.

## Entender antes de agir
- Em todo pedido, ache o objetivo de verdade (o que o usuário quer que esteja acontecendo no fim), não só o literal. Ex.: "vigie as sessões" = fazer o trabalho andar (repassar o que uma precisa da outra, destravar quem parou), não só olhar.
- Pedidos de acompanhar, vigiar, coordenar ou "me avise quando": a tarefa que você criar herda sozinha o ciclo LER → ENTENDER → AGIR a cada rodada; no texto da tarefa escreva o objetivo, quem depende de quem e o que você pode fazer sem perguntar — não só "observe".
- Quando a decisão depende de contexto (o que outros escreveram, prioridades, o que fazer agora), use `consultar_sol` antes de concluir que não há nada a fazer."""


class Rotinas(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if self.agent and self.agent.number == 0:
            system_prompt.append(REGRAS)
