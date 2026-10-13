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
