"""Item 6 of docs/AUDITORIA_MATURIDADE_AGENTE.md: the terminal told the agent nothing when a command failed (no exit
code), and in 4 days of logs (21/10) it returned 284 times with "no output after 30 s / might be still running"; the
agent then reset the terminal or ran the command again, killing what was still working. Hermes (terminal_tool) returns
the exit code with the output; OpenClaw (bash-tools) adds the next step for the common errors. Both, here:
- before: a terminal command gets one line that prints the exit code when it is not 0;
- after: the output gets the next step for the error it shows."""

import re

MARCA = "⟦código de saída"
LINHA = '__a0rc=$?; [ "$__a0rc" -ne 0 ] && echo "⟦código de saída $__a0rc⟧"'
RESPOSTAS = re.compile(r"^\s*(y|n|yes|no|s|sim|q|quit|exit|\d{1,2})\s*$", re.I)  # answers to a program, not commands


def com_codigo_de_saida(codigo: str) -> str:
    """The command plus the exit-code line. Left as is: answers typed into a running program, a command that continues on
    the next line (\\ or |), one sent to the background, or one that already has the line."""
    texto = str(codigo or "")
    fim = texto.rstrip()
    if (not fim or MARCA in texto or "__a0rc" in texto or RESPOSTAS.match(texto)
            or fim.endswith(("\\", "|", "&&", "||")) or (fim.endswith("&") and not fim.endswith("&&"))):
        return texto
    return fim + "\n" + LINHA


def codigo_de_saida(saida: str) -> int | None:
    m = re.findall(r"⟦código de saída (\d+)⟧", str(saida or ""))
    if m:
        return int(m[-1])
    m = re.findall(r"exit code (\d+)", str(saida or ""))
    return int(m[-1]) if m else None


AINDA_RODANDO = (re.compile(r"(after \d+ seconds with no output|might be still running|Returning control to agent)", re.I),
     "O comando CONTINUA rodando (o terminal só parou de esperar). Para esperar o fim, chame code_execution_tool com "
     "runtime \"output\" na mesma session (espera até 10 min). Não use reset (mata o comando) e não rode de novo. Para "
     "algo que demora muito, rode em segundo plano com saída num arquivo (`cmd > /tmp/x.log 2>&1 &`) e leia o arquivo.")
# Only when the command failed (exit code not 0, or a Python error): ordinary output often mentions "not found".
DICAS = [
    (re.compile(r"python: (command )?not found|/python: No such file", re.I),
     "Aqui não existe `python`: use `python3`."),
    (re.compile(r"pip: (command )?not found|pip3?: No such file", re.I),
     "Aqui não existe `pip`: use `python3 -m pip install --break-system-packages X` (terminal) ou "
     "`/opt/venv-a0/bin/pip install X` (para o runtime python)."),
    (re.compile(r"No module named ['\"]?([\w.]+)", re.I),
     "Falta um módulo Python: instale (`python3 -m pip install --break-system-packages <módulo>`; no runtime python, "
     "`/opt/venv-a0/bin/pip install <módulo>`) e rode de novo. Confira antes se o nome do pacote é outro "
     "(ex.: yaml → pyyaml, cv2 → opencv-python, PIL → pillow)."),
    (re.compile(r"externally-managed-environment", re.I),
     "O pip do sistema recusa instalar: acrescente `--break-system-packages` ou use `/opt/venv-a0/bin/pip`."),
    (re.compile(r"(command not found|: not found)", re.I),
     "O comando não existe aqui. Confira o nome (`command -v nome`), procure um parecido (`ls /usr/bin | grep parte`) "
     "ou instale (`apt-get install -y pacote`)."),
    (re.compile(r"Permission denied", re.I),
     "Sem permissão: para script, rode com o interpretador (`bash x.sh`, `python3 x.py`) ou `chmod +x`; para pasta do "
     "sistema, grave em /a0/usr/workdir."),
    (re.compile(r"No such file or directory", re.I),
     "Arquivo ou pasta não existe nesse caminho. Confira com `ls` ou `find /a0/usr -name 'parte*'`; caminho relativo "
     "depende da pasta atual (`pwd`)."),
    (re.compile(r"(\bKilled\b|exit code 137|código de saída 137)", re.I),
     "O processo foi morto por falta de memória: processe em partes menores (páginas, lotes) ou libere memória."),
    (re.compile(r"(syntax error near unexpected token|unexpected EOF while looking for matching)", re.I),
     "Erro de aspas no bash: ponha o script num heredoc (`python3 - <<'PY' ... PY`) ou num arquivo, em vez de aspas "
     "dentro de aspas."),
]


def dica(saida: str) -> str:
    """The next step to add to a terminal result, or ''."""
    saida = str(saida or "")
    if "↳ Próximo passo" in saida:
        return ""
    rc = codigo_de_saida(saida)
    falhou = rc not in (None, 0) or "Traceback (most recent call last)" in saida or "-" * 40 + "\n" in saida
    passos = [AINDA_RODANDO[1]] if AINDA_RODANDO[0].search(saida) else []
    if falhou:
        passos += [texto for padrao, texto in DICAS if padrao.search(saida)]
    if rc not in (None, 0) and len(passos) == 0:
        passos.append(f"O comando falhou (código {rc}). Leia o erro acima e corrija a causa antes de tentar outra coisa; "
                      "não rode o mesmo comando de novo.")
    if not passos:
        return ""
    return "\n\n↳ Próximo passo: " + " ".join(passos[:3])
