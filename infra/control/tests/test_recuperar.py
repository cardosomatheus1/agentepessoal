"""infra/control/recuperar.py (VM travada, 23/10): guarda o console, religa só quando deve. AWS falsa.
Run from the repository root: python3 infra/control/tests/test_recuperar.py"""

import base64
import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


class Ec2Falso:
    def __init__(self, estado="running", checagem="impaired", para_em=2):
        self.estados = [estado]
        self.checagem_ = checagem
        self.chamadas = []
        self.para_em = para_em  # quantas leituras até "stopped" depois do stop

    def describe_instances(self, InstanceIds):
        if self.estados[-1] == "stopping":
            self.para_em -= 1
            if self.para_em <= 0:
                self.estados.append("stopped")
        return {"Reservations": [{"Instances": [{"State": {"Name": self.estados[-1]}}]}]}

    def describe_instance_status(self, InstanceIds, IncludeAllInstances):
        return {"InstanceStatuses": [{"InstanceStatus": {"Status": self.checagem_}}]}

    def get_console_output(self, InstanceId, Latest):
        self.chamadas.append("console")
        return {"Output": base64.b64encode(b"Kernel panic - not syncing: Oops: Fatal exception").decode()}

    def stop_instances(self, InstanceIds, Force):
        self.chamadas.append(f"stop force={Force}")
        self.estados.append("stopping")

    def start_instances(self, InstanceIds):
        self.chamadas.append("start")
        self.estados.append("pending")


class S3Falso:
    def __init__(self):
        self.objetos = {}

    def put_object(self, Bucket, Key, Body):
        self.objetos[Key] = Body


class SsmFalso:
    def __init__(self, religadas=None):
        self.valor = json.dumps({"religadas": religadas}) if religadas is not None else None

    def get_parameter(self, Name, WithDecryption=False):
        if self.valor is None:
            raise KeyError(Name)
        return {"Parameter": {"Value": self.valor}}

    def put_parameter(self, Name, Type, Overwrite, Value):
        self.valor = Value


def alarme(nome, valor="ALARM"):
    return {"alarmData": {"alarmName": nome, "state": {"value": valor}}}


def main() -> int:
    spec = importlib.util.spec_from_file_location("recuperar_teste", RAIZ / "infra" / "control" / "recuperar.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.BUCKET, m.INSTANCE_ID = "balde", "i-1"
    falhas = []

    def checa(ok, msg):
        if not ok:
            falhas.append(msg)

    def novo(ec2=None, ssm=None, agora=1000.0):
        avisos = []
        rel = m.Recuperar(ec2 or Ec2Falso(), S3Falso(), ssm or SsmFalso(), enviar_tg=avisos.append,
                          dormir=lambda s: None, agora=lambda: agora)
        return rel, avisos

    # 1º alarme (3 min): só guarda o console (o reinício é a ação do próprio alarme)
    rel, avisos = novo()
    r = rel(alarme("agentepessoal-vm-travada"))
    checa(r["feito"] == "console guardado" and rel.ec2.chamadas == ["console"] and not avisos, f"guardar: {r} {rel.ec2.chamadas}")
    texto = list(rel.s3.objetos.values())[0].decode()
    checa("Kernel panic" in texto and list(rel.s3.objetos)[0].startswith("incidentes/console-"), f"console no S3: {rel.s3.objetos}")

    # 2º alarme (15 min): guarda, avisa, desliga forçado, espera parar, liga, registra
    rel, avisos = novo()
    r = rel(alarme(m.ALARME_RELIGAR))
    checa(r["feito"] == "desligada e ligada", f"religar: {r}")
    checa(rel.ec2.chamadas == ["console", "stop force=True", "start"], f"ordem: {rel.ec2.chamadas}")
    checa(len(avisos) == 1 and "desligando e ligando" in avisos[0], f"aviso: {avisos}")
    checa(json.loads(rel.ssm.valor)["religadas"] == [1000.0], f"registro: {rel.ssm.valor}")

    # não age: VM hibernando/desligada, checagem já ok, alarme voltando a OK
    for estado in ("stopping", "stopped", "pending"):
        rel, avisos = novo(ec2=Ec2Falso(estado=estado))
        r = rel(alarme(m.ALARME_RELIGAR))
        checa(r["feito"] == "nada" and rel.ec2.chamadas == [] and not avisos, f"{estado}: {r}")
    rel, avisos = novo(ec2=Ec2Falso(checagem="ok"))
    r = rel(alarme(m.ALARME_RELIGAR))
    checa("stop force=True" not in rel.ec2.chamadas and not avisos and "não religo" in r["motivo"], f"checagem ok: {r}")
    rel, _ = novo()
    checa(rel(alarme(m.ALARME_RELIGAR, "OK"))["feito"] == "nada" and rel.ec2.chamadas == [], "alarme em OK")

    # limite: 3 religadas em 6 h → não religa, avisa que precisa de alguém; religadas antigas não contam
    rel, avisos = novo(ssm=SsmFalso([100.0, 200.0, 300.0]))
    r = rel(alarme(m.ALARME_RELIGAR))
    checa(r["feito"] == "nada" and "stop force=True" not in rel.ec2.chamadas and "precisa de alguém" in avisos[0], f"limite: {r}")
    rel, _ = novo(ssm=SsmFalso([1.0, 2.0, 3.0]), agora=1.0 + 7 * 3600)
    checa(rel(alarme(m.ALARME_RELIGAR))["feito"] == "desligada e ligada", "religadas de 7 h atrás não contam")

    # teste: guarda e diz o que faria, sem desligar
    rel, avisos = novo()
    r = rel({"alarme": m.ALARME_RELIGAR, "teste": True})
    checa(r["feito"] == "teste: religaria" and "stop force=True" not in rel.ec2.chamadas and not avisos, f"teste: {r}")

    # a VM não para: erro (a função falha e o log mostra), nunca liga por cima
    ec2 = Ec2Falso(para_em=10**9)
    rel = m.Recuperar(ec2, S3Falso(), SsmFalso(), enviar_tg=lambda t: None, dormir=lambda s: None,
                      agora=iter(range(0, 10**6, 100)).__next__)
    try:
        rel(alarme(m.ALARME_RELIGAR))
        falhas.append("a VM que não para devia dar erro")
    except RuntimeError:
        checa("start" not in ec2.chamadas, "não liga se não parou")

    # aviso que falha não impede religar
    rel = m.Recuperar(Ec2Falso(), S3Falso(), SsmFalso(), enviar_tg=lambda t: 1 / 0, dormir=lambda s: None, agora=lambda: 5.0)
    checa(rel(alarme(m.ALARME_RELIGAR))["feito"] == "desligada e ligada", "aviso com erro não impede religar")

    # 24/10: VM ligada e sem rede (alarme sobre NetworkOut): guarda o console, avisa, não desliga (o alarme reinicia)
    rel, avisos = novo(ec2=Ec2Falso(checagem="ok"))
    r = rel(alarme(m.ALARME_SEM_REDE))
    checa(rel.ec2.chamadas == ["console"] and len(avisos) == 1 and "sem rede" in avisos[0], f"sem-rede: {r} {avisos}")
    checa(list(rel.s3.objetos)[0].endswith("-sem-rede.txt"), f"sem-rede: console com a etapa: {rel.s3.objetos}")
    rel, avisos = novo(ec2=Ec2Falso(estado="stopped"))
    checa(rel(alarme(m.ALARME_SEM_REDE))["feito"] == "nada" and not avisos, "sem-rede com a VM desligada: nada")

    # os alarmes: os dois da checagem e o da rede (saída < 50 KB em 3 x 5 min; dado ausente = desligada = normal)
    al = {a["AlarmName"]: a for a in m.alarmes("i-1", "arn:fn")}
    checa(set(al) == {m.ALARME_REINICIAR, m.ALARME_RELIGAR, m.ALARME_SEM_REDE}, f"alarmes: {list(al)}")
    sr = al[m.ALARME_SEM_REDE]
    checa(sr["MetricName"] == "NetworkOut" and sr["Statistic"] == "Sum" and sr["Period"] == 300
          and sr["EvaluationPeriods"] == 3 and sr["DatapointsToAlarm"] == 3 and sr["ComparisonOperator"] == "LessThanThreshold"
          and sr["Threshold"] == 50000.0 and sr["TreatMissingData"] == "notBreaching", f"alarme sem rede: {sr}")
    checa(sr["AlarmActions"] == ["arn:aws:automate:us-east-1:ec2:reboot", "arn:fn"], f"sem rede reinicia e chama: {sr}")
    checa(al[m.ALARME_RELIGAR]["AlarmActions"] == ["arn:fn"] and al[m.ALARME_REINICIAR]["EvaluationPeriods"] == 3,
          "alarmes da checagem como antes")
    # 23/10 23:22-23:40: saída de 3,1 a 3,9 KB por 5 min (travada) dispara; o menor valor saudável de 22-24/10 não
    checa(3876 < sr["Threshold"] < 300421, "limiar entre o travado e o saudável medidos")

    print(f"TESTES {'ok' if not falhas else 'FALHOU'}")
    for f in falhas:
        print("  ✗", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
