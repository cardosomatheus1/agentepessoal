"""The A0/Hermes key of the phone bridge (23/10 migration, phase 6): each login goes to the A0 by default and to the
Hermes when the destination file says so; through the Hermes a message opens a run in the person's fixed session
(written in the plugin's session map, readable by the Hermes), a value of any vault the person pasted becomes
§§secret(NAME) before it leaves the bridge, a request for his ok becomes 3 buttons whose short id answers the run's
approval with the exact request id, and the final answer goes to the person (teste_* logins: to a file, no phone).
Run from the repository root: python3 infra/vm/tests/test_ponte_hermes.py (boto3 needed for the import, no AWS call)."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def main() -> int:
    spec = importlib.util.spec_from_file_location("ponte_hermes_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    tmp = Path(tempfile.mkdtemp(prefix="ponte-hermes-"))
    p.DESTINO = tmp / "destino.json"
    p.HERMES_SESSOES = tmp / "hermes" / "sessoes.json"
    p.HERMES_TESTE = tmp / "hermes_teste.jsonl"
    p.HERMES_CHAVE = tmp / "api_key"
    p.HERMES_CHAVE.write_text("k" * 64)
    p.COFRE = tmp / "segredos"
    p.COFRE.mkdir()
    (p.COFRE / "matheus.json").write_text(json.dumps({"IG_SENHA": "senhaForte123", "PIN": "12"}))
    (p.COFRE / "ilia.json").write_text(json.dumps({"OUTRA": "valorDaIlia9"}))
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    # the key: A0 by default, Hermes per login or for everyone
    ok(p.destino("matheus") == "a0", "sem o arquivo: tudo no A0")
    p.DESTINO.write_text(json.dumps({"padrao": "a0", "logins": {"teste_hermes": "hermes"}}))
    ok(p.destino("teste_hermes") == "hermes" and p.destino("matheus") == "a0", "só o login de teste no Hermes")
    p.DESTINO.write_text(json.dumps({"padrao": "hermes", "logins": {"ilia": "a0"}}))
    ok(p.destino("matheus") == "hermes" and p.destino("ilia") == "a0", "a virada: padrão Hermes, exceção por login")
    p.DESTINO.write_text("{quebrado")
    ok(p.destino("matheus") == "a0", "arquivo ilegível: volta ao A0 (nunca some mensagem)")

    # session map the plugin reads (owner of the tools and of the vault)
    ok(p.sessao_hermes("Matheus") == "tg-matheus", "sessão fixa por pessoa")
    p.sessao_hermes("ilia")
    mapa = json.loads(p.HERMES_SESSOES.read_text())
    ok(mapa == {"tg-matheus": "matheus", "tg-ilia": "ilia"}, f"mapa de sessões do plugin: {mapa}")

    # pasted vault values never leave the bridge
    ok(p.mascarar_cofres("a senha é senhaForte123 e a da ilia valorDaIlia9, pin 12") ==
       "a senha é §§secret(IG_SENHA) e a da ilia §§secret(OUTRA), pin 12", "valor colado vira o nome; curto fica")

    # a message opens a run; approvals become buttons; the answer goes back
    chamadas, respostas = [], {}

    def hermes(caminho, corpo=None, timeout=60):
        chamadas.append((caminho, corpo))
        return respostas[caminho].pop(0) if isinstance(respostas.get(caminho), list) else respostas.get(caminho, {})

    p._hermes = hermes
    enviados = []
    p.tg_texto = lambda chat, texto, botoes=None, app=None: enviados.append((chat, texto, botoes))
    threads = []
    p.threading.Thread = lambda target, args, daemon, name: type("T", (), {"start": lambda self: threads.append((target, args))})()
    respostas["/v1/runs"] = {"run_id": "run_1"}
    run = p.entregar_hermes({"usuario": "matheus", "texto": "minha senha é senhaForte123, entra lá", "anexos": ["/a0/usr/x.pdf"],
                             "audio": "", "botao": ""}, "123")
    corpo = chamadas[-1][1]
    ok(run == "run_1" and corpo["session_id"] == "tg-matheus" and "§§secret(IG_SENHA)" in corpo["input"]
       and "senhaForte123" not in corpo["input"] and "/a0/usr/x.pdf" in corpo["input"], f"o pedido ao Hermes: {corpo}")
    respostas["/v1/runs/run_1"] = [
        {"status": "running"},
        {"status": "waiting_for_approval", "approval": {"request_id": "req9", "description": "Publicar post no site X"}},
        {"status": "waiting_for_approval", "approval": {"request_id": "req9", "description": "Publicar post no site X"}},
        {"status": "completed", "output": "Feito: publicado e conferido."}]
    alvo, args = threads[-1]
    estado = alvo(*args, espera=30, pausa=0)
    botoes = enviados[0][2]
    ok(estado == "completed" and len(enviados) == 2 and "Preciso do seu ok" in enviados[0][1] and len(botoes) == 3
       and all(len(b["id"]) <= 64 for b in botoes), f"um pedido de ok = 3 botões (uma vez só): {enviados}")
    ok(enviados[1] == ("123", "Feito: publicado e conferido.", None), f"a resposta final vai à pessoa: {enviados[1]}")
    aprovar = next(b["id"] for b in botoes if b["id"].endswith(":aprovar"))
    p.entregar_hermes({"usuario": "matheus", "texto": "", "botao": aprovar}, "123")
    ok(chamadas[-1] == ("/v1/runs/run_1/approval", {"choice": "once", "request_id": "req9"}),
       f"o botão responde o run com o id exato do pedido: {chamadas[-1]}")
    n = len(chamadas)
    p.entregar_hermes({"usuario": "matheus", "texto": "", "botao": aprovar}, "123")
    ok(len(chamadas) == n and "já foi respondido" in enviados[-1][1], "o mesmo botão de novo não aprova outra vez")
    tarefa = next(b["id"] for b in botoes if b["id"].endswith(":tarefa"))
    ok(tarefa.split(":")[1] not in p._HERMES_OKS, "um pedido respondido sai da lista (Nesta tarefa também)")

    # teste_* logins: nothing to a phone, the operator reads the file
    respostas["/v1/runs"] = {"run_id": "run_2"}
    respostas["/v1/runs/run_2"] = [{"status": "completed", "output": "PONTE HERMES OK"}]
    p.entregar_hermes({"usuario": "teste_hermes", "texto": "oi", "botao": ""}, "0")
    alvo, args = threads[-1]
    alvo(*args, espera=5, pausa=0)
    linhas = [json.loads(x) for x in p.HERMES_TESTE.read_text().splitlines()]
    ok(linhas[-1]["texto"] == "PONTE HERMES OK" and linhas[-1]["usuario"] == "teste_hermes" and len(enviados) == 3,
       f"login de teste: resposta no arquivo, nada no Telegram ({linhas})")
    # a long request gets the progress message (edited in place), closed at the end
    andamentos = []
    p.andamento = lambda usuario, texto, fim=False: andamentos.append((usuario, texto, fim)) or "ok"
    p.HERMES_ANDAMENTO_APOS, p.HERMES_ANDAMENTO_CADA = 0, 0
    respostas["/v1/runs/run_4"] = [{"status": "running", "last_event": "tool.started"},
                                   {"status": "running", "last_event": "tool.completed"},
                                   {"status": "completed", "output": "pronto"}]
    p.acompanhar_hermes("run_4", "matheus", "123", espera=5, pausa=0)
    ok(len(andamentos) == 3 and andamentos[0][1].startswith("⏳ Trabalhando") and andamentos[-1] == ("matheus", "✅ Terminei", True),
       f"andamento editado durante o pedido e fechado no fim: {andamentos}")
    respostas["/v1/runs/run_5"] = [{"status": "running"}, {"status": "completed", "output": "x"}]
    n = len(andamentos)
    p.acompanhar_hermes("run_5", "teste_hermes", "0", espera=5, pausa=0)
    ok(len(andamentos) == n, "login de teste: sem andamento no Telegram")
    # a trigger from outside (Google watcher) goes to its own session, as data, quiet when nothing matters
    p.USR_HOST = tmp
    (tmp / "gatilhos" / "matheus").mkdir(parents=True)
    (tmp / "gatilhos" / "matheus" / "vigia_google.md").write_text("Conta nova: salve com `contas`; reunião: `reuniao` agendar.")
    respostas["/v1/runs"] = {"run_id": "run_6"}
    p.entregar_hermes({"usuario": "matheus", "gatilho": "vigia_google", "texto": "evento novo: Reunião X"}, "123")
    corpo = chamadas[-1][1]
    ok(corpo["session_id"] == "gatilhos-matheus" and "Gatilho «vigia_google» disparou" in corpo["input"]
       and "Conta nova: salve com `contas`" in corpo["input"] and "dado externo" in corpo["input"]
       and "evento novo" in corpo["input"], f"gatilho na sessão própria, com a instrução dele, conteúdo como dado: {corpo}")
    respostas["/v1/runs/run_3"] = [{"status": "completed", "output": "SEM NOVIDADE"}]
    n = len(enviados)
    p.acompanhar_hermes("run_3", "matheus", "123", espera=5, pausa=0)
    ok(len(enviados) == n, "SEM NOVIDADE não vai ao celular")
    for f in falhas:
        print("FALHA", f)
    print("ponte_hermes:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
