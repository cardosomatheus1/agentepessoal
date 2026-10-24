"""Endereço fixo do OpenCode pela AWS (24/10): infra/opencode_aws.py (CloudFront + VPC origin, só o grupo da CloudFront
entra na porta 4097), as unidades opencodemobile-aws.socket/.service e implantar.py levando a .service junto da .socket.
Sem AWS de verdade: clientes falsos. Run from the repository root: python3 infra/vm/tests/test_opencode_aws.py"""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def carregar(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class CloudFrontFalso:
    def __init__(self):
        self.origens, self.distribuicoes, self.criadas = [], [], []

    def list_vpc_origins(self):
        return {"VpcOriginList": {"Items": self.origens}}

    def create_vpc_origin(self, VpcOriginEndpointConfig, Tags):
        self.criadas.append(("origem", VpcOriginEndpointConfig))
        self.origens.append({"Id": "vo_1", "Name": VpcOriginEndpointConfig["Name"]})
        return {"VpcOrigin": {"Id": "vo_1"}}

    def get_vpc_origin(self, Id):
        return {"VpcOrigin": {"Status": "Deployed"}}

    def list_distributions(self):
        return {"DistributionList": {"Items": self.distribuicoes}}

    def create_distribution_with_tags(self, DistributionConfigWithTags):
        cfg = DistributionConfigWithTags["DistributionConfig"]
        self.criadas.append(("distribuicao", cfg))
        self.distribuicoes.append({"Id": "E1", "DomainName": "d1abc.cloudfront.net", "Comment": cfg["Comment"]})
        return {"Distribution": {"Id": "E1", "DomainName": "d1abc.cloudfront.net"}}


class Ec2Falso:
    def __init__(self):
        self.vm = {"GroupName": "agentepessoal-vm", "GroupId": "sg-vm", "IpPermissions": []}
        self.autorizadas = []

    def describe_security_groups(self, Filters):
        return {"SecurityGroups": [self.vm, {"GroupName": "CloudFront-VPCOrigins-Service-SG", "GroupId": "sg-cf",
                                             "IpPermissions": []}]}

    def authorize_security_group_ingress(self, GroupId, IpPermissions):
        self.autorizadas.append((GroupId, IpPermissions))
        self.vm["IpPermissions"] += IpPermissions


def main() -> int:
    falhas = []

    def checa(ok, msg):
        if not ok:
            falhas.append(msg)

    oa = carregar("opencode_aws_teste", RAIZ / "infra" / "opencode_aws.py")

    # distribuição: sem cache, todos os cabeçalhos menos Host (a senha vai no Authorization), todos os métodos, sem
    # compressão (SSE), só HTTPS para o celular, origem = VPC origin com 60 s de leitura (o SSE bate a cada 15 s)
    d = oa.config_distribuicao("vo_1", "ip-172-31-10-115.ec2.internal", "ref")
    c = d["DefaultCacheBehavior"]
    checa(c["CachePolicyId"] == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad", "Managed-CachingDisabled")
    checa(c["OriginRequestPolicyId"] == "b689b0a8-53d0-40ab-baf2-68738e2966ac", "Managed-AllViewerExceptHostHeader")
    checa(set(c["AllowedMethods"]["Items"]) == {"GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"}, "métodos")
    checa(c["Compress"] is False and c["ViewerProtocolPolicy"] == "redirect-to-https", "sem compressão, só https")
    o = d["Origins"]["Items"][0]
    checa(o["VpcOriginConfig"]["VpcOriginId"] == "vo_1" and o["VpcOriginConfig"]["OriginReadTimeout"] == 60, f"origem {o}")
    checa("CustomOriginConfig" not in o and o["DomainName"].endswith(".ec2.internal"), "origem privada, não pública")
    ov = oa.config_origem_vpc("arn:aws:ec2:us-east-1:1:instance/i-1")
    checa(ov["HTTPPort"] == 4097 and ov["OriginProtocolPolicy"] == "http-only", f"VPC origin na 4097: {ov}")

    # regra de entrada: só o grupo da VPC origin da CloudFront, nunca um bloco de IPs
    r = oa.regra_entrada("sg-cf")
    checa(r["FromPort"] == r["ToPort"] == 4097 and "IpRanges" not in r and r["UserIdGroupPairs"][0]["GroupId"] == "sg-cf",
          f"regra {r}")
    import re
    checa(re.fullmatch(r"[a-zA-Z0-9. _\-:/()#,@\[\]+=&;{}!$*]{1,255}", r["UserIdGroupPairs"][0]["Description"]),
          "descrição só com os caracteres que a EC2 aceita (24/10: '->' deu InvalidParameterValue)")

    # idempotente: a 2ª rodada não cria nada de novo nem abre a porta de novo
    cf, ec2 = CloudFrontFalso(), Ec2Falso()
    for _ in range(2):
        vid = oa.garantir_origem_vpc(cf, "arn:aws:ec2:us-east-1:1:instance/i-1")
        oa.garantir_regra(ec2, "vpc-1")
        dom = oa.garantir_distribuicao(cf, vid, "ip-1.ec2.internal")
    checa(len(cf.criadas) == 2 and dom == "d1abc.cloudfront.net", f"criou só uma vez: {cf.criadas}")
    checa(len(ec2.autorizadas) == 1 and ec2.autorizadas[0][0] == "sg-vm", f"porta aberta uma vez: {ec2.autorizadas}")

    # unidades: a porta só na interface da VPC (os containers do Docker não entram), repasse para 127.0.0.1:4096
    sock = (RAIZ / "infra/vm/unidades/opencodemobile-aws.socket").read_text()
    serv = (RAIZ / "infra/vm/unidades/opencodemobile-aws.service").read_text()
    checa(f"ListenStream={oa.PORTA}\n" in sock and "BindToDevice=ens5" in sock, "socket na 4097, só ens5")
    checa("systemd-socket-proxyd" in serv and "127.0.0.1:4096" in serv and "DynamicUser=yes" in serv, "repasse sem privilégio")

    # implantar.py --unidade X.socket leva X.service junto (como a .timer)
    imp = carregar("implantar_teste_oc", RAIZ / "infra" / "operador" / "implantar.py")
    checa(imp.unidades_de("opencodemobile-aws.socket") == ["opencodemobile-aws.socket", "opencodemobile-aws.service"], "socket")
    checa(imp.unidades_de("a.timer") == ["a.timer", "a.service"] and imp.unidades_de("b.service") == ["b.service"]
          and imp.unidades_de("") == [], "timer/service/vazio")

    print(f"TESTES {'ok' if not falhas else 'FALHOU'}")
    for f in falhas:
        print("  ✗", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
