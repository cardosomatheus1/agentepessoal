"""Tests of the phone notices (no network: the bridge call is replaced; temporary folder only).
Run with implantar.py (staging copy) or inside the container. paralelo.py next to this is a separate host test."""

import importlib.util
import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "pessoa_teste"  # not "teste_*": those never reach the sending code


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


class _Resposta:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": true}'


class Suite:
    def __init__(self):
        spec = importlib.util.spec_from_file_location("whatsapp_ponte_teste", RAIZ / "helpers" / "ponte.py")
        self.p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.p)
        self.resultados = []

    def _preparar(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="avisos-teste-"))
        self.p.AVISOS = self._tmp
        self.enviados = []
        p = self.p

        def falso_urlopen(req, timeout=0):
            self.enviados.append(json.loads(req.data))
            return _Resposta()

        p._abrir = falso_urlopen
        p.chave = lambda: "x"

    def t_aviso_igual_nao_sai_de_novo(self):
        p = self.p
        texto = "💬 *@zen.marmitas respondeu* no comentário: «oieeee….entra sim!!!»"
        eq(p.enviar(LOGIN, texto, tipo="progresso"), "", "primeiro sai")
        eq(p.enviar(LOGIN, texto + "  ", tipo="progresso"), "", "o repetido conta como entregue para quem chamou")
        eq(len(self.enviados), 1, "o repetido (só espaço a mais) não chega ao celular")
        segurados = p._ler_jsonl(p.AVISOS / f"{LOGIN}.segurados.jsonl")
        ok(len(segurados) == 1 and "12 h" in segurados[0]["motivo"], f"fica registrado o que foi segurado: {segurados}")
        p.enviar(LOGIN, texto.replace("oieeee", "oi de novo"), tipo="progresso")
        eq(len(self.enviados), 2, "fala nova sai")

    def t_janela_e_excecoes(self):
        p = self.p
        p.enviar(LOGIN, "⚠️ Instagram pediu login de novo", tipo="urgente")
        reg = p._ler_jsonl(p.AVISOS / f"{LOGIN}.jsonl")
        reg[-1]["em"] = time.time() - 7 * 3600  # sent 7 h ago
        p._gravar_jsonl(p.AVISOS / f"{LOGIN}.jsonl", reg)
        p.enviar(LOGIN, "⚠️ Instagram pediu login de novo", tipo="urgente")
        eq(len(self.enviados), 2, "urgente igual depois de 6 h sai de novo")
        p.enviar(LOGIN, "Pronto, feito.")
        p.enviar(LOGIN, "Pronto, feito.")
        eq(len(self.enviados), 4, "resposta à pessoa nunca é segurada")
        cod = "🔑 *Preciso de um código* — Google\n\nCódigo de verificação\n\nResponda só com o código."
        p.enviar(LOGIN, cod, tipo="urgente", sempre=True)
        p.enviar(LOGIN, cod, tipo="urgente", sempre=True)
        eq(len(self.enviados), 6, "pedido de código sempre sai (sempre=True)")
        b1 = [{"id": "aprov:c:111:aprovar", "titulo": "✅"}]
        b2 = [{"id": "aprov:c:222:aprovar", "titulo": "✅"}]
        p.enviar(LOGIN, "Posso enviar o e-mail?", botoes=b1)
        p.enviar(LOGIN, "Posso enviar o e-mail?", botoes=b2)
        eq(len(self.enviados), 8, "mesmo texto com botões de outro pedido é outro aviso")
        p.enviar(LOGIN, "Posso enviar o e-mail?", botoes=b1)
        eq(len(self.enviados), 8, "o mesmo pedido de novo não")

    def t_registro_quebrado_nao_quebra_o_envio(self):
        p = self.p
        p.AVISOS.mkdir(parents=True, exist_ok=True)
        (p.AVISOS / f"{LOGIN}.jsonl").write_text('{"em": 1, "texto": "a"}\n{"em": 2, "tex', encoding="utf-8")
        eq(p.enviar(LOGIN, "Resumo do dia", tipo="progresso"), "", "envia mesmo com uma linha cortada no registro")
        eq(len(p.avisos_recentes(LOGIN, horas=1)), 1, "e o registro volta a ser lido")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            self._preparar()
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
            finally:
                shutil.rmtree(self._tmp, ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
