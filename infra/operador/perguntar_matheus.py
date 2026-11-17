"""Pergunta do operador (Claude Code) ao Matheus no celular, com botões para tocar (17/11, Matheus: "Manda resolva aq
no telegram pra clicar"). Vai pela mesma ponte do agente, como resposta (não espera o horário de silêncio).

Os botões de escolha levam o id "op:<pergunta>:<escolha>": o toque não vai ao Hermes, fica anotado na VM
(/var/lib/agentepessoal/operador_respostas.jsonl, ponte_whatsapp.resposta_operador) e a pessoa recebe "Anotado".
O botão de página (--app) abre um endereço dentro do Telegram (no WhatsApp, o link vai no texto).

Uso, da raiz do repositório:
  python3 infra/operador/perguntar_matheus.py "texto" [--botao ses:sim="Liberar"]... [--app "Abrir navegador"=https://...]
  python3 infra/operador/perguntar_matheus.py --respostas        # as escolhas anotadas (as últimas 30)"""

import base64
import json
import subprocess
import sys
from pathlib import Path

PONTE = "/a0/usr/plugins/whatsapp/helpers/ponte.py"
RESPOSTAS = "/var/lib/agentepessoal/operador_respostas.jsonl"


def montar(argv: list) -> dict:
    """Os argumentos viram {"texto", "botoes", "app"}; erro claro no que a ponte ou o Telegram recusariam."""
    texto, botoes, app = [], [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--botao", "--app"):
            if i + 1 >= len(argv) or "=" not in argv[i + 1]:
                raise ValueError(f"{a} pede chave=valor")
            chave, valor = argv[i + 1].split("=", 1)
            if a == "--botao":
                bid = "op:" + chave.strip()
                if len(bid.encode()) > 64 or not valor.strip():
                    raise ValueError(f"botão inválido (id até 64 bytes, título não vazio): {chave}")
                botoes.append({"id": bid, "titulo": valor.strip()[:20]})
            else:
                if not valor.startswith("https://"):
                    raise ValueError("--app pede um endereço https://")
                app = {"titulo": chave.strip()[:30], "url": valor}
            i += 2
            continue
        texto.append(a)
        i += 1
    if len(botoes) > 3:
        raise ValueError("até 3 botões por mensagem")
    if botoes and app:
        raise ValueError("botões de escolha e botão de página vão em mensagens separadas")
    t = " ".join(texto).strip()
    if not t:
        raise ValueError("sem texto")
    return {"texto": t, "botoes": botoes, "app": app}


def comando(msg: dict) -> str:
    """O comando da VM: a mensagem vai em base64, nenhuma aspa quebra nem executa nada."""
    m = base64.b64encode(json.dumps(msg, ensure_ascii=False).encode("utf-8")).decode()
    py = (f"import base64, json, importlib.util; s = importlib.util.spec_from_file_location('ponte', '{PONTE}'); "
          f"p = importlib.util.module_from_spec(s); s.loader.exec_module(p); d = json.loads(base64.b64decode('{m}')); "
          f"print(p.enviar('matheus', d['texto'], botoes=d['botoes'] or None, tipo='resposta', app=d['app'], "
          f"sempre=True) or 'enviado')")
    return f"/opt/agentepessoal/a0py -c \"{py}\""


def main(argv: list) -> int:
    vm = Path(__file__).resolve().parent / "vmcmd.py"
    if argv[:1] == ["--respostas"]:
        r = subprocess.run([sys.executable, str(vm), f"tail -n 30 {RESPOSTAS} 2>/dev/null || echo '(nenhuma ainda)'"],
                           capture_output=True, text=True)
        print(r.stdout.strip())
        return 0
    try:
        msg = montar(argv)
    except ValueError as exc:
        print(f"erro: {exc}")
        return 2
    r = subprocess.run([sys.executable, str(vm), comando(msg)], capture_output=True, text=True)
    print(r.stdout.strip())
    return 0 if "enviado" in r.stdout else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
