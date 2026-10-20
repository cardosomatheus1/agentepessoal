"""Tests of the login rules (no web server; temporary users file only). Run with implantar.py (staging copy) or
inside the container."""

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import time
import traceback
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


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.u = _carregar("login_usuarios_teste", RAIZ / "helpers" / "usuarios.py")
        self.resultados = []

    def t_trava_so_o_ip_que_errou(self):
        # 12/10 review: a global lock let anyone, from a few addresses, lock the owner out
        u, agora = self.u, time.time()
        b = u.Bloqueio()
        for i in range(u.TENTATIVAS):
            ok(not b.bloqueado("1.1.1.1", agora), f"tentativa {i + 1} ainda não trava")
            b.falhou("1.1.1.1", agora)
        ok(b.bloqueado("1.1.1.1", agora), "o IP que errou 5 vezes fica travado")
        for n in range(40):  # many other addresses failing (distributed attack)
            b.falhou(f"10.0.{n}.1", agora)
        ok(not b.bloqueado("200.200.200.200", agora), "o dono, de outro IP, nunca é trancado para fora")
        ok(b.espera(agora) == 5.0, "com muitas falhas no total, cada erro só fica mais lento")
        ok(not b.bloqueado("1.1.1.1", agora + u.JANELA + 1), "a trava do IP passa em 15 min")
        b.ok("1.1.1.1")
        ok(not b.bloqueado("1.1.1.1", agora), "acertar a senha limpa o IP")
        ok(u.Bloqueio().espera(agora) == 1.0, "normalmente, 1 s por erro")

    def t_bloqueio_de_deploy_antigo_e_trocado(self):
        # 13/10: the web process kept a Bloqueio of the previous class (no espera) and wrong passwords gave 500
        u = self.u
        class Velho:
            def bloqueado(self, ip): return False
        ext = {"login_usuarios_bloqueio": Velho()}
        b = u.bloqueio_do_app(ext)
        ok(isinstance(b, u.Bloqueio) and hasattr(b, "espera"), "instância antiga trocada pela atual")
        ok(u.bloqueio_do_app(ext) is b, "a atual é mantida entre pedidos")
        b.falhou("1.2.3.4"); ok(u.bloqueio_do_app(ext).falhas.get("1.2.3.4"), "as falhas ficam guardadas")

    def t_modulo_recarrega_depois_do_deploy(self):
        # 13/10: the web process kept the helpers module from before the deploy (no bloqueio_do_app): every login 500
        import ast, os, types
        ext = next((RAIZ / "extensions").rglob("_10_varios_usuarios.py"))
        arvore = ast.parse(ext.read_text(encoding="utf-8"))
        fonte = ast.get_source_segment(ext.read_text(encoding="utf-8"), next(n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == "_mod"))
        g = {"sys": sys, "importlib": importlib, "Path": Path, "__file__": str(ext)}
        exec(fonte, g)
        velho = types.ModuleType("login_usuarios_helpers"); velho._mtime = -1
        sys.modules["login_usuarios_helpers"] = velho
        try:
            m = g["_mod"]()
            ok(m is not velho and hasattr(m, "bloqueio_do_app"), "o módulo antigo é trocado pelo do arquivo atual")
            ok(g["_mod"]() is m, "sem mudança no arquivo, reaproveita o mesmo módulo")
        finally:
            sys.modules.pop("login_usuarios_helpers", None)

    def t_verificar_senha(self):
        u = self.u
        tmp = Path(tempfile.mkdtemp(prefix="login-teste-"))
        try:
            u.ARQUIVO = tmp / "usuarios.json"
            sal = "00" * 16
            h = hashlib.pbkdf2_hmac("sha256", b"certa", bytes.fromhex(sal), 1000).hex()
            u.ARQUIVO.write_text(json.dumps({"usuarios": {"ana": {"nome": "Ana", "salt": sal, "hash": h, "iter": 1000}}}))
            ok(u.verificar("Ana ", "certa") is not None, "senha certa entra (login sem diferença de maiúscula/espaço)")
            ok(u.verificar("ana", "errada") is None, "senha errada não entra")
            ok(u.verificar("ninguem", "x") is None, "usuário que não existe não entra")
            h2 = hashlib.pbkdf2_hmac("sha256", b"do-operador", bytes.fromhex("11" * 16), 1000).hex()
            u.ARQUIVO.write_text(json.dumps({"usuarios": {"ana": {"nome": "Ana", "salt": sal, "hash": h, "iter": 1000,
                                 "operador": {"salt": "11" * 16, "hash": h2, "iter": 1000}}}}))
            ok(u.verificar("ana", "do-operador") is not None and u.verificar("ana", "certa") is not None,
               "a senha dos scripts do operador entra como o mesmo login, e a da pessoa continua valendo")
            ok(u.verificar("ana", "errada") is None, "e senha errada continua sem entrar")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- 15/10: guests (Ilia, Matheus's friend): own project, only personal tools, own files, spending tagged ----
    def _c(self):
        return _carregar("login_usuarios_convidados_teste", RAIZ / "helpers" / "convidados.py")

    def t_convidado_so_ferramentas_pessoais(self):
        c = self._c()
        proj = c.projeto("ilia")
        ok(c.bloqueio("matheus", "prospeccao", {}, None) == "", "o dono nunca é barrado aqui")
        ok(c.bloqueio("fernanda", "code_execution_tool", {}, None) == "", "quem não é convidado também não")
        for f in ("prospeccao", "conteudo", "code_execution_tool", "text_editor", "livro", "contas",
                  "skills_tool", "parallel", "whatsapp_guardar_token", "google.gmail_listar"):
            ok("não está disponível" in c.bloqueio("ilia", f, {}, proj), f"convidado sem {f}")
        for f in ("response", "search_engine", "pesquisar", "browser", "lembrar", "memory_load", "document_query"):
            ok(c.bloqueio("Ilia", f, {"query": "previsão do tempo em Salvador"}, proj) == "", f"convidado usa {f}")
        ok("fora do projeto" in c.bloqueio("ilia", "search_engine", {}, None), "conversa dele fora do projeto: nada roda")
        ok("fora do projeto" in c.bloqueio("ilia", "response", {}, "meta-nexos"), "nem em projeto de outra pessoa")
        # 15/10: Will, same rules as Ilia; one guest never runs in the other's project
        ok(c.convidado("will") and "não está disponível" in c.bloqueio("will", "prospeccao", {}, c.projeto("will")), "Will é convidado")
        ok("fora do projeto" in c.bloqueio("will", "response", {}, proj), "Will não roda no projeto do Ilia")

    def t_convidado_so_os_arquivos_dele(self):
        c = self._c()
        proj = c.projeto("ilia")
        meu = "/a0/usr/whatsapp/ilia/2026-10/15-101010-tg5.jpg"
        ok(c.bloqueio("ilia", "document_query", {"document": meu}, proj) == "", "arquivo que ele mandou")
        ok(c.bloqueio("ilia", "whatsapp_enviar", {"arquivo": "/a0/usr/projects/convidado-ilia/resumo.pdf"}, proj) == "",
           "arquivo criado no projeto dele")
        for ruim in ("/a0/usr/prospeccao/leads.json", "/a0/usr/whatsapp/matheus/2026-10/x.jpg", "/a0/usr/segredos/matheus.json",
                     "/a0/usr/whatsapp/ilia/../matheus/x.jpg", "file:///a0/usr/usuarios.json", "/etc/passwd",
                     "usr/prospeccao/leads.json", "../usr/segredos/matheus.json", "/a0/usr/whatsapp/ilia-falso/x"):
            ok("fora dos arquivos" in c.bloqueio("ilia", "document_query", {"document": ruim}, proj), f"recusado: {ruim}")
        ok("fora dos arquivos" in c.bloqueio("ilia", "whatsapp_enviar", {"arquivo": "/a0/usr/conteudo/agenda.json"}, proj),
           "não manda arquivo do Matheus para o celular dele")
        ok(c.bloqueio("ilia", "browser", {"message": "abra https://g1.globo.com/home/ultimas e resuma"}, proj) == "",
           "o /home dentro de um site não é caminho local")
        for interno in ("http://host.docker.internal:8787/arquivos/conteudo", "http://localhost/api/chats",
                        "http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8789/andamento"):
            ok("internos" in c.bloqueio("ilia", "browser", {"message": f"abra {interno}"}, proj), f"interno: {interno}")
        ok(c.bloqueio("ilia", "response", {"text": "salvei em /a0/usr/whatsapp/matheus"}, proj) == "",
           "responder com texto nunca é barrado por caminho")

    def t_convidado_projeto_preparado(self):
        c = self._c()
        tmp = Path(tempfile.mkdtemp(prefix="convidado-"))
        try:
            criados, headers = [], {}

            class Projetos:
                def get_project_folder(self, nome):
                    return str(tmp / nome)

                def create_project(self, nome, dados):
                    criados.append(nome)
                    (tmp / nome / ".a0proj").mkdir(parents=True)
                    (tmp / nome / ".a0proj" / "project.json").write_text(json.dumps(dados))

                def load_basic_project_data(self, nome):
                    return json.loads((tmp / nome / ".a0proj" / "project.json").read_text())

                def save_project_header(self, nome, dados):
                    (tmp / nome / ".a0proj" / "project.json").write_text(json.dumps(dados))

            pj = Projetos()
            nome = c.preparar("ilia", pj, ["local:response", "plugin:pesquisa:pesquisar"])
            meta = tmp / nome / ".a0proj"
            ok(nome == "convidado-ilia" and criados == [nome], "projeto criado uma vez")
            ok((meta / "dono.txt").read_text() == "ilia", "o projeto é dele (some da lista do Matheus)")
            pol = json.loads((meta / "plugins" / "_tool_access" / "config.json").read_text())
            ok(pol == {"mode": "custom", "default": "block", "mcp_default": "block",
                       "allowed": ["local:response", "plugin:pesquisa:pesquisar"], "blocked": []}, f"política: {pol}")
            ok("Ilia" in json.loads((meta / "project.json").read_text())["instructions"], "instruções com o nome dele")
            dados = json.loads((meta / "project.json").read_text()); dados["instructions"] = "velha"
            (meta / "project.json").write_text(json.dumps(dados))
            ok(c.preparar("ilia", pj, ["local:response"]) == nome and criados == [nome], "de novo: não recria")
            ok("Ilia" in json.loads((meta / "project.json").read_text())["instructions"], "instruções atualizadas")
            ok(json.loads((meta / "plugins" / "_tool_access" / "config.json").read_text())["allowed"] == ["local:response"],
               "política atualizada")
            try:
                c.preparar("matheus", pj, [])
                ok(False, "o dono não vira convidado")
            except ValueError:
                pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def t_convidado_ids_das_ferramentas(self):
        c = self._c()
        tmp = Path(tempfile.mkdtemp(prefix="ferramentas-"))
        try:
            for arq in ("usr/pesquisa/tools/pesquisar.py", "core/_browser/tools/browser.py", "usr/_browser/tools/x.py",
                        "nucleo/response.py"):
                (tmp / arq).parent.mkdir(parents=True, exist_ok=True); (tmp / arq).write_text("")
            ids = c.ids_ferramentas(("pesquisar", "browser", "response", "sumiu"), (tmp / "usr", tmp / "core"), tmp / "nucleo")
            ok(ids == ["plugin:pesquisa:pesquisar", "plugin:_browser:browser", "local:response", "local:sumiu"], f"{ids}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def t_convidado_lingua_e_lugar(self):
        # 15/10: Ilia's Russian voice notes were forced into Portuguese and the agent searched far from his route
        c = self._c()
        ok("idioma" in c.CONVIDADOS["ilia"] and c.CONVIDADOS["ilia"]["idioma"] is None, "áudio do Ilia: língua detectada")
        txt = c.instrucoes("ilia")
        ok("na língua em que Ilia escrever" in txt and "em português" not in txt, "responde na língua dele")
        ok("Google Maps" in txt and "pergunte antes de pesquisar" in txt, "pedido de lugar: pontos dele, distância e mapa")

    def t_convidado_rotinas(self):
        # 16/10, Matheus: "os convidados devem poder" criar tarefas agendadas — só as dele, poucas, no máximo por hora
        c = self._c()
        proj = c.projeto("will")
        ok(c.bloqueio("will", "scheduler", {"action": "list_tasks"}, proj) == "", "convidado usa o agendador")
        ok(c.bloqueio("will", "scheduler:create_scheduled_task", {}, proj) == "", "também com o método no nome")
        ok("Rotinas de convidado" in c.instrucoes("will") or "criar rotinas" in c.instrucoes("will"), "ele sabe que pode")
        diaria = {"name": "Resumo", "prompt": "x", "schedule": {"minute": "0", "hour": "9", "day": "*", "month": "*", "weekday": "*"}}
        ok(c.regra_agenda("will", "create_scheduled_task", diaria, [], False) == "", "todo dia às 9h pode")
        for ruim in ("*", "*/5", "0,30", ""):
            a = {**diaria, "schedule": {**diaria["schedule"], "minute": ruim}}
            ok("hora em hora" in c.regra_agenda("will", "create_scheduled_task", a, [], False), f"minuto {ruim!r} recusado")
        ok("hora em hora" in c.regra_agenda("will", "create_scheduled_task", {"schedule": "*/10 * * * *"}, [], False), "cron em texto")
        ok(c.regra_agenda("will", "create_scheduled_task", {"schedule": "15 8 * * 1-5"}, [], False) == "", "cron em texto ok")
        ok("máximo é 5" in c.regra_agenda("will", "create_adhoc_task", {}, [object()] * 5, False), "no máximo 5 rotinas")
        for acao in ("delete_task", "run_task", "update_task", "show_task", "wait_for_task"):
            ok("não é desta pessoa" in c.regra_agenda("will", acao, {"uuid": "x"}, [], False), f"{acao} na tarefa de outro")
            ok(c.regra_agenda("will", acao, {"uuid": "x"}, [object()], True) == "" or acao == "update_task", f"{acao} na dele")
        ok("hora em hora" in c.regra_agenda("will", "update_task", {"uuid": "x", "schedule": {"minute": "*"}}, [object()], True),
           "nem mudando a rotina para cada minuto")
        ok("não está disponível" in c.regra_agenda("will", "apagar_tudo", {}, [], True), "ação desconhecida")
        ok("No máximo 24" in c.regra_agenda("will", "create_planned_task", {"plan": {"todo": ["2026-10-17T09:00"] * 25}}, [], False),
           "tarefa planejada com execuções demais")
        tarefas = [{"name": "Minha", "project_name": proj}, {"name": "Prospecção do Matheus", "project_name": None},
                   {"name": "Do Ilia", "project_name": "convidado-ilia"}]
        ok([t["name"] for t in json.loads(c.filtrar_agenda("will", json.dumps(tarefas)))] == ["Minha"], "lista só as dele")
        ok(c.filtrar_agenda("will", json.dumps(tarefas[1])) == "Nenhuma tarefa encontrada.", "não mostra a de outro")
        ok(json.loads(c.filtrar_agenda("will", json.dumps(tarefas[0])))["name"] == "Minha", "mostra a dele")
        ok(c.decidir_pausa(True, [("a", "idle"), ("b", "disabled"), ("c", "running")], []) == (["a"], []),
           "passou do limite: pausa as que esperam")
        ok(c.decidir_pausa(False, [("a", "disabled"), ("b", "disabled")], ["a"]) == ([], ["a"]),
           "no dia seguinte volta só a que foi pausada pelo limite")
        ext = (RAIZ / "extensions" / "python" / "tool_execute_before" / "_02_convidado.py").read_text(encoding="utf-8")
        ok("regra_agenda" in ext and "t.project_name == c.projeto(login)" in ext, "a trava usa as tarefas do projeto dele")
        ok((RAIZ / "extensions" / "python" / "tool_execute_after" / "_05_agenda_convidado.py").exists()
           and (RAIZ / "extensions" / "python" / "job_loop" / "_20_limite_convidados.py").exists(), "filtro e pausa ligados")

    def t_convidado_computador_isolado(self):
        # 16/10, Matheus: terminal, código e arquivos "precisa ser isolado, de forma alguma acessar nada meu"
        c = self._c()
        proj = c.projeto("will")
        ok(c.bloqueio("will", "terminal_isolado", {"comando": "ls /etc"}, proj) == "", "a caixa dele roda o que ele quiser")
        for f in ("code_execution_tool", "text_editor", "input"):
            ok("não está disponível" in c.bloqueio("will", f, {}, proj), f"nunca o {f} do agente")
        tool = (RAIZ / "tools" / "terminal_isolado.py").read_text(encoding="utf-8")
        ok("host.docker.internal:8790" in tool and "convidado(login)" in tool and "subprocess" not in tool,
           "a ferramenta só pede à caixa do convidado; não roda nada aqui")
        ok("computador próprio" in c.instrucoes("will"), "ele sabe que tem")

    def t_tarefa_e_do_dono_do_projeto(self):
        # 16/10: a routine's own chat has no "dono"; it belongs to its project's owner (a guest's routine reports to him)
        if "agent" in sys.modules:
            return  # inside the agent: the real modules are loaded; the fake ones below would replace them
        tmp = Path(tempfile.mkdtemp())
        (tmp / "dono.txt").write_text("will")

        class Ctx:
            def __init__(self, cid, dados):
                self.id, self.dados = cid, dados

            def get_data(self, k):
                return self.dados.get(k)

            def get_output_data(self, k):
                return None

        ctxs = {"T": Ctx("T", {}), "M": Ctx("M", {"dono": "matheus"}), "S": Ctx("S", {})}
        projetos = {"T": "convidado-will", "S": None}
        agent = type(sys)("agent")
        agent.AgentContext = type("AC", (), {"get": staticmethod(lambda i: ctxs.get(i))})
        helpers = type(sys)("helpers")
        projects = type(sys)("helpers.projects")
        projects.get_context_project_name = lambda ctx: projetos.get(ctx.id)
        projects.get_project_meta = lambda nome, arq: str(tmp / arq) if nome == "convidado-will" else "/nao/existe"
        helpers.projects = projects
        antes = {k: sys.modules.get(k) for k in ("agent", "helpers", "helpers.projects")}
        sys.modules.update({"agent": agent, "helpers": helpers, "helpers.projects": projects})
        try:
            sep = _carregar("separacao_teste", RAIZ / "helpers" / "separacao.py")
            ok(sep.dono_contexto(ctxs["T"]) == "will", "rotina no projeto do Will é do Will")
            ok(sep.dono_contexto(ctxs["M"]) == "matheus", "quem tem dono continua com ele")
            ok(sep.dono_contexto(ctxs["S"]) == "matheus", "sem dono e sem projeto: do Matheus, como antes")
        finally:
            for k, v in antes.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def t_gasto_marcado_com_o_dono(self):
        c = self._c()

        class Modelo:
            def __init__(self):
                self.kwargs = {"temperature": 0, "extra_headers": {"X-Outro": "1"}}

        m = Modelo()
        n = c.com_dono(m, "Ilia")
        ok(n is not m and n.kwargs["extra_headers"] == {"X-Outro": "1", "X-A0-Dono": "ilia"} and n.kwargs["temperature"] == 0,
           f"cópia com o cabeçalho: {n.kwargs}")
        ok(m.kwargs == {"temperature": 0, "extra_headers": {"X-Outro": "1"}}, "o modelo original (compartilhado) não muda")
        ok(c.com_dono(m, "../x") is m and c.com_dono(m, "") is m and c.com_dono(None, "ilia") is None, "dono inválido: nada muda")

    def t_rastreio_da_chamada(self):
        # 20/10: each model call says which chat, routine and agent made it (proxy: cache diagnosis and settings)
        r = _carregar("login_usuarios_rastreio_teste", RAIZ / "helpers" / "rastreio.py")

        class Ctx:
            def __init__(self, cid, dados=None):
                self.id, self.dados = cid, dados or {}

            def get_data(self, k):
                return self.dados.get(k)

            def get_output_data(self, k):
                return None

        tarefa = type("T", (), {"uuid": "HL76nfIg"})()
        ctxs = {"R": Ctx("R"), "P": Ctx("P", {"_parallel_parent_context_id": "R"}), "M": Ctx("M"),
                "L": Ctx("L", {"parent_context_id": "L"})}
        tarefas = lambda cid: [tarefa] if cid == "R" else []  # noqa: E731
        eq(r.rotina_de(ctxs["R"], tarefas, ctxs.get), "HL76nfIg", "chat da rotina")
        eq(r.rotina_de(ctxs["P"], tarefas, ctxs.get), "HL76nfIg", "trabalhador paralelo aberto pela rotina")
        eq(r.rotina_de(ctxs["M"], tarefas, ctxs.get), "", "conversa de uma pessoa: sem rotina")
        eq(r.rotina_de(ctxs["L"], tarefas, ctxs.get), "", "pai apontando para si mesmo não trava")
        eq(r.cabecalhos("abc-1", "HL76nfIg", 0, "chat"),
           {"X-A0-Conversa": "abc-1", "X-A0-Rotina": "HL76nfIg", "X-A0-Agente": "0", "X-A0-Papel": "chat"}, "cabeçalhos")
        eq(r.cabecalhos("a b", "", 100, "outro"), {}, "valores tortos ficam de fora")
        eq(r.cabecalhos("abc", None, 2, "util"), {"X-A0-Conversa": "abc", "X-A0-Agente": "2", "X-A0-Papel": "util"},
           "sem rotina, ajudante 2, modelo utilitário")
        eq(r.do_agente(object(), "chat"), {}, "agente estranho: nada, sem erro")
        c = self._c()

        class Modelo:
            def __init__(self):
                self.kwargs = {"extra_headers": {"X-Outro": "1"}}

        m = Modelo()
        n = c.com_dono(m, "matheus", {"X-A0-Conversa": "abc"})
        eq(n.kwargs["extra_headers"], {"X-Outro": "1", "X-A0-Dono": "matheus", "X-A0-Conversa": "abc"}, "dono e rastreio")
        ok(m.kwargs == {"extra_headers": {"X-Outro": "1"}}, "o modelo original não muda")
        eq(c.com_dono(m, "", {"X-A0-Conversa": "abc"}).kwargs["extra_headers"], {"X-Outro": "1", "X-A0-Conversa": "abc"},
           "sem dono válido, o rastreio vai assim mesmo")
        # the two extensions (chat and utility model) end to end, with a fake scheduler
        helpers_mod = sys.modules.get("helpers")
        nomes = ("agent", "helpers.task_scheduler", "helpers.extension")
        antes = {k: sys.modules.get(k) for k in nomes + ("helpers",)}
        agent_mod = type(sys)("agent")
        agent_mod.AgentContext = type("AC", (), {"get": staticmethod(lambda i: ctxs.get(i))})
        ts = type(sys)("helpers.task_scheduler")
        ts.TaskScheduler = type("TS", (), {"get": staticmethod(lambda: type("S", (), {
            "get_tasks_by_context_id": staticmethod(tarefas)})())})
        try:
            sys.modules.update({"agent": agent_mod, "helpers.task_scheduler": ts})
            if helpers_mod is None:
                sys.modules["helpers"] = type(sys)("helpers")
            try:
                import helpers.extension  # noqa: F401  (the real one inside Agent Zero)
            except Exception:
                ext = type(sys)("helpers.extension")
                ext.Extension = type("Extension", (), {})
                sys.modules["helpers.extension"] = ext
            for pasta, papel in (("chat_model_call_before", "chat"), ("util_model_call_before", "util")):
                e = _carregar(f"quem_gasta_{papel}_teste", RAIZ / "extensions" / "python" / pasta / "_10_quem_gasta.py")
                obj = e.QuemGasta.__new__(e.QuemGasta)
                obj.agent = type("A", (), {"context": ctxs["P"], "number": 1})()
                dados = {"model": Modelo()}
                coro = obj.execute(call_data=dados)
                try:
                    coro.send(None)
                except StopIteration:
                    pass
                cab = dados["model"].kwargs["extra_headers"]
                eq({k: v for k, v in cab.items() if k.startswith("X-A0-") and k != "X-A0-Dono"},
                   {"X-A0-Conversa": "P", "X-A0-Rotina": "HL76nfIg", "X-A0-Agente": "1", "X-A0-Papel": papel},
                   f"extensão {pasta}")
        finally:
            for k, v in antes.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def t_sonnet_so_para_o_matheus(self):
        # 20/10: Matheus asked for Sonnet 5.5 only for himself; routines and guests stay on the default model
        import json as _json
        cfg = _json.loads((RAIZ / "modelo_por_dono.json").read_text(encoding="utf-8"))
        import importlib.util as _u
        spec = _u.spec_from_file_location("modelo_teste_sonnet", RAIZ / "helpers" / "modelo.py")
        M = _u.module_from_spec(spec); spec.loader.exec_module(M)
        eq(M.preset_para(cfg, "matheus", "c1", False), "Sonnet", "conversa do Matheus: Sonnet")
        eq(M.preset_para(cfg, "matheus", "c1", True), "", "rotina do Matheus: modelo padrão")
        eq(M.preset_para(cfg, "ilia", "c2", False), "", "convidado: modelo padrão")
        eq(M.preset_para(cfg, "will", "c3", False), "", "convidado: modelo padrão")

    def t_modelo_por_dono_pronto_e_desligado(self):
        # 20/10: ready for "Sonnet only for Matheus", off while there is no file
        import json as _json
        import tempfile as _tf
        M = _carregar("login_modelo_teste", RAIZ / "helpers" / "modelo.py")

        class Ctx:
            def __init__(self, cid, **dados):
                self.id, self.dados = cid, dict(dados)

            def get_data(self, k):
                return self.dados.get(k)

            def set_data(self, k, v):
                self.dados[k] = v

        pasta = Path(_tf.mkdtemp(prefix="modelo-teste-"))
        try:
            eq(M.ler(pasta / "nao-existe.json"), {}, "sem arquivo: desligado")
            (pasta / "m.json").write_text("{quebrado", encoding="utf-8")
            eq(M.ler(pasta / "m.json"), {}, "arquivo ilegível: desligado")
        finally:
            import shutil as _sh
            _sh.rmtree(pasta, ignore_errors=True)
        cfg = {"donos": {"matheus": "Sonnet"}, "conversas": {"c9": "Default"}}
        c = Ctx("c1")
        eq(M.aplicar(c, "Matheus", False, {}), "", "desligado: nada")
        ok(c.get_data(M.CHAVE) is None, "nada gravado")
        eq(M.aplicar(c, "matheus", False, cfg), "ligou:Sonnet", "conversa do Matheus: preset dele")
        eq(c.get_data(M.CHAVE), {"preset_name": "Sonnet"}, "pela escolha da própria conversa")
        eq(M.aplicar(c, "matheus", False, cfg), "", "de novo: nada muda")
        eq(M.aplicar(c, "matheus", False, {}), "desligou", "arquivo apagado: volta ao padrão")
        ok(c.get_data(M.CHAVE) is None and c.get_data(M.AUTO) is None, "limpo")
        r = Ctx("r1")
        eq(M.aplicar(r, "matheus", True, cfg), "", "rotina fica no padrão")
        eq(M.aplicar(r, "matheus", True, {**cfg, "rotinas": True}), "ligou:Sonnet", "com rotinas: true, a rotina também")
        eq(M.aplicar(Ctx("c9"), "matheus", False, cfg), "ligou:Default", "a conversa nomeada vence o dono")
        eq(M.aplicar(Ctx("i1"), "ilia", False, cfg), "", "outro dono: nada")
        manual = Ctx("c2", chat_model_override={"preset_name": "Luna alto"})
        eq(M.aplicar(manual, "matheus", False, cfg), "manual", "escolha feita na tela nunca é trocada")
        eq(manual.get_data(M.CHAVE), {"preset_name": "Luna alto"}, "continua a dele")
        eq(M.aplicar(manual, "matheus", False, {}), "manual", "nem desfeita")
        texto = (RAIZ / "extensions" / "python" / "monologue_start" / "_30_modelo_por_dono.py").read_text(encoding="utf-8")
        ok("if not cfg and not ctx.get_data(M.AUTO):" in texto, "desligado, a extensão nem olha a conversa")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
