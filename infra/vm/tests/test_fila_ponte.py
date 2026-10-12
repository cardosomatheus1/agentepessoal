"""Phone messages are never lost while the agent is starting: they go back to the queue (the person is told once), are
given up only after ~25 min (kept aside, the person told to resend), and a Telegram update re-sent by Telegram is
handled once. Run from the repository root: python3 infra/vm/tests/test_fila_ponte.py (boto3 for the import; no AWS)."""

import http.server
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FilaFalsa:
    def __init__(self):
        self.apagadas, self.voltas = [], []

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.apagadas.append(ReceiptHandle)

    def change_message_visibility(self, QueueUrl, ReceiptHandle, VisibilityTimeout):
        self.voltas.append((ReceiptHandle, VisibilityTimeout))


def main() -> int:
    p = _carregar("ponte_fila_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    tmp = Path(tempfile.mkdtemp(prefix="fila-ponte-"))
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    try:
        fila, ditos, entregues, logs = FilaFalsa(), [], [], []
        p.sqs, p.VISTOS, p.NAO_ENTREGUES, p.ATIVIDADE = fila, tmp / "vistos.json", tmp / "nao_entregues.jsonl", tmp / "a"
        p.PAUSA_ENTREGA, p.log = 0, logs.append
        p.tg = lambda metodo, dados: {}
        p.tg_texto = lambda chat, texto, botoes=None: ditos.append(("tg", texto))
        p.enviar_texto = lambda numero, texto: ditos.append(("wa", texto))
        p.lido_e_digitando = lambda mid: None
        p.comando_cofre = p.comando_silencio = lambda usuario, texto: None
        p.preparar = lambda item: {"usuario": item["usuario"], "texto": item["mensagem"]["text"]["body"]}
        modo = {"erro": None}

        def entregar(dados):
            entregues.append(dados)
            if modo["erro"]:
                raise modo["erro"]

        p.entregar = entregar

        def tg(update_id, vezes=1, texto="oi"):
            corpo = {"canal": "telegram", "usuario": "matheus", "chat": "42",
                     "update": {"update_id": update_id, "message": {"message_id": 1, "chat": {"id": 42}, "text": texto}}}
            return {"Body": json.dumps(corpo), "ReceiptHandle": f"r{update_id}-{vezes}", "MessageId": "m",
                    "Attributes": {"ApproximateReceiveCount": str(vezes)}}

        # delivered, then the same update re-sent by Telegram
        p.tratar("fila", tg(100))
        ok(len(entregues) == 1 and fila.apagadas == ["r100-1"], "entregue e apagada da fila")
        p.tratar("fila", tg(100, texto="oi"))
        ok(len(entregues) == 1 and fila.apagadas[-1] == "r100-1", "o mesmo update de novo não chega 2× ao agente")

        # agent down: back to the queue, said once; given up only after TENTATIVAS_FILA
        modo["erro"] = urllib.error.URLError("connection refused")
        ditos.clear()
        p.tratar("fila", tg(200, 1))
        ok(fila.voltas == [("r200-1", p.VOLTA_FILA)] and "r200-1" not in fila.apagadas, "volta para a fila, não some")
        ok(len(ditos) == 1 and "fila" in ditos[0][1], f"avisa uma vez que está na fila: {ditos}")
        ok(len(entregues) == 1 + p.TENTATIVAS_ENTREGA, "tentou por cerca de um minuto antes de devolver")
        p.tratar("fila", tg(200, 2))
        ok(len(ditos) == 1 and fila.voltas[-1][0] == "r200-2", "na segunda volta não repete o aviso")
        p.tratar("fila", tg(200, p.TENTATIVAS_FILA))
        ok(fila.apagadas[-1] == f"r200-{p.TENTATIVAS_FILA}" and "não chegou" in ditos[-1][1], f"desiste e diz: {ditos[-1]}")
        guardada = [json.loads(l) for l in p.NAO_ENTREGUES.read_text().splitlines()]
        ok(guardada and guardada[0]["item"]["update"]["update_id"] == 200, "a mensagem fica guardada no host")

        # the agent answered and refused (4xx): no point in retrying
        n = len(entregues)
        modo["erro"] = urllib.error.HTTPError("u", 403, "sem acesso", {}, None)
        p.tratar("fila", tg(300))
        ok(len(entregues) == n + 1 and fila.apagadas[-1] == "r300-1", "recusa do agente não fica tentando")
        ok("Não consegui entregar" in ditos[-1][1], "e diz que não entregou")

        # WhatsApp: same queueing
        modo["erro"] = urllib.error.URLError("connection refused")
        wa = {"Body": json.dumps({"usuario": "matheus", "numero": "5571", "mensagem": {"id": "wamid.9", "text": {"body": "oi"}}}),
              "ReceiptHandle": "w1", "MessageId": "m", "Attributes": {"ApproximateReceiveCount": "1"}}
        ditos.clear()
        p.tratar("fila", wa)
        ok(fila.voltas[-1] == ("w1", p.VOLTA_FILA) and "w1" not in fila.apagadas, "WhatsApp também volta para a fila")
        ok(ditos and ditos[0][0] == "wa" and "fila" in ditos[0][1], "e avisa pelo WhatsApp")
        modo["erro"] = None
        p.tratar("fila", {**wa, "ReceiptHandle": "w2", "Attributes": {"ApproximateReceiveCount": "2"}})
        ok(fila.apagadas[-1] == "w2", "quando o agente sobe, chega e sai da fila")
        # /foco: holds progress notices until the chosen time, even while the person is awake (writing)
        import datetime as dt
        from zoneinfo import ZoneInfo

        p.FOCO, p.SILENCIO = tmp / "foco.json", tmp / "silencio.json"
        p.SILENCIO.write_text(json.dumps({"matheus": {"desligado": True}}))
        fuso = ZoneInfo("America/Bahia")
        base = dt.datetime(2026, 10, 13, 10, 0, tzinfo=fuso).timestamp()
        r = p.comando_foco("matheus", "/foco até 15h", agora=base)
        ate = p._foco_ate("matheus")
        ok(dt.datetime.fromtimestamp(ate, fuso).strftime("%d %H:%M") == "13 15:00" and "15:00" in r, f"foco até as 15h: {r}")
        p.ULTIMA_ENTRADA["matheus"] = __import__("time").time()  # awake, writing
        ok(p.em_silencio("matheus") == (__import__("time").time() < ate), "em foco, segura mesmo acordado")
        r = p.comando_foco("matheus", "/foco 9:30", agora=base)
        ok(dt.datetime.fromtimestamp(p._foco_ate("matheus"), fuso).strftime("%d %H:%M") == "14 09:30", f"hora que já passou = amanhã: {r}")
        p.comando_foco("matheus", "/foco 45min", agora=base)
        ok(abs(p._foco_ate("matheus") - (base + 45 * 60)) < 1, "duração em minutos")
        ok("Sem foco" in p.comando_foco("matheus", "/foco off", agora=base), "/foco off encerra")
        ok(not p.em_silencio("matheus"), "sem foco e com silêncio desligado, nada é segurado")
        ok("Use /foco" in p.comando_foco("matheus", "/foco amanhã cedo", agora=base), "o que não entende, explica")
        ok(p.comando_foco("matheus", "oi") is None, "mensagem comum não é comando")

        # daily ceiling of progress notices (12/10 review §4.3 item 6), grouped at 12:30 / 18:30 / next morning
        p.CONTAGEM = tmp / "avisos_dia.json"
        dez = dt.datetime(2026, 10, 13, 10, 0, tzinfo=fuso).timestamp()
        quando = lambda ts: dt.datetime.fromtimestamp(ts, fuso).strftime("%d %H:%M")  # noqa: E731
        ok(quando(p.proximo_agrupado(dez)) == "13 12:30" and quando(p.proximo_agrupado(dez + 3 * 3600)) == "13 18:30"
           and quando(p.proximo_agrupado(dez + 9 * 3600)) == "14 07:00", "próximos horários de agrupar")
        saidas = [p.passou_do_teto("matheus", dez + i) for i in range(p.TETO_DIA + 2)]
        ok(saidas == [False] * p.TETO_DIA + [True, True], f"os {p.TETO_DIA} primeiros saem; o resto agrupa: {saidas}")
        ok(quando(p._teto_ate("matheus")) == "13 12:30", "agrupado até as 12h30")
        ok(not p.passou_do_teto("matheus", dez + 86400), "no dia seguinte a contagem recomeça")

        # held notices: buttons are kept and delivered one by one; plain ones grouped
        p.FILA = tmp / "fila"
        enviados = []
        p.avisar = lambda u, texto: enviados.append(("grupo", texto))
        p.avisar_com_botoes = lambda u, texto, botoes: enviados.append(("botoes", texto, botoes))
        p.guardar_para_depois("matheus", "Resumo do Radar: 2 e-mails")
        p.guardar_para_depois("matheus", "🧵 Fio: cobrar o contador", [{"id": "fio:matheus:f1:fazer", "titulo": "✅ Faz pra mim"}])
        p.guardar_para_depois("matheus", "Prospecção: 3 aquecidos")
        n = p.descarregar(p.FILA / "matheus.jsonl")
        ok(n == 3 and [e[0] for e in enviados] == ["botoes", "grupo"], f"um com botões + um agrupado: {enviados}")
        ok(enviados[0][2][0]["id"] == "fio:matheus:f1:fazer", "o botão continua o mesmo")
        ok("Resumo do Radar" in enviados[1][1] and "3 aquecidos" in enviados[1][1], "os sem botão vão juntos")
        ok(not (p.FILA / "matheus.jsonl").exists(), "a fila esvazia")

        # 12/10 review §6: one message in the morning — the night's notices wait for the summary and go inside it
        p.RESUMO_MANHA = tmp / "resumo_manha.json"
        p.SILENCIO.write_text(json.dumps({"matheus": {"inicio": "23:00", "fim": "07:00"}}))
        p.ULTIMA_ENTRADA["matheus"] = 0
        sete_e_vinte = dt.datetime(2026, 10, 13, 7, 20, tzinfo=fuso).timestamp()
        p.AGENDADAS = tmp / "tasks.json"
        ok(not p.esperando_resumo("matheus", sete_e_vinte), "quem nunca recebeu resumo não espera")
        p.AGENDADAS.write_text(json.dumps({"tasks": [{"name": "📰 Resumo do dia", "state": "idle"}]}))
        ok(p.esperando_resumo("matheus", sete_e_vinte), "o dono com a rotina 📰 ligada espera já no primeiro dia")
        ok(not p.esperando_resumo("outra", sete_e_vinte), "a rotina do dono não vale para outra pessoa")
        p.AGENDADAS.write_text(json.dumps({"tasks": [{"name": "📰 Resumo do dia", "state": "disabled"}]}))
        ok(not p.esperando_resumo("matheus", sete_e_vinte), "rotina desligada: não espera")
        p.RESUMO_MANHA.write_text(json.dumps({"matheus": "2026-10-12"}))
        ok(p.esperando_resumo("matheus", sete_e_vinte), "7h20: a noite espera o resumo")
        ok(not p.esperando_resumo("matheus", sete_e_vinte + 75 * 60), "8h35: passou do limite, sai sozinho")
        ok(not p.esperando_resumo("matheus", sete_e_vinte - 30 * 60), "6h50: ainda é silêncio (outra regra)")
        p.ULTIMA_ENTRADA["matheus"] = sete_e_vinte - 60
        ok(not p.esperando_resumo("matheus", sete_e_vinte), "escrevendo agora: não segura")
        p.ULTIMA_ENTRADA["matheus"] = 0
        p.RESUMO_MANHA.write_text(json.dumps({"matheus": "2026-10-05"}))
        ok(not p.esperando_resumo("matheus", sete_e_vinte), "sem resumo há mais de 3 dias: não espera")
        p.RESUMO_MANHA.write_text(json.dumps({"matheus": "2026-10-12"}))

        enviados.clear()
        p.guardar_para_depois("matheus", "Radar: 2 e-mails novos do contador")
        p.guardar_para_depois("matheus", "🧵 Fio: cobrar a Carla", [{"id": "fio:matheus:f2:fazer", "titulo": "✅ Faz pra mim"}])
        p.guardar_para_depois("matheus", "Prospecção: 4 perfis aquecidos")
        # the whole path: the summary arrives at /enviar marked as the 📰 routine
        p.chave = lambda: "k"
        p.cfg = lambda: {"tg_chats": {"42": "matheus"}, "numeros": {}}
        p.ativo = lambda: None
        p.em_silencio = lambda u: False
        p.passou_do_teto = lambda u, agora=None: False
        ditos.clear()
        servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), p.Saida)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        try:
            corpo = {"usuario": "matheus", "texto": "*📰 Resumo do dia*\n\n*Bom dia!* Reunião às 15h.", "tipo": "progresso",
                     "rotina": "📰 Resumo do dia"}
            req = urllib.request.Request(f"http://127.0.0.1:{servidor.server_address[1]}/enviar", data=json.dumps(corpo).encode(),
                                         headers={"Content-Type": "application/json", "X-Chave": "k"})
            with urllib.request.urlopen(req, timeout=10) as r:
                ok(json.loads(r.read()).get("ok"), "resumo entregue")
        finally:
            servidor.shutdown()
        ok(len(ditos) == 1, f"uma mensagem de texto só: {ditos}")
        texto = ditos[0][1] if ditos else ""
        ok(texto.startswith("*📰 Resumo do dia*") and "🌙 *Da noite*" in texto and "contador" in texto
           and "4 perfis aquecidos" in texto and "cobrar a Carla" not in texto, f"a noite dentro do resumo: {texto!r}")
        ok([e[0] for e in enviados] == ["botoes"] and enviados[0][2][0]["id"] == "fio:matheus:f2:fazer",
           f"o que tem botão vem depois, com o botão: {enviados}")
        ok(not (p.FILA / "matheus.jsonl").exists(), "a fila da noite esvaziou")
        ok(json.loads(p.RESUMO_MANHA.read_text())["matheus"] == dt.datetime.now(fuso).date().isoformat(), "resumo de hoje marcado")
        ok(not p.esperando_resumo("matheus"), "depois do resumo, nada mais espera")

        # what arrives between reading the night and sending the summary stays in the queue
        p.guardar_para_depois("matheus", "A")
        texto, itens = p.resumo_com_a_noite("matheus", "Resumo")
        p.guardar_para_depois("matheus", "B (chegou durante o envio)")
        p.tirar_da_fila("matheus", itens)
        restam = [json.loads(l)["texto"] for l in (p.FILA / "matheus.jsonl").read_text().splitlines()]
        ok(restam == ["B (chegou durante o envio)"], f"só sai o que foi junto: {restam}")
        ok(p.resumo_com_a_noite("ninguem", "Resumo") == ("Resumo", []), "sem fila, o resumo vai como está")

        # 12/10 review §6: requests in parallel — one progress message per person, edited in place on Telegram
        chamadas = []

        def tg_falso(metodo, dados=None, arquivo=None):
            chamadas.append((metodo, dict(dados or {})))
            if metodo == "editMessageText" and dados.get("message_id") == 999:
                raise RuntimeError("Bad Request: message to edit not found")
            return {"ok": True, "result": {"message_id": 500 + len(chamadas)}}

        p.tg = tg_falso
        p.tg_chat = lambda u: "42" if u == "matheus" else ""
        p.ANDAMENTO.clear()
        t0 = 10_000.0
        ok(p.andamento("matheus", "⏳ 1 pedido (2 min)", agora=t0) == "enviada", "a primeira vai como mensagem nova")
        mid = chamadas[-1][0] == "sendMessage" and p.ANDAMENTO["matheus"]["id"]
        ok(p.andamento("matheus", "⏳ 2 pedidos (4 min)", agora=t0 + 120) == "editada"
           and chamadas[-1] == ("editMessageText", {"chat_id": "42", "message_id": mid, "text": "⏳ 2 pedidos (4 min)",
                                                    "disable_web_page_preview": True}), f"as seguintes editam a mesma: {chamadas[-1]}")
        n = len(chamadas)
        ok(p.andamento("matheus", "⏳ 2 pedidos (4 min)", agora=t0 + 130) == "editada" and len(chamadas) == n,
           "texto igual: nem chama o Telegram")
        ok(p.andamento("matheus", "✅ Terminei", fim=True, agora=t0 + 300) == "fechada" and chamadas[-1][0] == "editMessageText",
           "no fim, edita para pronto e fecha")
        ok(p.andamento("matheus", "⏳ outro pedido", agora=t0 + 400) == "enviada", "depois de fechada, o próximo pedido abre outra")
        p.ANDAMENTO["matheus"]["id"] = 999  # the person deleted it
        ok(p.andamento("matheus", "⏳ outro pedido (3 min)", agora=t0 + 500) == "enviada" and chamadas[-1][0] == "sendMessage",
           "não deu para editar: manda uma nova")
        ok(p.andamento("matheus", "⏳ velha", agora=t0 + 500 + p.ANDAMENTO_VIDA + 1) == "enviada", "mensagem velha: uma nova")
        p.ANDAMENTO.clear()
        ok(p.andamento("matheus", "✅ Terminei", fim=True, agora=t0) == "nada" and chamadas[-1][1].get("text") != "✅ Terminei",
           "sem mensagem aberta, o fim não manda nada")
        # WhatsApp (cannot edit): the combined line at most every 4 min
        whats = []
        p.enviar_texto = lambda numero, texto: whats.append(texto)
        p.cfg = lambda: {"tg_chats": {}, "numeros": {"5571": "fernanda"}}
        ok(p.andamento("fernanda", "⏳ a", agora=t0) == "enviada" and p.andamento("fernanda", "⏳ b", agora=t0 + 60) == "nada"
           and p.andamento("fernanda", "⏳ c", agora=t0 + p.ANDAMENTO_WA) == "enviada" and whats == ["⏳ a", "⏳ c"],
           f"WhatsApp: no máximo 1 a cada 4 min: {whats}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("fila:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
