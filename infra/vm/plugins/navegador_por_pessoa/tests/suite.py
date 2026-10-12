"""Tests of where the browser profiles live (temporary folders only; never the live profiles).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.p = _carregar("navegador_perfis_teste", RAIZ / "helpers" / "perfis.py")
        self.resultados = []

    def _cenario(self):
        base = Path(tempfile.mkdtemp(prefix="perfis-teste-"))
        self._tmp.append(base)
        sessoes, fora = base / "tmp" / "browser" / "sessions", base / "usr" / "navegador" / "sessions"
        return base, sessoes, fora

    def _perfil(self, pasta: Path, pid: int | None = None):
        (pasta / "shared" / "Default").mkdir(parents=True, exist_ok=True)
        (pasta / "shared" / "Default" / "Cookies").write_text("login")
        if pid is not None:
            os.symlink(f"f2a42967c635-{pid}", pasta / "shared" / "SingletonLock")

    def t_antes_da_copia_nada_muda(self):
        _, sessoes, fora = self._cenario()
        self._perfil(sessoes)
        eq(self.p.guardar_perfis_fora(sessoes, fora), "sem cópia fora do contêiner", "sem a cópia, não mexe")
        ok(sessoes.is_dir() and not sessoes.is_symlink(), "a pasta do contêiner continua onde estava")

    def t_com_a_copia_liga_e_guarda_a_antiga(self):
        _, sessoes, fora = self._cenario()
        self._perfil(sessoes, pid=999999)  # SingletonLock left by a Chromium that is gone (container restarted)
        self._perfil(fora)
        eq(self.p.guardar_perfis_fora(sessoes, fora, cmdline=lambda pid: b""), "ligado", "liga com a cópia")
        ok(sessoes.is_symlink() and sessoes.resolve() == fora.resolve(), "a pasta virou um atalho para a cópia")
        eq((sessoes / "shared" / "Default" / "Cookies").read_text(), "login", "o navegador acha os logins pelo atalho")
        antigas = list(sessoes.parent.glob("sessions.antes-*"))
        eq(len(antigas), 1, "a pasta antiga fica guardada ao lado, não é apagada")
        ok((antigas[0] / "shared" / "Default" / "Cookies").exists(), "com o conteúdo")
        eq(self.p.guardar_perfis_fora(sessoes, fora), "ok", "de novo: já está ligado, nada muda")

    def t_contêiner_novo_sem_pasta(self):
        _, sessoes, fora = self._cenario()
        self._perfil(fora)
        eq(self.p.guardar_perfis_fora(sessoes, fora), "ligado", "contêiner recriado (sem pasta): liga direto")
        ok((sessoes / "shared" / "Default" / "Cookies").exists(), "os logins voltam no contêiner novo")

    def t_navegador_aberto_espera(self):
        _, sessoes, fora = self._cenario()
        self._perfil(sessoes, pid=4242)
        self._perfil(fora)
        aberto = lambda pid: b"/usr/bin/chromium\x00--user-data-dir=/a0/tmp/browser/sessions/shared" if pid == 4242 else b""  # noqa: E731
        eq(self.p.guardar_perfis_fora(sessoes, fora, cmdline=aberto), "navegador aberto: fica para o próximo início",
           "com o Chromium usando o perfil, não troca")
        ok(sessoes.is_dir() and not sessoes.is_symlink(), "nada foi movido")
        outro = lambda pid: b"python3\x00run_ui.py"  # noqa: E731  (after a restart the pid belongs to something else)
        eq(self.p.guardar_perfis_fora(sessoes, fora, cmdline=outro), "ligado", "trava velha de outro processo não conta")

    async def rodar(self, so=""):
        self._tmp = []
        try:
            for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
                try:
                    getattr(self, nome)()
                    self.resultados.append({"teste": nome, "ok": True})
                except Exception as exc:
                    self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                            "onde": traceback.format_exc().splitlines()[-3:]})
        finally:
            for t in self._tmp:
                shutil.rmtree(t, ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
