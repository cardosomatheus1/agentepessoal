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
        for f in ("prospeccao", "conteudo", "code_execution_tool", "text_editor", "scheduler", "livro", "contas",
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
