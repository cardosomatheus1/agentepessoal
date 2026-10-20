"""The model proxy: /health answers locally; a call refused for a moment (connection refused, 429, 5xx) is tried once
more, anything else passes straight through. Fake upstream and token, local port only. Run from the repository root:
python3 infra/vm/tests/test_proxy.py"""

import http.server
import importlib.util
import json
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


class RespostaFalsa:
    def __init__(self, status, corpo=b"", cabecalhos=None):
        self.status, self._corpo, self._cab = status, corpo, cabecalhos or {}
        self._lido = False

    def getheader(self, nome, padrao=None):
        return self._cab.get(nome, padrao)

    def getheaders(self):
        return [("Content-Type", "application/json"), *self._cab.items()]

    def read(self, n=-1):
        corpo, self._corpo = self._corpo, b""
        return corpo

    def read1(self, n=-1):
        return self.read()


def main() -> int:
    estado = {"token_ok": True}
    gerador = types.ModuleType("aws_bedrock_token_generator")

    def provide_token(region, expiry):
        if not estado["token_ok"]:
            raise RuntimeError("sem credencial")
        return "tok"

    gerador.provide_token = provide_token
    sys.modules["aws_bedrock_token_generator"] = gerador
    spec = importlib.util.spec_from_file_location("proxy_teste", RAIZ / "infra" / "vm" / "bedrock_proxy.py")
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    p.ESPERA_MAX = p.ESPERA_CONEXAO = 0
    log_usage_real = p.log_usage
    p.mark_activity = p.log_usage = lambda *a, **k: None
    roteiro, pedidos, cabecalhos, corpos = [], [], [], []

    class ConexaoFalsa:
        def __init__(self, host, timeout=0, context=None):
            self.host = host

        def request(self, metodo, path, body=None, headers=None):
            cabecalhos.append({k.lower() for k in headers})
            corpos.append(body)
            pedidos.append((self.host, path, headers.get("Authorization")))
            self._proximo = roteiro.pop(0)
            if isinstance(self._proximo, Exception):
                raise self._proximo

        def getresponse(self):
            return self._proximo

        def close(self):
            pass

    p._conexao = ConexaoFalsa
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), p.Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    def chamar(caminho="/openai/v1/chat/completions"):
        req = urllib.request.Request(base + caminho, data=b'{"model": "luna"}' if caminho != "/health" else None,
                                     method="POST" if caminho != "/health" else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        roteiro[:] = [RespostaFalsa(503), RespostaFalsa(200, b'{"ok": 1}')]
        pedidos.clear()
        ok(chamar() == (200, b'{"ok": 1}') and len(pedidos) == 2, f"503 passageiro: tenta de novo e entrega ({pedidos})")
        ok(pedidos[0][2] == "Bearer tok", "leva a chave gerada aqui")
        roteiro[:] = [RespostaFalsa(429, cabecalhos={"Retry-After": "1"}), RespostaFalsa(429, b'{"erro": "limite"}')]
        pedidos.clear()
        ok(chamar()[0] == 429 and len(pedidos) == 2, "429 de novo: só uma nova tentativa, e o agente vê o 429")
        roteiro[:] = [ConnectionRefusedError("recusada"), RespostaFalsa(200, b"{}")]
        pedidos.clear()
        ok(chamar()[0] == 200 and len(pedidos) == 2, "conexão recusada por um instante: tenta de novo")
        roteiro[:] = [ConnectionRefusedError("recusada"), ConnectionRefusedError("recusada")]
        status, corpo = chamar()
        ok(status == 502 and b"unreachable" in corpo, f"fora do ar: 502 claro ({status} {corpo[:60]})")
        roteiro[:] = [RespostaFalsa(400, b'{"erro": "pedido ruim"}')]
        pedidos.clear()
        ok(chamar()[0] == 400 and len(pedidos) == 1, "erro do pedido (400) passa direto, sem repetir")
        pedidos.clear()
        status, corpo = chamar("/health")
        ok(status == 200 and json.loads(corpo)["token"] and not pedidos, "saúde responde aqui, sem chamar a AWS")
        estado["token_ok"] = False
        p._token.update(value="", at=0.0)
        ok(chamar("/health")[0] == 503, "sem conseguir a chave, a saúde diz que não está bem")
        # links for post files (13/10: the agent container has no AWS credentials)
        class S3Falso:
            def head_object(self, Bucket, Key):
                if "falta" in Key:
                    raise RuntimeError("404")

            def generate_presigned_url(self, op, Params, ExpiresIn):
                return f"https://s3/{Params['Bucket']}/{Params['Key']}?{op}&{ExpiresIn}"
        p.BUCKET, p._s3["client"] = "balde", S3Falso()
        r = p.link_conteudo("conteudo/semana1/pov.mp4")
        ok(r.get("url") == "https://s3/balde/conteudo/semana1/pov.mp4?get_object&3600", f"link de 1 h para ler ({r})")
        for ruim in ("entrada/chats/x/y.mp4", "conteudo/../segredo", "conteudo/", ""):
            ok("error" in p.link_conteudo(ruim), f"fora de conteudo/ é recusado: {ruim!r}")
        ok("não encontrado" in p.link_conteudo("conteudo/falta.mp4").get("error", ""), "arquivo que não existe")
        # 20/10: the week of posts uploads its arts through a 1-hour PUT link, only under conteudo/semanas/
        r = p.subir_conteudo("conteudo/semanas/2026-10-21/p1/arte.jpg")
        ok(r.get("url") == "https://s3/balde/conteudo/semanas/2026-10-21/p1/arte.jpg?put_object&3600", f"link de envio ({r})")
        for ruim in ("conteudo/semana1/pov.mp4", "conteudo/semanas/../x", "conteudo/semanas/", "conteudo/semanas/a b.jpg", ""):
            ok("error" in p.subir_conteudo(ruim), f"envio fora de conteudo/semanas/ é recusado: {ruim!r}")
        req = urllib.request.Request(f"{base}/arquivos/conteudo_subir", data=b'{"chave": "conteudo/semanas/s/p/a.jpg"}',
                                     method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            ok(json.loads(r.read())["url"].endswith("a.jpg?put_object&3600"), "rota /arquivos/conteudo_subir")
        req = urllib.request.Request(f"{base}/arquivos/conteudo", data=b'{"chave": "conteudo/a.mp4"}', method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            ok(json.loads(r.read())["url"].endswith("conteudo/a.mp4?get_object&3600"), "rota /arquivos/conteudo")
        # 15/10: voice answers in the person's language
        class PollyFalsa:
            def __init__(self):
                self.pedidos = []

            def synthesize_speech(self, **kw):
                self.pedidos.append(kw)
                if kw["Engine"] == "generative" and kw["VoiceId"] == "Danielle":
                    raise RuntimeError("sem generativa")
                import io
                return {"AudioStream": io.BytesIO(b"mp3")}
        pf = PollyFalsa()
        p._aws["polly"] = pf
        p.time = types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time,
                                       strftime=__import__("time").strftime, gmtime=__import__("time").gmtime)
        r = p.voz("Привет", "ru")
        ok(r.get("voz") == "Tatyana" and pf.pedidos[-1]["LanguageCode"] == "ru-RU", f"russo com voz russa ({r})")
        r = p.voz("Oi", "pt")
        ok(r.get("voz") == "Camila" and r.get("motor") == "generative", f"português segue com a Camila ({r})")
        r = p.voz("Hi", "en")
        ok(r.get("motor") == "neural" and r.get("voz") == "Danielle", f"sem a generativa, a neural da mesma voz ({r})")
        ok("sem voz" in p.voz("x", "zz").get("error", ""), "língua sem voz: erro claro (o texto ainda vai)")
        p.time = __import__("time")
        # 15/10 guests: whose chat made the call goes in the usage log, never to Bedrock
        estado["token_ok"] = True
        pedidos.clear(); cabecalhos.clear(); roteiro[:] = [RespostaFalsa(200, b'{"ok": 1}')]
        req = urllib.request.Request(f"{base}/openai/v1/chat/completions", data=b"{}", method="POST",
                                     headers={"X-A0-Dono": "ilia"})
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()
        ok(cabecalhos and "x-a0-dono" not in cabecalhos[0], f"X-A0-Dono não sobe para a AWS ({cabecalhos})")
        import tempfile
        p.USAGE_FILE = Path(tempfile.mkdtemp(prefix="uso-")) / "uso.jsonl"
        uso = b'data: {"usage": {"prompt_tokens": 10, "completion_tokens": 2}}'
        log_usage_real("/v1/chat/completions", b'{"model": "m"}', 200, uso, 1.0, "ilia")
        log_usage_real("/v1/chat/completions", b'{"model": "m"}', 200, uso, 1.0, "../x")
        log_usage_real("/v1/chat/completions", b'{"model": "m"}', 200, uso, 1.0)
        linhas = [json.loads(x) for x in p.USAGE_FILE.read_text().splitlines()]
        ok([x.get("dono") for x in linhas] == ["ilia", None, None], f"dono no uso, só login válido ({linhas})")
        # Converse (Claude): inputTokens leaves out the cached part; entrada keeps the whole prompt
        conv = b'{"metadata": {"usage": {"inputTokens": 100, "cacheReadInputTokens": 5000, "cacheWriteInputTokens": 300, "outputTokens": 20}}}'
        log_usage_real("/model/us.anthropic.claude-sonnet-5-5/converse", b"{}", 200, conv, 1.0, "matheus")
        u = json.loads(p.USAGE_FILE.read_text().splitlines()[-1])
        ok((u["modelo"], u["entrada"], u["cache"], u["cache_gravado"], u["saida"]) ==
           ("us.anthropic.claude-sonnet-5-5", 5400, 5000, 300, 20), f"uso do Converse com cache: {u}")
        # cache points: end of system and of the last message, only for Claude on Converse, never twice
        pedido = {"system": [{"text": "regras"}], "messages": [{"role": "user", "content": [{"text": "oi"}]},
                  {"role": "assistant", "content": [{"text": "olá"}]}, {"role": "user", "content": [{"text": "e aí"}]}]}
        cru = json.dumps(pedido).encode()
        novo = json.loads(p.com_cache("/model/us.anthropic.claude-sonnet-5-5/converse-stream", cru))
        ok(novo["system"][-1] == {"cachePoint": {"type": "default"}} and
           novo["messages"][-1]["content"][-1] == {"cachePoint": {"type": "default"}} and
           novo["messages"][0]["content"] == [{"text": "oi"}], f"pontos de cache no Claude: {novo}")
        ok(str(novo).count("cachePoint") == 2, "dois pontos (sistema e última mensagem)")
        de_novo = p.com_cache("/model/us.anthropic.claude-sonnet-5-5/converse", json.dumps(novo).encode())
        ok(str(json.loads(de_novo)).count("cachePoint") == 2, "pedido que já tem ponto de cache passa igual")
        ok(p.com_cache("/model/amazon.nova-pro-v1:0/converse", cru) == cru, "modelo que não é Claude passa igual")
        ok(p.com_cache("/v1/chat/completions", cru) == cru, "OpenAI (Luna/Sol) passa igual")
        ok(p.com_cache("/model/us.anthropic.claude-sonnet-5-5/converse", b"nao e json") == b"nao e json", "corpo torto passa igual")
        # 20/10: a person's chat gets the 1-hour cache on both points; routines, helpers and the utility model keep 5 min
        longo = json.loads(p.com_cache("/model/us.anthropic.claude-sonnet-5-5/converse", cru, True))
        ok(longo["system"][-1] == {"cachePoint": {"type": "default", "ttl": "1h"}} and
           longo["messages"][-1]["content"][-1] == {"cachePoint": {"type": "default", "ttl": "1h"}}, f"1 h na conversa: {longo}")
        humano = {"conversa": "abc", "agente": 0, "papel": "chat"}
        ok(p.conversa_humana(humano), "conversa, agente principal, modelo de chat: 1 h")
        for outro in ({**humano, "rotina": "HL76nfIg"}, {**humano, "agente": 1}, {**humano, "papel": "util"}, {}, None,
                      {"agente": 0, "papel": "chat"}):
            ok(not p.conversa_humana(outro), f"rotina, ajudante, utilitário ou origem desconhecida: 5 min ({outro})")
        # 20/10: which chat/routine/agent made the call (X-A0-* headers), only well-formed values
        ok(p.rastreio_de({"X-A0-Conversa": "Ab_1-x", "X-A0-Rotina": "HL76nfIg", "X-A0-Agente": "2", "X-A0-Papel": "Util"})
           == {"conversa": "Ab_1-x", "rotina": "HL76nfIg", "agente": 2, "papel": "util"}, "cabeçalhos de rastreio lidos")
        ok(p.rastreio_de({"X-A0-Conversa": "a b", "X-A0-Rotina": "../x", "X-A0-Agente": "-1", "X-A0-Papel": "outro"}) == {},
           "valores tortos são ignorados")
        # 20/10: GPT (Responses and Chat): stable cache key per routine/chat + 24 h retention, unless the call brings its own
        rot = {"conversa": "ctx1", "rotina": "HL76nfIg", "agente": 0, "papel": "chat"}
        ok(p.chave_cache(rot) == "a0-r-HL76nfIg-a0", "rotina: a chave é da rotina (todas as rodadas leem a parte fixa)")
        ok(p.chave_cache({"conversa": "ctx1", "agente": 1, "papel": "util"}) == "a0-c-ctx1-a1-u", "conversa, ajudante, utilitário")
        ok(p.chave_cache({"agente": 0}) == "" and p.chave_cache(None) == "", "sem conversa nem rotina: sem chave")
        gpt = json.dumps({"model": "openai.gpt-6-luna", "instructions": "x", "input": "oi"}).encode()
        for rota in ("/openai/v1/responses", "/openai/v1/chat/completions"):
            d = json.loads(p.com_chave(rota, gpt, rot))
            ok(d["prompt_cache_key"] == "a0-r-HL76nfIg-a0" and d["prompt_cache_retention"] == "24h" and d["input"] == "oi",
               f"{rota}: chave e 24 h ({d})")
        proprio = json.dumps({"model": "m", "prompt_cache_key": "dele", "prompt_cache_retention": "in_memory"}).encode()
        ok(p.com_chave("/openai/v1/responses", proprio, rot) == proprio, "pedido com os campos próprios passa igual")
        so_chave = json.loads(p.com_chave("/openai/v1/responses", json.dumps({"prompt_cache_key": "dele"}).encode(), rot))
        ok(so_chave == {"prompt_cache_key": "dele", "prompt_cache_retention": "24h"}, f"só falta a retenção: {so_chave}")
        ok(p.com_chave("/openai/v1/responses", gpt, {}) == gpt, "origem desconhecida: nada muda")
        ok(p.com_chave("/model/us.anthropic.claude-sonnet-5-5/converse", gpt, rot) == gpt, "Claude não recebe esses campos")
        ok(p.com_chave("/openai/v1/embeddings", gpt, rot) == gpt, "outras rotas passam iguais")
        ok(p.com_chave("/openai/v1/responses", b"[1]", rot) == b"[1]" and p.com_chave("/openai/v1/responses", b"x{", rot) == b"x{",
           "corpo que não é objeto passa igual")
        # through the handler: the key reaches Bedrock, the X-A0-* headers do not
        cabecalhos.clear(); corpos.clear(); roteiro[:] = [RespostaFalsa(200, b'{"ok": 1}')]
        req = urllib.request.Request(f"{base}/openai/v1/responses", data=gpt, method="POST", headers={
            "X-A0-Dono": "matheus", "X-A0-Conversa": "ctx1", "X-A0-Rotina": "HL76nfIg", "X-A0-Agente": "0", "X-A0-Papel": "chat"})
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()
        ok(not {"x-a0-conversa", "x-a0-rotina", "x-a0-agente", "x-a0-papel"} & cabecalhos[0], f"rastreio não sobe ({cabecalhos})")
        ok(json.loads(corpos[0])["prompt_cache_key"] == "a0-r-HL76nfIg-a0", f"chave chega à AWS ({corpos[0][:200]})")
        cabecalhos.clear(); corpos.clear(); roteiro[:] = [RespostaFalsa(200, b'{"ok": 1}')]
        req = urllib.request.Request(f"{base}/bedrock/model/us.anthropic.claude-sonnet-5-5/converse", data=cru, method="POST",
                                     headers={"X-A0-Conversa": "ctx1", "X-A0-Agente": "0", "X-A0-Papel": "chat"})
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()
        ok('"ttl": "1h"' in corpos[0].decode(), f"conversa do Matheus no Claude vai com 1 h ({corpos[0][-120:]})")
        # 20/10: the usage line says who made the call and fingerprints the start of the prompt — never its text
        segredo = "CPF 123.456.789-00 do Matheus"
        conv_pedido = {"system": [{"text": "regras " * 500}, {"cachePoint": {"type": "default"}}],
                       "toolConfig": {"tools": [{"toolSpec": {"name": "a"}}, {"toolSpec": {"name": "b"}}]},
                       "messages": [{"role": "user", "content": [{"text": segredo}]},
                                    {"role": "assistant", "content": [{"text": "ok"}]}]}
        conv_uso = (b'{"metadata": {"usage": {"inputTokens": 10, "cacheReadInputTokens": 0, "cacheWriteInputTokens": 900,'
                    b' "cacheDetails": [{"inputTokens": 700, "ttl": "1h"}, {"inputTokens": 200, "ttl": "5m"}], "outputTokens": 5}}}')
        rota_c = "/model/us.anthropic.claude-sonnet-5-5/converse-stream"
        log_usage_real(rota_c, json.dumps(conv_pedido).encode(), 200, conv_uso, 1.0, "matheus",
                       {"conversa": "ctx1", "agente": 0, "papel": "chat"})
        bruto = p.USAGE_FILE.read_text().splitlines()[-1]
        u = json.loads(bruto)
        ok(segredo not in bruto and "regras" not in bruto and '"a"' not in bruto, f"nenhum texto do pedido no uso: {bruto}")
        ok((u["conversa"], u["agente"], u["papel"], u["api"], u["cache_gravado"], u["cache_gravado_1h"], u["mensagens"]) ==
           ("ctx1", 0, "chat", "converse", 900, 700, 2), f"rastreio e gravação de 1 h no uso: {u}")
        ok(set(u["instrucoes"]) == {"n", "ini", "todo"} and len(u["instrucoes"]["ini"]) == 10 and u["instrucoes"]["n"] > 2000
           and u["instrucoes"]["ini"] != u["instrucoes"]["todo"], f"impressão das instruções: tamanho e 2 hashes ({u['instrucoes']})")
        sem_ponto = json.loads(json.dumps(conv_pedido))
        sem_ponto["system"].pop()
        ok(p.impressao(sem_ponto, True) == p.impressao(conv_pedido, True), "o ponto de cache não muda a impressão")
        outra = json.loads(json.dumps(conv_pedido))
        outra["toolConfig"]["tools"].reverse()
        a, b = p.impressao(conv_pedido, True), p.impressao(outra, True)
        ok(a["ferramentas"] != b["ferramentas"] and a["instrucoes"] == b["instrucoes"] and a["primeira"] == b["primeira"],
           "ferramentas em outra ordem: só a parte das ferramentas muda")
        resp = {"model": "openai.gpt-6-luna", "instructions": "fixo", "tools": [{"name": "t"}], "prompt_cache_key": "a0-c-x-a0",
                "prompt_cache_retention": "24h",
                "input": [{"role": "developer", "content": "dev"}, {"role": "user", "content": segredo}, {"role": "user", "content": "b"}]}
        i = p.impressao(resp)
        ok(i["mensagens"] == 2 and i["instrucoes"] == p._digital(["fixo", {"role": "developer", "content": "dev"}]) and
           i["primeira"] == p._digital({"role": "user", "content": segredo}), f"Responses: instruções + developer, 1ª fala: {i}")
        chat = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}
        ok(p.impressao(chat)["instrucoes"] == p._digital([{"role": "system", "content": "s"}]) and p.impressao(chat)["mensagens"] == 1,
           "Chat Completions: mensagens de sistema iniciais são as instruções")
        log_usage_real("/openai/v1/responses", json.dumps(resp).encode(), 200, b'{"usage": {"input_tokens": 9}}', 1.0, "", rot)
        u = json.loads(p.USAGE_FILE.read_text().splitlines()[-1])
        ok((u["rotina"], u["api"], u["cache_key"], u["cache_retention"]) == ("HL76nfIg", "responses", "a0-c-x-a0", "24h")
           and "cache_gravado_1h" not in u and segredo not in json.dumps(u), f"linha do GPT: {u}")
    finally:
        servidor.shutdown()
    for f in falhas:
        print("FALHA", f)
    print("proxy:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
