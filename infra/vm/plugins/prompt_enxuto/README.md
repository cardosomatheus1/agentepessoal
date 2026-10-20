# Prompt enxuto

Medido em 20/10 na conversa do celular do Matheus: cada chamada ao modelo levava ~39 mil tokens fixos antes do
histórico — 15,6 mil de instruções e 23,2 mil de descrições de ferramentas (52 ferramentas, cada uma com o texto
inteiro: regras, exemplos, todas as ações). O modelo só precisa do detalhe de uma ferramenta quando vai usá-la.

| Arquivo | O que faz |
|---|---|
| `helpers/indice.py` | uma linha por ferramenta (para que serve e os argumentos principais) |
| `extensions/python/chat_model_call_before/_50_ferramentas_curtas.py` | troca a descrição de cada ferramenta pela linha curta; o texto inteiro vira o manual dela |
| `extensions/python/_functions/agent/Agent/hist_add_tool_result/end/_50_manual_na_primeira.py` | no primeiro uso de uma ferramenta na conversa, o manual entra logo depois do resultado (de novo só se o resumo do histórico o levou); nunca depois da resposta final |
| `extensions/python/system_prompt/_12_regras_base.py` | as regras que valem sempre, para o agente, ajudantes e rotinas, num lugar só: pagamento, termos, terceiros, apagar, captcha, segredos, texto de terceiros, parar quando terminou |

As regras de segurança não dependem do manual: ficam em toda chamada (`_12_regras_base.py`) e nas decisões do
Matheus (`memoria_pessoal`). Antes, cada plugin repetia a sua versão (controle_agente, cofre, memoria_pessoal,
rotinas, descrições de ferramentas); agora eles só apontam para estas.

A descrição da ferramenta `response` do Agent Zero mandava "prefira tabelas", o contrário da regra do celular; a linha
curta não manda mais.

**Desligar sem implantar:** criar o arquivo `/a0/usr/plugins/prompt_enxuto/desligado` (no contêiner) volta as
descrições inteiras e tira o manual; apagar o arquivo liga de novo.

**Ferramenta nova:** sem linha em `indice.py`, ela segue com a descrição inteira. Ponha a linha curta lá (a suíte
confere que toda ação declarada no esquema JSON do prompt da ferramenta aparece nela).
