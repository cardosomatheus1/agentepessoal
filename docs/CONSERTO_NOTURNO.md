# Conserto noturno do agente

Decisão do Matheus (21/10): "tem como ele ver a falha e se autocorrigir?" → "Pode fazer, direto no ar como recomendou".
Toda noite uma sessão do Claude Code lê as falhas do agente nas últimas 24 h, conserta as que são defeito das nossas
ferramentas, com teste, implanta e manda um resumo ao celular dele. Este arquivo é o roteiro dessa sessão; mudar o
roteiro é mudar este arquivo (commit), não o prompt da tarefa agendada.

O agente aprende sozinho o **jeito** de fazer as coisas (plugin `aprendizado`: skills e, desde 21/10, o caminho que
funcionou depois de uma falha). Esta sessão cuida do outro lado: o **defeito da ferramenta**, que só se conserta no código.

## Passo a passo

1. Branch `ccr-bcbe3101-9u4klv` do `cardosomatheus1/agentepessoal`: `git pull`. Leia o `CLAUDE.md` e
   `docs/HANDOFF_CONTA_NOVA.md`. As regras deles valem aqui inteiras. O ambiente pode começar sem as ferramentas da
   AWS (1ª conferência, 21/10): `python3 -c "import boto3" 2>/dev/null || pip install -q boto3` e
   `command -v aws >/dev/null || pip install -q awscli`.
2. `python3 infra/operador/falhas_do_dia.py 24` (e `--json` se quiser os grupos inteiros).
3. Escolha **até 3 grupos** para consertar, nesta ordem de prioridade: mais vezes, mais conversas, efeito maior para o
   Matheus. Só entra grupo que é **defeito nosso** e aconteceu **3 vezes ou mais**:
   - entra: a ferramenta recusa ou erra uma chamada razoável (ex.: ref escrita `"button 22"`, `key` em vez de
     `keys`), a dica de erro manda o agente para o lado errado, um gancho nosso quebra, a conferência barra o que
     devia passar;
   - não entra: site fora do ar, captcha, senha errada, falha de terceiros, falta de permissão, avisos de laço sem
     causa de ferramenta por trás (anote no resumo, não conserte no escuro).
4. Para cada grupo escolhido:
   - confira no `git log` se outra sessão mexeu nesse plugin nas **últimas 2 horas** (pode estar trabalhando nele
     agora); se sim, pule e diga no resumo. Commit mais antigo que isso é trabalho terminado: não impede (21/10: a 1ª
     rodada pulou tudo por causa dos commits do dia);
   - escreva o teste **com a chamada exata do relatório** (os `args` e o resultado reais) e veja ele **falhar** no
     código atual;
   - conserte no lugar certo (quase sempre `infra/vm/plugins/navegador_rapido`, `controle_agente` ou o plugin da
     ferramenta); em correção que embrulha método do Agent Zero, use **versão** na marca (`VERSAO_...`) e o original
     guardado (`_original`), senão o servidor rodando não pega a nova (lição de 21/10);
   - `python3 infra/operador/rodar_suites_locais.py` inteiro passando (com
     `A0SRC=<cópia do código do Agent Zero>` quando o teste usa os scripts do navegador);
   - commit com o motivo e o número de falhas que resolve;
   - **revisão independente com OpenCode 2 + Opus 5.5** (decisão #35 do Matheus: toda alteração de código passa por
     ele): `python3 infra/operador/revisar_opencode.py <commit>~1..<commit> "o que a correção resolve"`. Só segue com
     `VEREDITO: APROVADO`. REPROVADO: corrija o que ele apontou (novo commit) e revise de novo; na 2ª reprovação,
     reverta e deixe para o resumo. Ponto menor que ele aponte e seja barato: corrija junto. Se o revisor não rodar
     (saída 2), não implante: conte no resumo;
   - push, `python3 infra/operador/implantar.py <plugin>`;
   - **confira no servidor**: o log do `agent-zero` (`docker logs`) sem erro do plugin e, quando der, uma chamada de
     teste com `infra/operador/mandar_msg.py` numa conversa nova (mensagem começando com "Teste do operador:"), sem
     mexer em conversa dele.
5. Resumo para o Matheus, em português curto, com `python3 infra/operador/avisar_matheus.py "texto"` (chega como aviso
   de progresso: de madrugada fica guardado e ele recebe de manhã). Formato:
   `🔧 Conserto da noite: <n> falhas do agente corrigidas` + uma linha por grupo (o que acontecia, quantas vezes, o que
   mudou) + o que ficou de fora e por quê + "Revisado por OpenCode 2 com Opus 5.5: aprovado" (ou o que ele reprovou). Noite sem nada a consertar: não mande nada.
6. Acrescente uma linha em `docs/CONSERTO_NOTURNO_DIARIO.md` (data, grupos corrigidos com commits, grupos pulados e
   motivo), commit e push.

## Casos marcados pelo operador

Valem como grupo a consertar mesmo com menos de 3 vezes (efeito grande para o Matheus). Depois de consertado, apague a linha.

- 21/10, portal da 99 (developer-food.99app.com): no formulário da loja de teste, o agente pôs a **senha do cofre no
  campo "telefone do gerente"**. Ele percebeu, limpou e cancelou, e nada foi enviado. Ache no log a chamada que
  preencheu o campo (cofre ou `type` com a senha) e faça a ferramenta recusar escrever um segredo do cofre num campo
  que não é de senha (`type=password`, ou nome/rótulo de senha). O teste usa a chamada real.

## Limites (não se quebram)

- Nada de dado vivo editado à mão, nada de mensagem a terceiros, nada destrutivo, nenhum PR, push só no branch acima.
- Uma correção que não dá para provar com teste fica de fora (vai no resumo como "não consertado: motivo").
- No máximo 3 grupos por noite: o resto fica para a próxima.
- Se a suíte ou a implantação falhar e você não conseguir resolver, **não** deixe nada pela metade no ar: desfaça o seu
  commit (novo commit revertendo, nunca reescrever histórico), implante de novo e conte no resumo.
