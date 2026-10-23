"""Roda rotinas do Hermes UMA vez, à mão, sem ligá-las (migração, fases 5 e 7). Dentro do container do Hermes:
  python3 /opt/data/agentepessoal/rotina_rodar.py <job_id|uuid do A0>... [--todas-ligadas] [--paralelas N]
O "run" do próprio cron (API/CLI) LIGA a rotina pausada (trigger_job: enabled/scheduled); aqui a rodada roda direto
(cron.scheduler.run_job, o mesmo executor do relógio do cron) e o registro da rotina não muda: pausada continua
pausada. O resultado segue o caminho de sempre (rotinas_hermes.py: no ensaio vai para ensaio_celular.jsonl, só o
operador vê) e uma linha por rodada vai para /opt/data/agentepessoal/rodadas_manuais.jsonl."""
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/hermes")
from cron import jobs  # noqa: E402

MAPA = Path("/opt/data/agentepessoal/rotinas.json")
SAIDA = Path("/opt/data/agentepessoal/rodadas_manuais.jsonl")


def alvos(args: list) -> list:
    mapa = json.loads(MAPA.read_text(encoding="utf-8"))
    por_a0 = {v["a0"]: k for k, v in mapa.items()}
    if "--todas-ligadas" in args:
        return [k for k, v in mapa.items() if v.get("ligada_no_a0")]
    return [por_a0.get(a, a) for a in args if not a.startswith("--") and not a.isdigit()]


def rodar(job_id: str) -> dict:
    from cron.scheduler import run_job

    job = jobs.get_job(job_id)
    if not job:
        return {"job": job_id, "erro": "não existe"}
    antes = (job.get("state"), job.get("enabled"))
    inicio = time.time()
    try:
        ok, _doc, final, erro = run_job(dict(job))
    except Exception as exc:
        ok, final, erro = False, "", f"{type(exc).__name__}: {exc}"
    depois = jobs.get_job(job_id) or {}
    linha = {"em": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "job": job_id, "nome": job.get("name"), "ok": ok,
             "segundos": round(time.time() - inicio), "erro": (str(erro)[:500] if erro else None),
             "resposta": (final or "")[:1500], "estado_antes": antes,
             "estado_depois": (depois.get("state"), depois.get("enabled"))}
    with SAIDA.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linha


def main(args: list) -> None:
    n = int(args[args.index("--paralelas") + 1]) if "--paralelas" in args else 1
    lista = alvos(args)
    print("RODANDO", len(lista), flush=True)
    with cf.ThreadPoolExecutor(max(1, n)) as ex:
        for f in cf.as_completed([ex.submit(rodar, j) for j in lista]):
            r = f.result()
            print("RODADA", r.get("nome"), "ok" if r.get("ok") else f"erro: {r.get('erro')}", r.get("segundos"), "s",
                  "pausada continua" if r.get("estado_depois") == r.get("estado_antes") else f"ESTADO MUDOU {r.get('estado_depois')}",
                  flush=True)
    print("FIM", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
