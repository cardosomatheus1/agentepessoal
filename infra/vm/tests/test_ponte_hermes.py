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

    def hermes(caminho, corpo=None, timeout=60, usuario=""):
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
    # virada (fase 8): botões e comandos que o A0 tratava sem modelo, mensagem nova entra no pedido que roda, convidados
    # no Hermes deles, /conversa só para quem está no Hermes, "ok" de cartão já enviado não vai de novo
    p.HERMES_CONVIDADOS = tmp / "convidados"
    (p.HERMES_CONVIDADOS / "ilia").mkdir(parents=True)
    (p.HERMES_CONVIDADOS / "ilia" / "porta").write_text("8660\n")
    ok(p.instancia("ilia") == ("http://127.0.0.1:8660", "hermes-ilia") and p.instancia("matheus") == (p.HERMES_URL, "hermes"),
       "convidado no Hermes dele (porta própria); o resto no principal")
    exec_botoes = []
    p.botao_hermes = lambda usuario, dados: exec_botoes.append((usuario, dados.get("botao"), dados.get("texto"))) or {"ok": True, "texto": "PAINEL"}
    n = len(chamadas)
    p.entregar_hermes({"usuario": "matheus", "texto": "✅ Aprovar", "botao": "pa:matheus:a1:aprovar"}, "123")
    ok(exec_botoes[-1] == ("matheus", "pa:matheus:a1:aprovar", "✅ Aprovar") and len(chamadas) == n,
       "botão da prospecção roda as funções do A0 no Hermes, sem abrir pedido ao modelo")
    p.entregar_hermes({"usuario": "matheus", "texto": "Aprovar", "botao": "aprov:ctx:1:aprovar"}, "123")
    ok("agente antigo" in enviados[-1][1] and len(chamadas) == n, "botão de ok do A0: avisa que não está mais aberto")
    for cmd in ("/pendentes", "/ajuda", "/atividade"):
        p.entregar_hermes({"usuario": "matheus", "texto": cmd, "botao": ""}, "123")
        ok(exec_botoes[-1][2] == cmd and len(chamadas) == n, f"{cmd} respondido sem o modelo")
    p.DESTINO.write_text(json.dumps({"padrao": "hermes"}))
    p.linha_livro = lambda u: "LIVRO"
    p.linha_saude = lambda: "SAUDE"
    p.texto_gasto = lambda u="matheus": "GASTO"
    painel = p.texto_painel("matheus")
    ok("PAINEL" in painel and "Fazendo agora" in painel and "GASTO" in painel, f"/painel pelo Hermes: {painel[:200]}")
    respostas["/v1/runs"] = {"run_id": "run_7"}
    p.entregar_hermes({"usuario": "matheus", "texto": "faz X", "botao": ""}, "123")
    ok(p.ativos_hermes("matheus") == ["run_7"], "o pedido fica entre os que rodam")
    respostas["/v1/runs/run_7/steer"] = {"accepted": True}
    r = p.entregar_hermes({"usuario": "matheus", "texto": "e também Y", "botao": ""}, "123")
    ok(r == "run_7" and chamadas[-1] == ("/v1/runs/run_7/steer", {"input": "e também Y"}),
       "mensagem com um pedido rodando entra nele (como a correção do A0)")
    p.entregar_hermes({"usuario": "matheus", "texto": "/parar", "botao": ""}, "123")
    ok(chamadas[-1] == ("/v1/runs/run_7/stop", {}) and p.ativos_hermes("matheus") == [] and "Parei" in enviados[-1][1],
       "/parar para o que roda")
    p.entregar_hermes({"usuario": "matheus", "texto": "/nova", "botao": ""}, "123")
    nova = p.sessao_hermes("matheus")
    ok(nova.startswith("tg-matheus-") and json.loads(p.HERMES_SESSOES.read_text()).get(nova) == "matheus",
       f"/nova começa outra sessão (mapeada para ele): {nova}")
    respostas["/v1/runs"] = {"run_id": "run_8"}
    p.entregar_hermes({"usuario": "matheus", "texto": "oi", "botao": ""}, "123")
    ok(chamadas[-1][1]["session_id"] == nova, "depois de /nova, os pedidos vão à sessão nova")
    respostas["/v1/runs/run_9"] = [{"status": "completed", "output": "ok"}]
    n = len(enviados)
    p.acompanhar_hermes("run_9", "matheus", "123", espera=5, pausa=0)
    ok(len(enviados) == n, "o 'ok' depois de um cartão com botões não vai de novo (como no A0)")
    # WhatsApp sem Telegram: a resposta vai pelo número
    p._cfg, p._cfg_em = {"numeros": {"5571": "fernanda"}}, 9e18
    pelo_zap = []
    p.enviar_texto = lambda numero, texto: pelo_zap.append((numero, texto))
    p.responder_hermes("fernanda", "", "oi")
    ok(pelo_zap == [("5571", "oi")], "sem Telegram, a resposta do Hermes vai pelo WhatsApp")
    # o Hermes fora do ar (subindo): a mensagem espera na fila, não some
    spec2 = importlib.util.spec_from_file_location("ponte_hermes_teste2", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    p2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(p2)
    p2.HERMES_URL, p2.HERMES_CHAVE = "http://127.0.0.1:9", p.HERMES_CHAVE
    try:
        p2._hermes("/v1/runs", {"input": "x"})
        ok(False, "Hermes fora do ar devia segurar a mensagem")
    except p2.AgenteFora:
        pass
    # /conversa: só a chave da ponte, só quem está no Hermes
    p.DESTINO.write_text(json.dumps({"padrao": "a0"}))
    respostas_http = []

    class Req:
        def __init__(self, corpo, chave_ok=True):
            self.path, self.headers = "/conversa", {"X-Chave": "c" if chave_ok else "x", "Content-Length": str(len(corpo))}
            self.rfile = __import__("io").BytesIO(corpo)
    p.chave = lambda: "c"
    for corpo, chave_ok, esperado in ((b'{"usuario":"matheus","texto":"oi"}', True, 409),
                                      (b'{"usuario":"matheus","texto":"oi"}', False, 403)):
        r = Req(corpo, chave_ok)
        r._responder = lambda code, c: respostas_http.append(code)
        p.Saida.do_POST(r)
        ok(respostas_http[-1] == esperado, f"/conversa responde {esperado}: {respostas_http[-1]}")
    # 23/10 isolamento dos convidados (Matheus: "de forma alguma acessar nada meu"): cofre do convidado numa pasta só
    # dele; a chave da ponte dele só serve para ele mesmo; arquivo só da pasta dele, nunca um do Matheus
    p.HERMES_CONVIDADOS = tmp / "convidados2"
    (p.HERMES_CONVIDADOS / "ilia").mkdir(parents=True)
    (p.HERMES_CONVIDADOS / "ilia" / "porta").write_text("8660")
    (p.HERMES_CONVIDADOS / "ilia" / "chave").write_text("chave-da-ilia")
    ok(p.pasta_cofre("ilia") == p.COFRE / "convidados" / "ilia" and p.pasta_cofre("matheus") == p.COFRE,
       "cofre do convidado na pasta só dele (o Hermes dele monta só ela)")
    p.cfg = lambda: {"tg_chats": {}}
    p.comando_cofre("ilia", "/senha WIFI senhaDaIlia99")
    ok(json.loads((p.COFRE / "convidados" / "ilia" / "ilia.json").read_text()).get("WIFI") == "senhaDaIlia99"
       and "senhaDaIlia99" not in (p.COFRE / "ilia.json").read_text(), "o /senha do convidado vai à pasta dele")
    ok(p.mascarar_cofres("é senhaDaIlia99") == "é §§secret(WIFI)", "e o valor dele é mascarado também")
    ok(p.chave_convidado_ok("ilia", "chave-da-ilia") and not p.chave_convidado_ok("ilia", "outra")
       and not p.chave_convidado_ok("matheus", "chave-da-ilia"), "chave própria do convidado")
    p.chave = lambda: "chave-principal"
    for caminho, usuario, esperado in (("/enviar", "matheus", 403), ("/conversa", "matheus", 403),
                                       ("/configurar", "ilia", 403), ("/gatilho_url", "ilia", 403),
                                       ("/enviar", "Ilia ", 403)):
        corpo = json.dumps({"usuario": usuario, "texto": "oi"}).encode()
        r = Req(corpo, True)
        r.path, r.headers = caminho, {"X-Chave": "chave-da-ilia", "Content-Length": str(len(corpo))}
        r._responder = lambda code, c: respostas_http.append(code)
        p.Saida.do_POST(r)
        ok(respostas_http[-1] == esperado, f"chave da Ilia em {caminho} para {usuario!r}: {respostas_http[-1]}")
    raiz = p.HERMES_CONVIDADOS / "ilia" / "a0usr"
    (raiz / "workdir").mkdir(parents=True)
    (raiz / "workdir" / "lista.pdf").write_text("x")
    p.USR_HOST = tmp / "usr"
    (p.USR_HOST / "whatsapp" / "ilia").mkdir(parents=True)
    (p.USR_HOST / "whatsapp" / "ilia" / "foto.jpg").write_text("x")
    (p.USR_HOST / "segredos").mkdir(parents=True)
    (p.USR_HOST / "segredos" / "matheus.json").write_text("{}")
    (p.USR_HOST / "prospeccao").mkdir()
    (p.USR_HOST / "prospeccao" / "matheus.json").write_text("{}")
    ok(p.arquivo_do_pedido("/a0/usr/workdir/lista.pdf", "ilia") == (raiz / "workdir" / "lista.pdf").resolve()
       and p.arquivo_do_pedido("/a0/usr/whatsapp/ilia/foto.jpg", "ilia") is not None, "o convidado manda os arquivos dele")
    for ruim in ("/a0/usr/segredos/matheus.json", "/a0/usr/prospeccao/matheus.json", str(p.USR_HOST / "segredos" / "matheus.json"),
                 "/a0/usr/whatsapp/ilia/../../segredos/matheus.json", "/a0/usr/../../etc/passwd"):
        ok(p.arquivo_do_pedido(ruim, "ilia") is None, f"o convidado nunca manda arquivo do Matheus: {ruim}")
    ok(p.arquivo_do_pedido("/a0/usr/prospeccao/matheus.json", "") is not None, "o agente do Matheus manda os dele")
    for f in falhas:
        print("FALHA", f)
    print("ponte_hermes:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
