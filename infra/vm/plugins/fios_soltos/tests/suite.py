"""Tests of the loose-ends register's safe writes (temporary folder only; never the live register).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import shutil
import sys
import tempfile
import threading
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "teste_fios"


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
        self.f = _carregar("fios_teste", RAIZ / "helpers" / "fios.py")
        self.resultados = []

    def _pasta_nova(self):
        if getattr(self, "_tmp", None):
            shutil.rmtree(self._tmp, ignore_errors=True)
        self._tmp = Path(tempfile.mkdtemp(prefix="fios-teste-"))
        self.f.PASTA = self._tmp

    def t_salvar_ignorar_adiar(self):
        f = self.f
        eq(f.mesclar(LOGIN, [{"titulo": "Pagar a conta de luz", "prioridade": "alta"}]), (1, 0, 0), "criado")
        fid = f.carregar(LOGIN)["fios"][0]["id"]
        eq(f.adiar(LOGIN, fid, 2)["estado"], "adiado", "adiado")
        eq(f.ignorar(LOGIN, fid)["estado"], "ignorado", "ignorado")
        ok("Pagar a conta de luz" in f.carregar(LOGIN)["ruido"], "assunto ignorado vira ruído (não volta)")
        f.mesclar(LOGIN, [{"titulo": "Mandar o contrato"}])
        outro = next(x["id"] for x in f.carregar(LOGIN)["fios"] if x["titulo"] == "Mandar o contrato")
        eq(f.mesclar(LOGIN, [], [outro]), (0, 0, 1), "resolvido")
        eq(f.mesclar(LOGIN, [], [outro]), (0, 0, 0), "resolver de novo não conta")
        ok(not list(f.PASTA.glob(".*.tmp")), "nenhum temporário largado")

    def t_registro_ilegivel_nao_vira_vazio(self):
        f = self.f
        f.mesclar(LOGIN, [{"titulo": "Responder a Anna"}])
        arq = f.arquivo(LOGIN)
        arq.write_text('{"fios": [{"titulo": "Respon', encoding="utf-8")
        try:
            f.mesclar(LOGIN, [{"titulo": "Outro"}])
            raise Falha("gravar por cima de um registro ilegível devia dar erro")
        except f.EstadoIlegivel:
            pass
        eq(arq.read_text(encoding="utf-8"), '{"fios": [{"titulo": "Respon', "o registro não foi sobrescrito")

    def t_gravacoes_simultaneas_nao_se_apagam(self):
        f = self.f
        erros = []

        def gravar(prefixo):
            try:
                for i in range(15):
                    f.mesclar(LOGIN, [{"titulo": f"{prefixo} {i}"}])
            except Exception as exc:  # pragma: no cover
                erros.append(repr(exc))

        fios = [threading.Thread(target=gravar, args=(p,)) for p in ("a", "b", "c")]
        [x.start() for x in fios]
        [x.join() for x in fios]
        eq(erros, [], "sem erro")
        eq(len(f.carregar(LOGIN)["fios"]), 45, "os 45 fios ficaram (nenhuma gravação apagou a outra)")

    async def rodar(self, so=""):
        try:
            for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
                self._pasta_nova()
                try:
                    getattr(self, nome)()
                    self.resultados.append({"teste": nome, "ok": True})
                except Exception as exc:
                    self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                            "onde": traceback.format_exc().splitlines()[-3:]})
        finally:
            shutil.rmtree(getattr(self, "_tmp", ""), ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
