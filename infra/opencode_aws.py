"""Fixed HTTPS address for Matheus's OpenCode, on AWS only (24/10, Matheus: "não tem como botar um túnel fixo pelo AWS?").

    phone --HTTPS--> CloudFront (https://dXXXX.cloudfront.net, never changes)
          --HTTP, inside the VPC--> CloudFront VPC origin --> VM private IP :4097
          --> systemd-socket-proxyd (opencodemobile-aws.socket, only on ens5) --> OpenCode 127.0.0.1:4096 (its password)

No public inbound port on the VM: port 4097 is open in the VM's security group only to the security group CloudFront
creates for its VPC origins (CloudFront-VPCOrigins-Service-SG), and the socket listens only on the VPC interface, so the
Docker containers on the VM (Hermes, guests, boxes) cannot reach it either. Caching off, every viewer header (the
OpenCode login travels in Authorization) except Host, all methods, no compression (the event stream /api/event is
SSE; OpenCode sends a heartbeat every 15 s, the origin read timeout is 60 s). No Elastic IP: the VPC origin points at
the instance itself. Cost: CloudFront's always-free tier (1 TB out, 10 M requests a month) covers one person's use;
VPC origins have no charge of their own.

Idempotent (finds everything by name/comment). The address goes to SSM /agentepessoal/opencode/url-aws; the VM's
opencode_tunel.sh publicar prefers it (and keeps the quick tunnel as a fallback) and publishes it to
/agentepessoal/opencode/url, which the control page's "Abrir OpenCode" reads.

Usage, from the repository root:  python3 infra/opencode_aws.py   (also: python3 infra/deploy.py --opencode)
VM side: python3 infra/operador/implantar.py --host opencode_tunel.sh --unidade opencodemobile-aws.socket
"""

import sys
import time

import boto3

REGION = "us-east-1"
NAME = "agentepessoal"
VM_SG = f"{NAME}-vm"
ORIGEM = f"{NAME}-opencode"          # VPC origin name and distribution comment
PORTA = 4097                          # opencodemobile-aws.socket
PARAM_AWS = f"/{NAME}/opencode/url-aws"
SG_CLOUDFRONT = "CloudFront-VPCOrigins-Service-SG"
CACHE_DESLIGADO = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"         # Managed-CachingDisabled
TODOS_MENOS_HOST = "b689b0a8-53d0-40ab-baf2-68738e2966ac"        # Managed-AllViewerExceptHostHeader
METODOS = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]


def log(msg: str) -> None:
    print(f"[opencode-aws] {msg}", flush=True)


def config_origem_vpc(instancia_arn: str) -> dict:
    return {"Name": ORIGEM, "Arn": instancia_arn, "HTTPPort": PORTA, "HTTPSPort": 443,
            "OriginProtocolPolicy": "http-only",
            "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]}}


def config_distribuicao(vpc_origin_id: str, dominio_privado: str, referencia: str) -> dict:
    """The distribution: one origin (the VPC origin), no cache, every method, all viewer headers but Host."""
    return {
        "CallerReference": referencia,
        "Comment": ORIGEM,
        "Enabled": True,
        "PriceClass": "PriceClass_100",
        "HttpVersion": "http2and3",
        "IsIPV6Enabled": True,
        "Origins": {"Quantity": 1, "Items": [{
            "Id": ORIGEM,
            "DomainName": dominio_privado,
            "OriginPath": "",
            "CustomHeaders": {"Quantity": 0},
            "VpcOriginConfig": {"VpcOriginId": vpc_origin_id, "OriginReadTimeout": 60, "OriginKeepaliveTimeout": 60},
            "ConnectionAttempts": 3,
            "ConnectionTimeout": 10,
        }]},
        "DefaultCacheBehavior": {
            "TargetOriginId": ORIGEM,
            "ViewerProtocolPolicy": "redirect-to-https",
            "AllowedMethods": {"Quantity": len(METODOS), "Items": METODOS,
                               "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}},
            "Compress": False,
            "CachePolicyId": CACHE_DESLIGADO,
            "OriginRequestPolicyId": TODOS_MENOS_HOST,
        },
        "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
        "Restrictions": {"GeoRestriction": {"RestrictionType": "none", "Quantity": 0}},
    }


def regra_entrada(sg_cloudfront: str) -> dict:
    """The only inbound rule the VM gets: the OpenCode port, from CloudFront's VPC-origin security group."""
    return {"IpProtocol": "tcp", "FromPort": PORTA, "ToPort": PORTA,
            "UserIdGroupPairs": [{"GroupId": sg_cloudfront, "Description": "CloudFront VPC origin -> OpenCode"}]}


def tem_regra(permissoes: list, sg_cloudfront: str) -> bool:
    return any(p.get("IpProtocol") == "tcp" and p.get("FromPort") == PORTA and p.get("ToPort") == PORTA
               and any(g.get("GroupId") == sg_cloudfront for g in p.get("UserIdGroupPairs", []))
               for p in permissoes)


def instancia(ec2) -> dict:
    r = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [f"{NAME}-agent"]},
                                        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])
    achadas = [i for res in r["Reservations"] for i in res["Instances"]]
    if not achadas:
        raise SystemExit("VM não encontrada (tag Name=agentepessoal-agent)")
    return achadas[0]


def garantir_origem_vpc(cf, instancia_arn: str) -> str:
    for item in cf.list_vpc_origins().get("VpcOriginList", {}).get("Items", []) or []:
        if item["Name"] == ORIGEM:
            vid = item["Id"]
            break
    else:
        vid = cf.create_vpc_origin(VpcOriginEndpointConfig=config_origem_vpc(instancia_arn),
                                   Tags={"Items": [{"Key": "Project", "Value": NAME}]})["VpcOrigin"]["Id"]
        log(f"VPC origin criada: {vid} (leva uns 10-15 min para ficar pronta)")
    for _ in range(120):
        estado = cf.get_vpc_origin(Id=vid)["VpcOrigin"]["Status"]
        if estado == "Deployed":
            return vid
        time.sleep(15)
    raise SystemExit(f"VPC origin {vid} não ficou pronta (estado {estado})")


def garantir_regra(ec2, vpc: str) -> None:
    grupos = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc]},
                                                   {"Name": "group-name", "Values": [VM_SG, SG_CLOUDFRONT]}])["SecurityGroups"]
    por_nome = {g["GroupName"]: g for g in grupos}
    if SG_CLOUDFRONT not in por_nome:
        raise SystemExit(f"{SG_CLOUDFRONT} ainda não existe na VPC {vpc} (a VPC origin cria)")
    vm, cf = por_nome[VM_SG], por_nome[SG_CLOUDFRONT]["GroupId"]
    if tem_regra(vm["IpPermissions"], cf):
        return
    ec2.authorize_security_group_ingress(GroupId=vm["GroupId"], IpPermissions=[regra_entrada(cf)])
    log(f"porta {PORTA} aberta só para {SG_CLOUDFRONT} ({cf})")


def garantir_distribuicao(cf, vid: str, dominio_privado: str) -> str:
    for d in cf.list_distributions().get("DistributionList", {}).get("Items", []) or []:
        if d.get("Comment") == ORIGEM:
            return d["DomainName"]
    d = cf.create_distribution_with_tags(DistributionConfigWithTags={
        "DistributionConfig": config_distribuicao(vid, dominio_privado, f"{ORIGEM}-{int(time.time())}"),
        "Tags": {"Items": [{"Key": "Project", "Value": NAME}]}})["Distribution"]
    log(f"distribuição criada: {d['Id']} {d['DomainName']}")
    return d["DomainName"]


def main() -> None:
    sess = boto3.Session(region_name=REGION)
    ec2, cf, ssm = sess.client("ec2"), sess.client("cloudfront"), sess.client("ssm")
    conta = sess.client("sts").get_caller_identity()["Account"]
    vm = instancia(ec2)
    vid = garantir_origem_vpc(cf, f"arn:aws:ec2:{REGION}:{conta}:instance/{vm['InstanceId']}")
    garantir_regra(ec2, vm["VpcId"])
    url = "https://" + garantir_distribuicao(cf, vid, vm["PrivateDnsName"])
    ssm.put_parameter(Name=PARAM_AWS, Type="String", Overwrite=True, Value=url)
    log(f"endereço fixo: {url} (em {PARAM_AWS}; a VM o publica em /agentepessoal/opencode/url)")


if __name__ == "__main__":
    main()
    sys.exit(0)
