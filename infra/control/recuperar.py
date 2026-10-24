"""VM travada: guarda o que a tela (console) dela mostra e, se o reinício não resolveu, desliga e liga de novo.

Incidente de 23/10 (21:49 UTC): pane do kernel; a VM ficou parada (não religou sozinha) e só o alarme de 5 min a
reiniciou, 10 min depois; o rastro da pane quase se perdeu porque o console é sobrescrito no boot seguinte.

Chamada pelos alarmes do CloudWatch (infra/deploy.py, ensure_recovery), os dois sobre StatusCheckFailed_Instance:
- `agentepessoal-vm-travada` (3 min falhando): o próprio alarme reinicia a VM (ação ec2:reboot) e chama esta função,
  que só GUARDA o console no S3 (incidentes/console-<quando>-guardar.txt) antes que o reinício o apague;
- `agentepessoal-vm-travada-religar` (15 min falhando: o reinício não resolveu): guarda o console, avisa o Matheus no
  Telegram e faz desligar (forçado) + ligar, que leva a VM para outro hospedeiro físico.
- `agentepessoal-vm-sem-rede` (24/10; saída de rede quase zero por 15 min com a VM ligada, que as checagens não pegam:
  23/10 23:22 o kernel travou por dentro, só respondendo ARP): o alarme reinicia a VM e esta função guarda o console e
  avisa o Matheus. Ver `alarmes()`.
Não age se a VM não está "running" (hibernando, desligada pelo Matheus, ligando), se a checagem já voltou a "ok", nem
mais de LIMITE vezes em JANELA (fica para uma pessoa olhar). `{"teste": true}` só guarda o console e diz o que faria."""

import base64
import json
import os
import time
import urllib.request

INSTANCE_ID = os.environ.get("INSTANCE_ID", "")
BUCKET = os.environ.get("BUCKET", "")
PARAM_ESTADO = os.environ.get("PARAM_ESTADO", "/agentepessoal/recuperacao")
WHATSAPP_PARAM = os.environ.get("WHATSAPP_PARAM", "/agentepessoal/whatsapp/config")
ALARME_RELIGAR = "agentepessoal-vm-travada-religar"
ALARME_REINICIAR = "agentepessoal-vm-travada"
ALARME_SEM_REDE = "agentepessoal-vm-sem-rede"
# 24/10: de 22 a 24/10, a cada 5 min a VM saudável mandou >= 300 KB (SSM, túneis, backup); travada, 0 a 4 KB
SEM_REDE_BYTES_5MIN = 50_000
LIMITE, JANELA = 3, 6 * 3600
ESPERA_PARADA = 600  # s até a VM parar depois do desligar forçado


def alarmes(instance_id: str, function_arn: str, region: str = "us-east-1", tags: list | None = None) -> list[dict]:
    """Os alarmes do CloudWatch que chamam esta função (infra/deploy.py, ensure_recovery). Dado ausente = VM desligada
    ou hibernando = normal (notBreaching).
    - travada (checagem da instância falhando 3 min): o alarme reinicia, a função guarda o console;
    - travada-religar (15 min: o reinício não resolveu): a função desliga e liga (outro hospedeiro);
    - sem-rede (24/10): saída de rede < 50 KB em 3 períodos de 5 min seguidos com a VM ligada: o alarme reinicia, a
      função guarda o console e avisa. O vigia da rede de dentro da VM (estabilidade.py rede) age antes, aos 10 min,
      se ele ainda roda; este pega o kernel travado. Só age na troca para ALARM, então não entra em ciclo."""
    base = dict(Namespace="AWS/EC2", Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                TreatMissingData="notBreaching", Tags=tags or [])
    checagem = dict(base, MetricName="StatusCheckFailed_Instance", Statistic="Maximum", Period=60, Threshold=1.0,
                    ComparisonOperator="GreaterThanOrEqualToThreshold")
    return [
        {**checagem, "AlarmName": ALARME_REINICIAR, "EvaluationPeriods": 3, "DatapointsToAlarm": 3,
         "AlarmDescription": "VM do agente travada há 3 min: reinicia e guarda o console (infra/control/recuperar.py)",
         "AlarmActions": [f"arn:aws:automate:{region}:ec2:reboot", function_arn]},
        {**checagem, "AlarmName": ALARME_RELIGAR, "EvaluationPeriods": 15, "DatapointsToAlarm": 15,
         "AlarmDescription": "VM do agente travada há 15 min (o reinício não resolveu): desliga e liga (recuperar.py)",
         "AlarmActions": [function_arn]},
        {**base, "MetricName": "NetworkOut", "Statistic": "Sum", "Period": 300, "Threshold": float(SEM_REDE_BYTES_5MIN),
         "ComparisonOperator": "LessThanThreshold", "AlarmName": ALARME_SEM_REDE, "EvaluationPeriods": 3,
         "DatapointsToAlarm": 3,
         "AlarmDescription": "VM do agente ligada e sem rede há 15 min (checagens ok, kernel travado): reinicia, guarda o "
                             "console e avisa (recuperar.py)",
         "AlarmActions": [f"arn:aws:automate:{region}:ec2:reboot", function_arn]},
    ]


class Recuperar:
    def __init__(self, ec2, s3, ssm, enviar_tg=None, dormir=time.sleep, agora=time.time):
        self.ec2, self.s3, self.ssm = ec2, s3, ssm
        self.enviar_tg = enviar_tg or self._telegram
        self.dormir, self.agora = dormir, agora

    # ------------------------------------------------------------- leitura
    def estado(self) -> str:
        r = self.ec2.describe_instances(InstanceIds=[INSTANCE_ID])
        return r["Reservations"][0]["Instances"][0]["State"]["Name"]

    def checagem(self) -> str:
        r = self.ec2.describe_instance_status(InstanceIds=[INSTANCE_ID], IncludeAllInstances=True)["InstanceStatuses"]
        return r[0]["InstanceStatus"]["Status"] if r else "sem-dados"

    def guardar_console(self, etapa: str) -> str:
        try:
            saida = self.ec2.get_console_output(InstanceId=INSTANCE_ID, Latest=True).get("Output") or ""
        except Exception as exc:  # noqa: BLE001 - sem console não impede religar
            saida = f"(console indisponível: {exc})"
        try:
            texto = base64.b64decode(saida, validate=True).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - o boto3 às vezes já devolve decodificado
            texto = saida
        chave = f"incidentes/console-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(self.agora()))}-{etapa}.txt"
        self.s3.put_object(Bucket=BUCKET, Key=chave, Body=texto.encode("utf-8"))
        return f"s3://{BUCKET}/{chave}"

    def religadas(self) -> list:
        try:
            dados = json.loads(self.ssm.get_parameter(Name=PARAM_ESTADO)["Parameter"]["Value"])
            return [t for t in dados.get("religadas", []) if self.agora() - t < JANELA]
        except Exception:  # noqa: BLE001 - sem registro ainda
            return []

    # ------------------------------------------------------------- ação
    def _telegram(self, texto: str) -> None:
        cfg = json.loads(self.ssm.get_parameter(Name=WHATSAPP_PARAM, WithDecryption=True)["Parameter"]["Value"])
        for chat, login in (cfg.get("tg_chats") or {}).items():
            if login != "matheus":
                continue
            req = urllib.request.Request(f"https://api.telegram.org/bot{cfg['tg_token']}/sendMessage",
                                         data=json.dumps({"chat_id": chat, "text": texto}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()

    def avisar(self, texto: str) -> None:
        try:
            self.enviar_tg(texto)
        except Exception as exc:  # noqa: BLE001 - o aviso não pode impedir religar
            print(f"recuperar: aviso não entregue: {exc}")

    def desligar_e_ligar(self) -> None:
        self.ec2.stop_instances(InstanceIds=[INSTANCE_ID], Force=True)
        inicio = self.agora()
        while self.estado() != "stopped":
            if self.agora() - inicio > ESPERA_PARADA:
                raise RuntimeError("a VM não parou em 10 min")
            self.dormir(10)
        self.ec2.start_instances(InstanceIds=[INSTANCE_ID])

    def __call__(self, event: dict) -> dict:
        dados = event.get("alarmData") or {}
        nome = dados.get("alarmName") or event.get("alarme") or ""
        if dados and (dados.get("state") or {}).get("value") != "ALARM":
            return {"feito": "nada", "motivo": "o alarme não está em ALARM"}
        etapa = {ALARME_RELIGAR: "religar", ALARME_SEM_REDE: "sem-rede"}.get(nome, "guardar")
        estado = self.estado()
        if estado != "running":
            return {"feito": "nada", "motivo": f"a VM está {estado} (hibernando, desligada ou ligando)"}
        console = self.guardar_console(etapa)
        if etapa == "sem-rede":
            self.avisar("⚠️ A máquina do agente ficou ligada mas sem rede por 15 min (travou por dentro). Reiniciei; "
                        "volta em uns 3 min e as mensagens esperam na fila.")
            return {"feito": "console guardado e aviso (o alarme reinicia)", "console": console}
        if etapa == "guardar":
            return {"feito": "console guardado", "console": console}
        checagem = self.checagem()
        if checagem in ("ok", "initializing"):
            return {"feito": "console guardado", "console": console, "motivo": f"a checagem está {checagem}: não religo"}
        feitas = self.religadas()
        if len(feitas) >= LIMITE:
            self.avisar(f"⚠️ A máquina do agente travou de novo ({LIMITE}ª vez em 6 h). Não religuei: precisa de alguém "
                        "olhar (o operador tem o registro).")
            return {"feito": "nada", "console": console, "motivo": f"{LIMITE} religadas em 6 h"}
        if event.get("teste"):
            return {"feito": "teste: religaria", "console": console, "checagem": checagem}
        self.avisar("⚠️ A máquina do agente travou e o reinício não resolveu. Estou desligando e ligando de novo "
                    "(uns 5 min); as mensagens esperam na fila.")
        self.desligar_e_ligar()
        self.ssm.put_parameter(Name=PARAM_ESTADO, Type="String", Overwrite=True,
                               Value=json.dumps({"religadas": feitas + [self.agora()]}))
        return {"feito": "desligada e ligada", "console": console, "checagem": checagem}


def handler(event, _context):
    import boto3

    r = Recuperar(boto3.client("ec2"), boto3.client("s3"), boto3.client("ssm"))(event or {})
    print(json.dumps(r, ensure_ascii=False))
    return r
