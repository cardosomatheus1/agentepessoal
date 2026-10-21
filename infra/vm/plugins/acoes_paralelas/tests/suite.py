"""Tests of acoes_paralelas without Agent Zero (its names are stubbed). Run with implantar.py (staging copy) or from the
repository root: python3 infra/operador/rodar_suites_locais.py acoes_paralelas"""

import asyncio
import importlib.util
import os
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _modulo(nome, arquivo, stubs=None):
    stubs = stubs or {}
    antes = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(nome, arquivo)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class Intervencao(Exception):
    pass


class Response:
    def __init__(self, message, break_loop=False, additional=None):
        self.message, self.break_loop, self.additional = message, break_loop, additional


class Ferramenta:
    """A tool that takes `espera` seconds (asyncio.sleep, like a remote read) and records each step."""

    def __init__(self, nome, diario, espera=0.2, erro=None, fim=False):
        self.nome, self.diario, self.espera, self.erro, self.fim = nome, diario, espera, erro, fim

    async def before_execution(self, **a):
        self.diario.append(("antes", self.nome))

    async def execute(self, **a):
        self.diario.append(("comeca", self.nome))
        await asyncio.sleep(self.espera)
        if self.erro:
            raise self.erro
        self.diario.append(("termina", self.nome))
        return Response(f"resultado {self.nome} {a}", self.fim)

    async def after_execution(self, r):
        self.diario.append(("historico", self.nome, r.message))


class Agente:
    DATA_NAME_RESPONSES_TOOL_NAME_MAP = "mapa"

    def __init__(self, ferramentas, diario):
        self.ferramentas, self.diario = ferramentas, diario
        self.loop_data = types.SimpleNamespace(current_tool=None)
        self.dados = {"mapa": {"google_get_events_82f4960e": "google.get_events"}}

    def get_data(self, k):
        return self.dados.get(k)

    def get_tool(self, name, method, args, message, loop_data):
        return self.ferramentas[name]

    async def handle_intervention(self):
        pass

    async def _log_response_builtin_items(self, r):
        pass

    def _clear_responses_pending_state(self):
        self.diario.append(("limpou",))

    async def _execute_tool_request(self, tool_name, tool_args, message, raw_tool_name, responses_item_factory):
        """Agent Zero's one-call path (here: runs the tool alone and records it as such)."""
        f = self.ferramentas[tool_name]
        self.diario.append(("sozinha", tool_name))
        r = await f.execute(**tool_args)
        await f.after_execution(r)
        return r.message if r.break_loop else None


def _chamada(nome, args, cid):
    return types.SimpleNamespace(name=nome, arguments=args, call_id=cid)


class Suite:
    def __init__(self):
        self.resultados = []
        self.plano = _modulo("acoes_paralelas_plano_teste", RAIZ / "helpers" / "plano.py")

    def _executar(self, extensoes):
        e = _modulo("acoes_paralelas_executar_teste", RAIZ / "helpers" / "executar.py")

        async def call_extensions_async(ponto, agente, **kw):
            extensoes.append((ponto, kw.get("tool_name")))

        e._a0 = types.SimpleNamespace(
            call_extensions_async=call_extensions_async,
            function_call_output_item=lambda cid, msg: {"call_id": cid, "output": msg},
            original_tool_name=lambda n, mapa: (mapa or {}).get(n, n), Response=Response,
            parar=(Intervencao, asyncio.CancelledError))
        e.plano = lambda: self.plano
        e.DESLIGADO = Path(tempfile.gettempdir()) / f"acoes_paralelas_desligado_{os.getpid()}"
        return e

    # ---- the planner (Hermes's segments) -----------------------------------------------------------------------
    def t_plano_leituras_juntas_e_barreiras_em_fila(self):
        p = self.plano
        chamadas = [("search_engine", {"query": "a"}), ("document_query", {"document": "x"}),
                    ("browser", {"action": "open"}), ("memory_load", {"query": "b"}), ("lembrar", {"busca": "c"})]
        eq(p.planejar(chamadas), [("paralelo", [0, 1]), ("fila", [2]), ("paralelo", [3, 4])],
           "o navegador é barreira: separa os dois grupos e roda sozinho, na ordem")
        eq(p.planejar([("response", {"text": "x"}), ("search_engine", {})]), [("fila", [0]), ("fila", [1])],
           "a resposta final nunca entra em grupo")
        eq(p.planejar([("ferramenta_nova", {}), ("search_engine", {})]), [("fila", [0]), ("fila", [1])],
           "ferramenta desconhecida é barreira (como no Hermes)")
        for nome, args in [("code_execution_tool", {"runtime": "terminal"}), ("celular", {}), ("whatsapp_enviar", {}),
                           ("call_subordinate", {}), ("prospeccao", {"acao": "buscar"}), ("cerebro", {"acao": "reuniao"}),
                           ("decisao", {"acao": "registrar"}),
                           ("ferramentas_extras", {"acao": "usar", "nome": "google_create_event_1a2b3c4d"}),
                           ("ferramentas_extras", {"acao": "usar", "nome": "google_send_gmail_message_1a2b3c4d"})]:
            eq(p.admissao(nome, args), None, f"{nome} {args} roda sozinha")
        for nome, args in [("ferramentas_extras", {"acao": "usar", "nome": "google_get_events_82f4960e"}),
                           ("ferramentas_extras", {"acao": "usar", "nome": "github_search_code_4ff82997"}),
                           ("ferramentas_extras", {"acao": "buscar", "texto": "agenda"}),
                           ("skills_tool", {"action": "load"}), ("cerebro", {"acao": "consultar"}),
                           ("decisao", {"acao": "listar", "busca": "ifood"})]:
            ok(p.admissao(nome, args) is not None, f"{nome} {args} pode ir junto (só lê)")

    def t_plano_arquivos_pelo_caminho(self):
        p = self.plano
        ler = lambda c: ("text_editor", {"action": "read", "path": c})  # noqa: E731
        escrever = lambda c: ("text_editor", {"action": "write", "path": c})  # noqa: E731
        eq(p.planejar([ler("a.txt"), ler("a.txt"), ler("b.txt")]), [("paralelo", [0, 1, 2])], "leituras juntas")
        eq(p.planejar([escrever("a.txt"), escrever("b.txt")]), [("paralelo", [0, 1])], "escritas em arquivos diferentes")
        eq(p.planejar([ler("a.txt"), escrever("a.txt")]), [("fila", [0]), ("fila", [1])],
           "escrever o que outro lê: a leitura vem antes, sozinha (nunca lê pela metade)")
        eq(p.planejar([escrever("dir/x.txt"), ler("dir")]), [("fila", [0]), ("fila", [1])], "pasta e arquivo dentro dela")
        eq(p.planejar([("text_editor", {"action": "read"}), ler("b")]), [("fila", [0]), ("fila", [1])],
           "sem caminho: barreira")

    # ---- the runner ---------------------------------------------------------------------------------------------
    async def _rodar(self, chamadas, ferramentas, extensoes=None):
        diario = []
        fs = {n: Ferramenta(n, diario, **kw) for n, kw in ferramentas.items()}
        ag = Agente(fs, diario)
        extensoes = [] if extensoes is None else extensoes
        e = self._executar(extensoes)
        original_chamado = []

        async def original(agente, llm):
            original_chamado.append(True)
            return "original"
        llm = types.SimpleNamespace(function_calls=chamadas, response="")
        inicio = time.monotonic()
        r = await e.processar(ag, llm, original)
        return r, diario, time.monotonic() - inicio, original_chamado, extensoes, e

    async def t_leituras_rodam_ao_mesmo_tempo_e_voltam_na_ordem(self):
        chamadas = [_chamada("search_engine", {"query": "a"}, "c1"), _chamada("document_query", {"document": "d"}, "c2"),
                    _chamada("memory_load", {"query": "m"}, "c3")]
        r, diario, segundos, original, ext, _ = await self._rodar(
            chamadas, {"search_engine": {"espera": 0.3}, "document_query": {"espera": 0.1}, "memory_load": {"espera": 0.2}})
        eq(r, None, "a tarefa continua")
        ok(segundos < 0.5, f"três esperas de 0,1–0,3 s juntas levam ~0,3 s, não 0,6: {segundos:.2f}")
        eq([x[1] for x in diario if x[0] == "historico"], ["search_engine", "document_query", "memory_load"],
           "os resultados entram no histórico na ordem pedida, não na de chegada")
        comecos = [i for i, x in enumerate(diario) if x[0] == "comeca"]
        fins = [i for i, x in enumerate(diario) if x[0] == "termina"]
        ok(max(comecos) < min(fins), "todas começam antes de qualquer uma terminar")
        eq(ext, [("tool_execute_before", "search_engine"), ("tool_execute_before", "document_query"),
                 ("tool_execute_before", "memory_load"), ("tool_execute_after", "search_engine"),
                 ("tool_execute_after", "document_query"), ("tool_execute_after", "memory_load")],
           "as conferências de antes e de depois rodam para cada ferramenta")
        eq(original, [], "não usou o caminho do Agent Zero")

    async def t_erro_de_uma_nao_perde_as_outras(self):
        chamadas = [_chamada("search_engine", {}, "c1"), _chamada("lembrar", {}, "c2")]
        r, diario, *_ = await self._rodar(chamadas, {"search_engine": {"erro": RuntimeError("caiu")}, "lembrar": {}})
        hist = [x for x in diario if x[0] == "historico"]
        ok(len(hist) == 2 and "Erro ao rodar `search_engine`: RuntimeError: caiu" in hist[0][2],
           f"a que falhou vira resultado de erro; a outra entra normal: {hist}")

    async def t_intervencao_para_a_vez(self):
        chamadas = [_chamada("search_engine", {}, "c1"), _chamada("lembrar", {}, "c2")]
        try:
            await self._rodar(chamadas, {"search_engine": {"erro": Intervencao("nova mensagem")}, "lembrar": {}})
        except Intervencao:
            return
        raise Falha("mensagem nova da pessoa no meio para a vez, como no Agent Zero")

    async def t_barreira_no_meio_roda_sozinha_na_ordem(self):
        chamadas = [_chamada("search_engine", {}, "c1"), _chamada("lembrar", {}, "c2"),
                    _chamada("browser", {"action": "open"}, "c3"), _chamada("memory_load", {}, "c4")]
        r, diario, *_ = await self._rodar(chamadas, {n: {"espera": 0.01} for n in ("search_engine", "lembrar", "browser",
                                                                            "memory_load")})
        eq([x[1] for x in diario if x[0] == "historico"], ["search_engine", "lembrar", "browser", "memory_load"],
           "ordem do histórico = ordem pedida")
        ok(("sozinha", "browser") in diario and ("sozinha", "memory_load") in diario,
           "o navegador e o que sobra sozinho vão pelo caminho do Agent Zero")

    async def t_sem_ganho_ou_desligado_usa_o_agent_zero(self):
        _, _, _, original, *_ = await self._rodar([_chamada("search_engine", {}, "c1")], {"search_engine": {}})
        eq(original, [True], "uma chamada só: Agent Zero")
        _, _, _, original, *_ = await self._rodar([_chamada("browser", {}, "c1"), _chamada("celular", {}, "c2")],
                                            {"browser": {}, "celular": {}})
        eq(original, [True], "nada que possa ir junto: Agent Zero")
        e = self._executar([])
        e.DESLIGADO.write_text("")
        try:
            eq(e.ligado(), False, "interruptor")
        finally:
            e.DESLIGADO.unlink(missing_ok=True)

    async def t_resposta_final_dentro_do_grupo_encerra(self):
        chamadas = [_chamada("search_engine", {}, "c1"), _chamada("lembrar", {}, "c2")]
        r, diario, *_ = await self._rodar(chamadas, {"search_engine": {"fim": True}, "lembrar": {}})
        ok(r.startswith("resultado search_engine"), "break_loop de uma ferramenta encerra como no Agent Zero")
        ok(("limpou",) in diario, "e limpa o estado pendente do Responses")

    # ---- the installer --------------------------------------------------------------------------------------------
    def _instalador(self):
        stubs = {"helpers": types.ModuleType("helpers"), "helpers.extension": types.ModuleType("helpers.extension")}
        stubs["helpers.extension"].Extension = object
        return _modulo("acoes_paralelas_instalar_teste",
                       RAIZ / "extensions" / "python" / "agent_init" / "_20_acoes_paralelas.py", stubs)

    def t_so_instala_na_versao_conhecida_do_agent_zero(self):
        m = self._instalador()

        class Outra:
            async def process_llm_result_tools(self, llm):
                return "x"

            async def _execute_tool_request(self, **k):
                return None
        eq(m.instalar(Outra), "versao diferente: process_llm_result_tools", "outra versão: não troca nada")
        ok(getattr(Outra, m.MARCA, None) is None, "e não marca")
        m.CONHECIDOS = {k: m.assinatura(getattr(Outra, k)) for k in m.CONHECIDOS}
        original = Outra.process_llm_result_tools
        eq(m.instalar(Outra), "instalado", "versão conhecida: instala")
        eq(m.instalar(Outra), "ja", "uma vez só")
        ok(Outra.process_llm_result_tools is not original and getattr(Outra, m.MARCA) is original,
           "o método original fica guardado")
        fonte = Path("/home/user/src/agent-zero/agent.py")
        if fonte.exists():
            import ast
            import hashlib
            import textwrap
            texto = fonte.read_text(encoding="utf-8")
            linhas = texto.splitlines(keepends=True)
            for no in ast.walk(ast.parse(texto)):
                if isinstance(no, ast.ClassDef) and no.name == "Agent":
                    for f in no.body:
                        if getattr(f, "name", "") in m.CONHECIDOS:
                            md5 = hashlib.md5(textwrap.dedent("".join(linhas[f.lineno - 1:f.end_lineno])).encode()).hexdigest()
                            eq(md5, self._instalador().CONHECIDOS[f.name], f"assinatura de {f.name} igual à do Agent Zero")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                feito = getattr(self, nome)()
                if asyncio.iscoroutine(feito):
                    await feito
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print(("✓ " if x["ok"] else "✗ ") + x["teste"] + ("" if x["ok"] else f": {x['erro']} {x['onde']}"))
    print(f"{r['passou']}/{r['total']}")
    sys.exit(0 if r["passou"] == r["total"] else 1)
