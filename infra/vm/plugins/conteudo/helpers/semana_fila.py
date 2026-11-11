"""Produces one week of posts in the background and hands it to semana.propor (11/11).

    python semana_fila.py <pedido.json>

Started by semana.propor_em_segundo_plano right after the request passed the checks: drawing and judging 4 posts and 7
stories takes longer than one tool call of the agent may last (20 min in the Hermes), so the tool answers at once and
the work happens here. The result is kept in the request file; the notice to Matheus is propor()'s own."""

import importlib.util
import json
import sys
from pathlib import Path


def _semana():
    spec = importlib.util.spec_from_file_location("conteudo_semana_fila", Path(__file__).resolve().parent / "semana.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def produzir(pedido: str, semana=None, **kwargs) -> dict:
    s = semana or _semana()
    arq = Path(pedido)
    d = json.loads(arq.read_text(encoding="utf-8"))
    try:
        r = s.propor(d.get("propostas"), stories=d.get("stories"), **kwargs)
    except Exception as exc:
        r = {"ok": False, "erro": f"a produção da semana quebrou ({type(exc).__name__}: {str(exc)[:200]})"}
    finally:
        s._marca_producao().unlink(missing_ok=True)
    d["resultado"] = r
    arq.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if not r.get("ok"):  # checked a moment ago, so this is rare (the agenda changed meanwhile, a crash): said, not hidden
        s.c()._diario({"semana_em_producao": arq.name, "falhou": str(r.get("erro"))[:300]})
        s._avisar(None, f"⚠️ Conteúdo: a semana pedida pela rotina não foi criada: {str(r.get('erro'))[:200]}")
    return r


if __name__ == "__main__":
    print(json.dumps(produzir(sys.argv[1]), ensure_ascii=False, default=str)[:3000], flush=True)
