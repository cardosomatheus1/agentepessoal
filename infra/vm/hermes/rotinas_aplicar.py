"""As rotinas do agente no cron do Hermes (migração, fase 5): roda DENTRO do container do Hermes, chamado pelo subir.sh
a cada implantação, com o cron dele (cron.jobs: o mesmo armazenamento, com a trava entre processos, que o
`hermes cron` e o cronjob_manage usam). O git é a fonte (infra/vm/hermes/rotinas/<uuid do A0>.json):
- rotina nova: criada PAUSADA ("até a virada as rotinas rodam no A0"); na virada o operador liga as que estavam
  ligadas no A0 (`ligada_no_a0`), nunca as desligadas;
- rotina que já existe: pedido, horário, nome, modelo e portão atualizados; ligada/pausada fica como está;
- o mapa job → rotina do A0 vai para /opt/data/agentepessoal/rotinas.json (rotinas_hermes.py lê para o nome e o id).
Imprime ROTINAS_OK <n criadas> <n atualizadas> <n no total>."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/hermes")
from cron import jobs  # noqa: E402

FONTE = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/data/agentepessoal/rotinas_fonte")
MAPA = Path("/opt/data/agentepessoal/rotinas.json")
PORTAO = Path("/a0/usr/plugins/rotinas/portao.json")
PAUSA = "ensaio: até a virada as rotinas rodam no A0 (docs/MIGRACAO_HERMES.md)"


def portoes() -> set:
    try:
        d = json.loads(PORTAO.read_text(encoding="utf-8"))
        return {k for k, v in d.items() if isinstance(v, dict) and v.get("ligado") is not False and v.get("fontes")}
    except (OSError, ValueError):
        return set()


def main() -> None:
    try:
        mapa = json.loads(MAPA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mapa = {}
    por_a0 = {v.get("a0"): k for k, v in mapa.items() if isinstance(v, dict)}
    existentes = {j["id"]: j for j in jobs.list_jobs(include_disabled=True)}
    com_portao = portoes()
    criadas = atualizadas = 0
    novo_mapa = {}
    for arq in sorted(FONTE.glob("*.json")):
        r = json.loads(arq.read_text(encoding="utf-8"))
        campos = {"prompt": r["pedido"], "schedule": r["agenda"], "name": r["nome"], "model": r.get("modelo"),
                  "provider": "bedrock", "deliver": "local",
                  "script": f"portao_{r['a0']}.py" if r["a0"] in com_portao else None}
        job_id = por_a0.get(r["a0"])
        if job_id in existentes:
            jobs.update_job(job_id, campos)
            atualizadas += 1
        else:
            job = jobs.create_job(**{k: v for k, v in campos.items() if v is not None}, paused=True, paused_reason=PAUSA)
            job_id = job["id"]
            criadas += 1
        novo_mapa[job_id] = {"a0": r["a0"], "nome": r["nome"], "ligada_no_a0": r.get("ligada_no_a0", False),
                             "portao": r["a0"] in com_portao}
    MAPA.parent.mkdir(parents=True, exist_ok=True)
    MAPA.write_text(json.dumps(novo_mapa, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ROTINAS_OK", criadas, atualizadas, len(novo_mapa))


if __name__ == "__main__":
    main()
