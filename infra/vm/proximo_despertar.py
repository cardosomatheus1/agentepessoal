"""Wake the VM exactly for the agent's next scheduled task (instead of fixed times).

  proximo_despertar.py            schedule a one-shot EventBridge start 5 min before the next
                                  task run (or remove it when nothing is scheduled); run by
                                  hibernate.sh right before the VM stops
  proximo_despertar.py --perto N  exit 3 when a task runs within N minutes (the idle watchdog
                                  then does not hibernate)

Reads Agent Zero's /opt/a0/usr/scheduler/tasks.json: "scheduled" tasks (cron fields + timezone)
and "planned" tasks (a list of datetimes still to run).
"""

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from croniter import croniter

TAREFAS = Path("/opt/a0/usr/scheduler/tasks.json")
REGION = "us-east-1"
NOME = "agentepessoal-acordar-tarefa"
ANTES = dt.timedelta(minutes=5)


def proximas(agora: dt.datetime) -> list[tuple[dt.datetime, str]]:
    try:
        tarefas = json.loads(TAREFAS.read_text()).get("tasks", [])
    except Exception:
        return []
    saida = []
    for t in tarefas:
        if t.get("state") == "disabled":
            continue
        nome = t.get("name", "")
        if t.get("type") == "scheduled" and t.get("schedule"):
            s = t["schedule"]
            try:
                fuso = ZoneInfo(s.get("timezone") or "UTC")
                expr = " ".join(str(s.get(k, "*")) for k in ("minute", "hour", "day", "month", "weekday"))
                prox = croniter(expr, agora.astimezone(fuso)).get_next(dt.datetime)
                saida.append((prox.astimezone(dt.timezone.utc), nome))
            except Exception:
                continue
        elif t.get("type") == "planned":
            for quando in (t.get("plan") or {}).get("todo", []):
                try:
                    d = dt.datetime.fromisoformat(str(quando))
                    d = d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
                    if d > agora:
                        saida.append((d.astimezone(dt.timezone.utc), nome))
                except ValueError:
                    continue
    return sorted(saida)


def instancia() -> str:
    import urllib.request

    token = urllib.request.urlopen(urllib.request.Request(
        "http://169.254.169.254/latest/api/token", method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"}), timeout=3).read().decode()
    return urllib.request.urlopen(urllib.request.Request(
        "http://169.254.169.254/latest/meta-data/instance-id",
        headers={"X-aws-ec2-metadata-token": token}), timeout=3).read().decode()


def agendar(agora: dt.datetime) -> None:
    scheduler = boto3.client("scheduler", region_name=REGION)
    lista = proximas(agora)
    if not lista:
        try:
            scheduler.delete_schedule(Name=NOME)
        except scheduler.exceptions.ResourceNotFoundException:
            pass
        print("nenhuma tarefa agendada: nada vai acordar a VM")
        return
    quando, nome = lista[0]
    acordar = max(quando - ANTES, agora + dt.timedelta(minutes=2))
    conta = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    args = dict(
        Name=NOME, ScheduleExpression=f"at({acordar.strftime('%Y-%m-%dT%H:%M:%S')})",
        ScheduleExpressionTimezone="UTC", FlexibleTimeWindow={"Mode": "OFF"}, ActionAfterCompletion="DELETE",
        Target={"Arn": "arn:aws:scheduler:::aws-sdk:ec2:startInstances",
                "RoleArn": f"arn:aws:iam::{conta}:role/agentepessoal-acordar-vm",
                "Input": json.dumps({"InstanceIds": [instancia()]})},
    )
    try:
        scheduler.create_schedule(**args)
    except scheduler.exceptions.ConflictException:
        scheduler.update_schedule(**args)
    print(f"VM acorda em {acordar.isoformat()} para «{nome}» ({quando.isoformat()})")


def main() -> int:
    agora = dt.datetime.now(dt.timezone.utc)
    if len(sys.argv) > 2 and sys.argv[1] == "--perto":
        lista = proximas(agora)
        perto = bool(lista) and lista[0][0] - agora <= dt.timedelta(minutes=float(sys.argv[2]))
        return 3 if perto else 0
    agendar(agora)
    return 0


if __name__ == "__main__":
    sys.exit(main())
