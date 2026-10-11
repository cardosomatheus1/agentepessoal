# Arquitetura da prospecção (Raiz Connect)

## Peças e quem é dono de quê

| Peça | Onde | Dono / quem escreve |
|---|---|---|
| Regras do negócio (cliente ideal, tom, modelos, limites) | `plugins/prospeccao/playbook.md` | Matheus decide; Claude edita com teste |
| Lógica e estado (nota, sequência, limites, travas, revisor) | `plugins/prospeccao/helpers/prospeccao.py` | código; a única coisa que escreve `/a0/usr/prospeccao/<login>.json` |
| Fontes de leads fora do Instagram | `plugins/prospeccao/helpers/fontes.py` | código; escreve `<login>_fontes.json` |
| Ferramenta do agente | `plugins/prospeccao/tools/prospeccao.py` | expõe as funções acima ao modelo |
| Como fazer no Instagram | `skills/prospeccao-instagram/SKILL.md` | o modelo segue; nada de regra de negócio aqui |
| Rodadas agendadas | `plugins/prospeccao/rodadas.py` (prompts curtos que carregam a skill) | agendador do Agent Zero |
| Diário | `/a0/usr/prospeccao/<login>_eventos.jsonl` | append-only, gravado por `salvar()` |

Princípio: **o modelo decide o texto e opera o navegador; o código decide o que pode acontecer.** Quem pode receber o
quê, quando, quantas vezes e em que ordem é regra do código, nunca do modelo.

## Estados de uma ação

```
(nova) → proposta → aprovada → executada → apagada
             │          │  └──→ falhou
             │          └──→ cancelada | proposta (texto editado)
             └──→ pulada | expirada | cancelada | proposta (editada)
```

- A tabela `TRANSICOES` é a única fonte. `_mudar()` recusa qualquer salto (`TransicaoInvalida`) e registra no
  diário quem mudou, de onde para onde e por quê.
- Falhou não se repete: uma tentativa nova é uma ação nova.
- Executada que foi apagada no Instagram vira `apagada` (ação `apagada`) e deixa de contar como enviada.

## Travas (invariantes que o código garante)
- Remetente sempre a conta da Raiz; a pessoal é recusada.
- No máximo 2 mensagens sem resposta por lead. Uma resposta por fala da pessoa; robô (Manychat) não é fala.
- Limites por dia por tipo; só das 9h às 20h; 3 min entre ações; `conferido` (Direct e notificações lidos) antes de
  executar.
- Vaga de «aquecer» livre (descarte na visita) é reposta pela `proxima` com o melhor lead novo, sem texto, um por vez
  (só com a pré-aprovação ligada); visita que falhou não é tentada de novo.
- Esperas em dias de calendário (aquecido no dia D → primeira mensagem a partir do dia D+2; lembrete D+3).
- Bloqueio de ação do Instagram pausa 48 h. O 429 de consulta não é bloqueio: volta às fontes.
- Texto pré-aprovado passa pelo revisor (modelo independente). Se o motivo dele contradiz o texto (regra simples
  comprova o que ele diz faltar), há uma 2ª revisão com o fato. Sem revisor, nada sai sozinho (vai ao ✅).

## Mudanças: como se faz
1. `git pull`; confira no `git log` se outra sessão mexeu na prospecção nas últimas horas.
2. Mude o código com teste novo em `tests/suite.py`; a suíte inteira passa.
3. Commit + push.
4. `python3 infra/operador/implantar.py prospeccao --skill prospeccao-instagram`. Ele testa numa cópia de estágio
   na VM antes de trocar a viva e grava a versão em `.versao`.
5. Correção de dado vivo: função do helper (com teste), nunca edição do JSON.

## Erros de 11/10 que esta estrutura impede
- **Duas sessões implantando por cima uma da outra** → `implantar.py` recusa versão desconhecida na VM.
- **Registro editado à mão ("duplicada")** → dado só por função; `_mudar()` recusa saltos; diário mostra quem fez.
- **Trava que não solta (mensagem apagada, falhas antigas)** → estado `apagada`; falha antiga não bloqueia depois de
  um envio.
- **Revisor barrando por um motivo falso** → 2ª revisão quando o motivo contradiz o texto.
- **Agente apagando mensagem** → skill proíbe sem ordem explícita e sem ver duas iguais.
