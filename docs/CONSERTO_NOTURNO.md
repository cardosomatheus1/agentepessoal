# Conserto noturno do agente

Decisão do Matheus (21/10): "tem como ele ver a falha e se autocorrigir?" → "Pode fazer, direto no ar como recomendou".
Toda noite uma sessão do Claude Code lê as falhas do agente nas últimas 24 h, conserta as que são defeito das nossas
ferramentas, com teste, implanta e manda um resumo ao celular dele. Este arquivo é o roteiro dessa sessão; mudar o
roteiro é mudar este arquivo (commit), não o prompt da tarefa agendada.

O agente aprende sozinho o **jeito** de fazer as coisas (plugin `aprendizado`: skills e, desde 21/10, o caminho que
funcionou depois de uma falha). Esta sessão cuida do outro lado: o **defeito da ferramenta**, que só se conserta no código.

## Passo a passo

1. Branch `ccr-bcbe3101-9u4klv` do `cardosomatheus1/agentepessoal`: `git pull`. Leia o `CLAUDE.md` e
   `docs/HANDOFF_CONTA_NOVA.md`. As regras deles valem aqui inteiras.
2. `python3 infra/operador/falhas_do_dia.py 24` (e `--json` se quiser os grupos inteiros).
3. Escolha **até 3 grupos** para consertar, nesta ordem de prioridade: mais vezes, mais conversas, efeito maior para o
   Matheus. Só entra grupo que é **defeito nosso** e aconteceu **3 vezes ou mais**:
   - entra: a ferramenta recusa ou erra uma chamada razoável (ex.: ref escrita `"button 22"`, `key` em vez de
     `keys`), a dica de erro manda o agente para o lado errado, um gancho nosso quebra, a conferência barra o que
     devia passar;
   - não entra: site fora do ar, captcha, senha errada, falha de terceiros, falta de permissão, avisos de laço sem
     causa de ferramenta por trás (anote no resumo, não conserte no escuro).
4. Para cada grupo escolhido:
   - confira no `git log` se outra sessão mexeu nesse plugin nas últimas horas; se sim, pule e diga no resumo;
   - escreva o teste **com a chamada exata do relatório** (os `args` e o resultado reais) e veja ele **falhar** no
     código atual;
   - conserte no lugar certo (quase sempre `infra/vm/plugins/navegador_rapido`, `controle_agente` ou o plugin da
     ferramenta); em correção que embrulha método do Agent Zero, use **versão** na marca (`VERSAO_...`) e o original
     guardado (`_original`), senão o servidor rodando não pega a nova (lição de 21/10);
   - `python3 infra/operador/rodar_suites_locais.py` inteiro passando (com
     `A0SRC=<cópia do código do Agent Zero>` quando o teste usa os scripts do navegador);
   - commit com o motivo e o número de falhas que resolve, push, `python3 infra/operador/implantar.py <plugin>`;
   - **confira no servidor**: o log do `agent-zero` (`docker logs`) sem erro do plugin e, quando der, uma chamada de
     teste com `infra/operador/mandar_msg.py` numa conversa nova (mensagem começando com "Teste do operador:"), sem
     mexer em conversa dele.
5. Resumo para o Matheus, em português curto, com `python3 infra/operador/avisar_matheus.py "texto"` (chega como aviso
   de progresso: de madrugada fica guardado e ele recebe de manhã). Formato:
   `🔧 Conserto da noite: <n> falhas do agente corrigidas` + uma linha por grupo (o que acontecia, quantas vezes, o que
   mudou) + o que ficou de fora e por quê. Noite sem nada a consertar: não mande nada.
6. Acrescente uma linha em `docs/CONSERTO_NOTURNO_DIARIO.md` (data, grupos corrigidos com commits, grupos pulados e
   motivo), commit e push.

## Limites (não se quebram)

- Nada de dado vivo editado à mão, nada de mensagem a terceiros, nada destrutivo, nenhum PR, push só no branch acima.
- Uma correção que não dá para provar com teste fica de fora (vai no resumo como "não consertado: motivo").
- No máximo 3 grupos por noite: o resto fica para a próxima.
- Se a suíte ou a implantação falhar e você não conseguir resolver, **não** deixe nada pela metade no ar: desfaça o seu
  commit (novo commit revertendo, nunca reescrever histórico), implante de novo e conte no resumo.
