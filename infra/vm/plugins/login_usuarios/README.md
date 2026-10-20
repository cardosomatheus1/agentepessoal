# Login com vários usuários

- Contas em `/a0/usr/usuarios.json` (só hash PBKDF2, fora do git). Criar/trocar senha na VM:
  `sudo python3 /opt/agentepessoal/usuarios.py <login> "<Nome>" '<senha>'` · remover: `--remover <login>`.
- Sessão de 400 dias (navegador e app). Hibernar não desloga; depois de um reinício completo da
  máquina o endereço do agente muda e é preciso entrar de novo uma vez.
- 5 senhas erradas do mesmo IP bloqueiam por 15 minutos.
- Cada pessoa tem a sua ficha `memoria/usuarios/<login>.md`; o agente sabe quem está falando em cada conversa.
- As conversas são compartilhadas: todos os usuários veem todas.

## Convidados (15/10: Ilia, amigo do Matheus)
- Lista e teto em `helpers/convidados.py` (`CONVIDADOS`); o teto também está em `ponte_whatsapp.py`
  (`CONVIDADOS_TETO`, um teste confere que batem).
- O convidado só fala pelo Telegram ("Conectar ilia" na página de controle gera o link de 15 min). As conversas
  dele rodam no projeto `convidado-<login>`: memória própria e só as ferramentas de `FERRAMENTAS` (conversa,
  pesquisa, navegador, arquivos que ele mandou, notas e cofre dele). Nada da Raiz, das contas do Matheus, terminal,
  editor de arquivos ou tarefas agendadas. A trava roda duas vezes: política do projeto (`_tool_access`) e
  `tool_execute_before/_02_convidado.py` (também recusa caminho local fora das pastas dele e endereço interno).
- Gasto por pessoa: toda chamada de modelo leva `X-A0-Dono`; o proxy grava `dono` em `uso.jsonl`. Passou do teto
  no dia, a ponte avisa o convidado e não entrega a mensagem até o dia seguinte. `/gasto` do convidado mostra só o dele.
- Rotinas (16/10, Matheus: "os convidados devem poder"): o convidado cria tarefas agendadas no projeto dele (até 5,
  no máximo de hora em hora); só vê e mexe nas dele (`regra_agenda`, `filtrar_agenda`); a conversa da rotina é dele
  (dono = dono do projeto, `separacao.dono_contexto`), então gasta e avisa como ele. Passou do teto do dia, a ponte
  grava `whatsapp/<login>/limite_hoje.txt` e `job_loop/_20_limite_convidados.py` pausa as rotinas até o dia seguinte.
- Novo convidado: some em `CONVIDADOS` e `CONVIDADOS_TETO`, em `LOGINS` de `infra/control/index.py`, teste, implante.

**Modelo por dono e por conversa (20/10, pronto e DESLIGADO):** `helpers/modelo.py` + `monologue_start/_30_modelo_por_dono.py`.
Sem o arquivo `/a0/usr/plugins/login_usuarios/modelo_por_dono.json` nada muda. Com ele
(`{"donos": {"matheus": "Sonnet"}, "conversas": {"<id>": "Default"}, "rotinas": false}`), cada mensagem do agente
principal escolhe o preset do seletor de modelos (presets.yaml) pela conversa ou pelo dono; rotinas ficam no padrão
salvo `"rotinas": true`. Usa a mesma escolha da tela (`chat_model_override`) e nunca troca nem desfaz uma escolha
feita à mão. Apagar o arquivo volta cada conversa ao padrão na mensagem seguinte. O proxy já registra `modelo` e
`dono` de cada chamada em `uso.jsonl`.
