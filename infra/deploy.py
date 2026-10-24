"""Create (or update) the on-demand agent + phone VM and its control page on AWS.

Idempotent: re-running reuses existing resources (found by name/tag).
Usage:  python infra/deploy.py            create / update cloud resources
        python infra/deploy.py --update   also push vm/ changes to the running VM (re-runs setup.sh)
        python infra/deploy.py --recuperacao   only the stuck-VM alarms and their function (infra/control/recuperar.py)
        python infra/deploy.py --controle-iam  only the control function's permissions
"""

import gzip
import hashlib
import io
import json
import sys
import tarfile
import secrets
import string
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
NAME = "agentepessoal"
# Graviton (ARM): Android apps run natively in the redroid container. Hibernation needs
# Ubuntu 22.04 on Graviton and a root disk larger than RAM. m8g (Graviton4, 4 vCPU, 16 GB)
# measured ~2x faster than t4g.xlarge on page capture and CPU work, for ~+34% per hour.
INSTANCE_TYPE = "m8g.xlarge"
DISK_GB = 80
AMI_PARAM = "/aws/service/canonical/ubuntu/server/22.04/stable/current/arm64/hvm/ebs-gp2/ami-id"
IDLE_MINUTES = 30  # only used with HIBERNAR=1
# 24/10 (Matheus: reliability over cost): the VM stays on. Idle hibernation only when this is "1" (written to
# /etc/agentepessoal.env); a resume on 24/10 left the network card dead. Always on costs ~US$ 25/month more.
HIBERNAR = "0"
IMAGE = "agent0ai/agent-zero:v2.13"
PARAM_PASSWORD = f"/{NAME}/password"
PARAM_URL = f"/{NAME}/agent-url"
PARAM_PHONE = f"/{NAME}/phone-url"
VM_ROLE = f"{NAME}-vm"
META_ROLE = f"{NAME}-segredo-meta"
VOZ_ROLE = f"{NAME}-voz"
CONTROL_ROLE = f"{NAME}-control"
FUNCTION = f"{NAME}-control"
WAKE_ROLE = f"{NAME}-acordar-vm"
WAKE_LATER = f"{NAME}-acordar-depois"
WHATSAPP_QUEUE = f"{NAME}-whatsapp"
PARAM_WHATSAPP = f"/{NAME}/whatsapp/config"
PARAM_OPENCODE = f"/{NAME}/opencode/url"

HERE = Path(__file__).parent
ROOT = HERE.parent
TAGS = [{"Key": "Project", "Value": NAME}]

session = boto3.Session(region_name=REGION)
ec2 = session.client("ec2")
iam = session.client("iam")
ssm = session.client("ssm")
lam = session.client("lambda")
s3 = session.client("s3")
sqs = session.client("sqs")
account = session.client("sts").get_caller_identity()["Account"]
BUCKET = f"{NAME}-backup-{account}"


def log(msg: str) -> None:
    print(f"[deploy] {msg}", flush=True)


# ---------------------------------------------------------------- parameters

def ensure_parameters() -> tuple[str, bool]:
    try:
        password = ssm.get_parameter(Name=PARAM_PASSWORD, WithDecryption=True)["Parameter"]["Value"]
        created = False
    except ssm.exceptions.ParameterNotFound:
        alphabet = string.ascii_letters + string.digits
        password = "".join(secrets.choice(alphabet) for _ in range(20))
        ssm.put_parameter(Name=PARAM_PASSWORD, Value=password, Type="SecureString", Tags=TAGS)
        created = True
        log("created password parameter")
    for name in (PARAM_URL, PARAM_PHONE):
        try:
            ssm.get_parameter(Name=name)
        except ssm.exceptions.ParameterNotFound:
            ssm.put_parameter(Name=name, Value="stopped", Type="String", Tags=TAGS)
    return password, created


# ---------------------------------------------------------------- backups

def ensure_bucket() -> None:
    try:
        s3.head_bucket(Bucket=BUCKET)
        return
    except ClientError:
        pass
    s3.create_bucket(Bucket=BUCKET)
    s3.put_public_access_block(
        Bucket=BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
    s3.put_bucket_encryption(
        Bucket=BUCKET,
        ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
    )
    # Keep 30 days of older versions so a bad sync can be rolled back.
    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET,
        LifecycleConfiguration={"Rules": [{
            "ID": "expire-old-versions", "Status": "Enabled", "Filter": {"Prefix": ""},
            "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
        }]},
    )
    s3.put_bucket_tagging(Bucket=BUCKET, Tagging={"TagSet": TAGS})
    log(f"created private versioned bucket {BUCKET}")


# ---------------------------------------------------------------------- IAM

def ensure_role(name: str, service: str, managed: list[str], inline: dict) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}],
    }
    try:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Tags=TAGS)["Role"]["Arn"]
        log(f"created role {name}")
    for policy in managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=policy)
    iam.put_role_policy(RoleName=name, PolicyName=f"{name}-inline", PolicyDocument=json.dumps(inline))
    return arn


def ensure_vm_role() -> str:
    params = f"arn:aws:ssm:{REGION}:{account}:parameter/{NAME}/*"
    ensure_role(
        VM_ROLE,
        "ec2.amazonaws.com",
        ["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"],
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["bedrock:*", "bedrock-mantle:*"], "Resource": "*"},
                # web search/fetch for the GPT models (plugins/pesquisa): SearXNG engines block AWS addresses.
                # ExternalWebAccess: fetch reads the live page (default); without it every fetch is a 401.
                {"Effect": "Allow", "Action": ["bedrock-websearch:InvokeSearch", "bedrock-websearch:InvokeFetch",
                                               "bedrock-websearch:ExternalWebAccess"], "Resource": "*"},
                # voice notes (plugins/auxiliar: the morning summary as audio), through the proxy's /arquivos/voz
                {"Effect": "Allow", "Action": "polly:SynthesizeSpeech", "Resource": "*"},
                {   # third-party Bedrock models (TwelveLabs Pegasus for plugins/video) subscribe on first use
                    "Effect": "Allow",
                    "Action": ["aws-marketplace:ViewSubscriptions", "aws-marketplace:Subscribe"],
                    "Resource": "*",
                    "Condition": {"StringEquals": {"aws:CalledViaLast": "bedrock.amazonaws.com"}},
                },
                {"Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:PutParameter"], "Resource": params},
                {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{BUCKET}"},
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                    "Resource": f"arn:aws:s3:::{BUCKET}/*",
                },
                {   # SecureString parameters (ponte_whatsapp saves the WhatsApp token)
                    "Effect": "Allow",
                    "Action": ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
                    "Resource": "*",
                    "Condition": {"StringEquals": {"kms:ViaService": f"ssm.{REGION}.amazonaws.com"}},
                },
                {   # ponte_whatsapp reads what the control function queued
                    "Effect": "Allow",
                    "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"],
                    "Resource": f"arn:aws:sqs:{REGION}:{account}:{WHATSAPP_QUEUE}",
                },
                {   # proximo_despertar.py: wake exactly for the next scheduled task
                    "Effect": "Allow",
                    "Action": ["scheduler:CreateSchedule", "scheduler:UpdateSchedule", "scheduler:DeleteSchedule"],
                    "Resource": f"arn:aws:scheduler:{REGION}:{account}:schedule/default/{NAME}-acordar-tarefa",
                },
                {"Effect": "Allow", "Action": "iam:PassRole", "Resource": f"arn:aws:iam::{account}:role/{WAKE_ROLE}"},
                {   # the idle watchdog hibernates its own instance
                    "Effect": "Allow",
                    "Action": "ec2:StopInstances",
                    "Resource": f"arn:aws:ec2:{REGION}:{account}:instance/*",
                    "Condition": {"StringEquals": {"aws:ResourceTag/Project": NAME}},
                },
            ],
        },
    )
    # credenciais_meta.py hands the agent short-lived credentials of META_ROLE (and of VOZ_ROLE, for the narration)
    iam.put_role_policy(RoleName=VM_ROLE, PolicyName=f"{VM_ROLE}-segredo-meta", PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Resource": [f"arn:aws:iam::{account}:role/{META_ROLE}", f"arn:aws:iam::{account}:role/{VOZ_ROLE}"]}],
    }))
    try:
        iam.get_instance_profile(InstanceProfileName=VM_ROLE)
    except iam.exceptions.NoSuchEntityException:
        iam.create_instance_profile(InstanceProfileName=VM_ROLE, Tags=TAGS)
        log("created instance profile")
    profile = iam.get_instance_profile(InstanceProfileName=VM_ROLE)["InstanceProfile"]
    if not profile["Roles"]:
        iam.add_role_to_instance_profile(InstanceProfileName=VM_ROLE, RoleName=VM_ROLE)
        log("waiting for instance profile to propagate")
        time.sleep(15)
    return profile["Arn"]


def ensure_voice_role() -> None:
    """Only the narration of the video templates (infra/reels/moldes, rendered by the agent since 22/10): Nova 2
    Sonic in Bedrock and Polly. Assumed by the VM for the agent (credenciais_meta.py, path /voz)."""
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{account}:role/{VM_ROLE}"}, "Action": "sts:AssumeRole"}]}
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["bedrock:InvokeModelWithBidirectionalStream", "bedrock:InvokeModel"],
         "Resource": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.nova-2-sonic-v1:0"},
        {"Effect": "Allow", "Action": "polly:SynthesizeSpeech", "Resource": "*"},
    ]}
    try:
        iam.get_role(RoleName=VOZ_ROLE)
        iam.update_assume_role_policy(RoleName=VOZ_ROLE, PolicyDocument=json.dumps(trust))
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=VOZ_ROLE, AssumeRolePolicyDocument=json.dumps(trust), MaxSessionDuration=3600, Tags=TAGS)
        log(f"created role {VOZ_ROLE}")
    iam.put_role_policy(RoleName=VOZ_ROLE, PolicyName="voz", PolicyDocument=json.dumps(policy))


def ensure_meta_secret_role() -> None:
    """Only what `pnpm --filter @ros/infra-aws segredo-meta` (NEXOS repo) needs: the Meta app,
    Meta sandbox, Meta webhook and WhatsApp webhook secrets, and a restart of api/worker. Assumed by the VM
    for the agent (credenciais_meta.py)."""
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{account}:role/{VM_ROLE}"}, "Action": "sts:AssumeRole"}]}
    services = [f"arn:aws:ecs:{REGION}:{account}:service/ros-dev-cluster/ros-dev-{s}" for s in ("api", "worker")]
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow",
         "Resource": [f"arn:aws:secretsmanager:{REGION}:{account}:secret:{s}-*"
                      for s in ("ros-dev-meta/app", "ros-dev-meta/sandbox", "ros-dev-meta/webhook", "ros-dev-whatsapp/webhook")],
         "Action": ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"]},
        {"Effect": "Allow", "Action": ["ecs:UpdateService", "ecs:DescribeServices"], "Resource": services},
        {"Effect": "Allow", "Action": "ecs:ListServices", "Resource": "*",
         "Condition": {"ArnEquals": {"ecs:cluster": f"arn:aws:ecs:{REGION}:{account}:cluster/ros-dev-cluster"}}},
    ]}
    try:
        iam.get_role(RoleName=META_ROLE)
        iam.update_assume_role_policy(RoleName=META_ROLE, PolicyDocument=json.dumps(trust))
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=META_ROLE, AssumeRolePolicyDocument=json.dumps(trust), MaxSessionDuration=3600, Tags=TAGS)
        log(f"created role {META_ROLE}")
    iam.put_role_policy(RoleName=META_ROLE, PolicyName="segredo-meta", PolicyDocument=json.dumps(policy))


# ---------------------------------------------------------------- network

def default_subnet_and_vpc() -> tuple[str, str]:
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise SystemExit("No default VPC in us-east-1; create one or pick a public subnet.")
    vpc = vpcs[0]["VpcId"]
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "vpc-id", "Values": [vpc]}, {"Name": "default-for-az", "Values": ["true"]}]
    )["Subnets"]
    # Not every instance type is offered in every AZ; keep the ones that have it.
    offered = {
        o["Location"]
        for o in ec2.describe_instance_type_offerings(
            LocationType="availability-zone",
            Filters=[{"Name": "instance-type", "Values": [INSTANCE_TYPE]}],
        )["InstanceTypeOfferings"]
    }
    subnets = sorted((s for s in subnets if s["AvailabilityZone"] in offered), key=lambda s: s["AvailabilityZone"])
    return subnets[0]["SubnetId"], vpc


def ensure_security_group(vpc: str) -> str:
    found = ec2.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [f"{NAME}-vm"]}, {"Name": "vpc-id", "Values": [vpc]}]
    )["SecurityGroups"]
    if found:
        return found[0]["GroupId"]
    sg = ec2.create_security_group(
        GroupName=f"{NAME}-vm",
        Description="agentepessoal VM: no inbound; access via Cloudflare tunnel and SSM",
        VpcId=vpc,
        TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}],
    )["GroupId"]
    log(f"created security group {sg} (no inbound rules)")
    return sg


# ---------------------------------------------------------------- instance

def presets_yaml() -> str:
    base = "http://host.docker.internal:8787/openai/v1"
    kwargs = "      a0_api_mode: responses\n      responses_state: local\n"

    def model(slot: str, name: str, extra: str, effort: str = "") -> str:
        return (
            f"  {slot}:\n    provider: other\n    name: {name}\n    api_base: {base}\n"
            f"    ctx_length: 200000\n{extra}    rl_requests: 0\n    rl_input: 0\n    rl_output: 0\n"
            f"    kwargs:\n{kwargs}" + (f"      reasoning_effort: {effort}\n" if effort else "")
        )

    def claude(slot: str, name: str, extra: str, effort: str = "") -> str:
        # Claude runs on the Bedrock runtime (Converse API) behind the proxy's /bedrock route; the
        # proxy swaps the placeholder key for a fresh bearer token
        return (
            f"  {slot}:\n    provider: bedrock\n    name: converse/{name}\n"
            f"    ctx_length: 200000\n{extra}    rl_requests: 0\n    rl_input: 0\n    rl_output: 0\n"
            "    kwargs:\n      a0_api_mode: chat\n      api_base: http://host.docker.internal:8787/bedrock\n"
            "      api_key: proxy\n      aws_region_name: us-east-1\n      max_tokens: 32000\n"
            + (f"      output_config:\n        effort: {effort}\n" if effort else "")
        )

    haiku = "us.anthropic.claude-haiku-5-5"
    # ctx_history 0.25: the history is summarized past ~50k tokens instead of ~140k (every step
    # resends it). max_embeds 30: images kept in context; at 10 a 7+5 image comparison looped forever
    chat_extra = "    ctx_history: 0.25\n    vision: true\n    max_embeds: 30\n"
    util_extra = "    ctx_input: 0.7\n"
    embedding = (
        "  embedding:\n    provider: huggingface\n    name: sentence-transformers/all-MiniLM-L6-v2\n"
        "    api_base: ''\n    rl_requests: 0\n    rl_input: 0\n    kwargs: {}\n"
    )
    return (
        "- name: Default\n"  # GPT-6 Luna at its default (medium) effort: in the model tests it was as accurate as Sol and faster
        + model("chat", "openai.gpt-6-luna", chat_extra)
        + model("utility", "openai.gpt-6-luna", util_extra)
        + embedding
        + "- name: Sol\n"
        + model("chat", "openai.gpt-6.1-sol", chat_extra)
        + model("utility", "openai.gpt-6-luna", util_extra)
        + "- name: Luna alto\n"
        + model("chat", "openai.gpt-6-luna", chat_extra, effort="high")
        + model("utility", "openai.gpt-6-luna", util_extra)
        + "- name: Luna max\n"
        + model("chat", "openai.gpt-6-luna", chat_extra, effort="max")
        + model("utility", "openai.gpt-6-luna", util_extra)
        + "- name: Haiku alto\n"
        + claude("chat", haiku, chat_extra, effort="high")
        + claude("utility", haiku, util_extra)
    )


def bundle() -> bytes:
    """vm/ plus generated config, uploaded to S3 and unpacked by the VM."""
    code_exec = json.loads((ROOT / "config/code_execution.json").read_text())
    code_exec["ssh_enabled"] = "auto"  # inside the Docker image this resolves to local shell
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        src = HERE / "vm"
        for path in sorted(src.rglob("*")):
            if "__pycache__" in path.parts or path.name == "user-data.sh.tpl":
                continue
            tar.add(path, arcname=str(path.relative_to(src)), recursive=False)
        for name, text in {
            "generated/presets.yaml": presets_yaml(),
            "generated/code_execution.json": json.dumps(code_exec, indent=2),
        }.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def upload_bundle() -> None:
    s3.put_object(Bucket=BUCKET, Key="bootstrap/bundle.tgz", Body=bundle())
    log(f"uploaded setup bundle to s3://{BUCKET}/bootstrap/bundle.tgz")


def user_data() -> bytes:
    rendered = (HERE / "vm/user-data.sh.tpl").read_text()
    for key, value in {"BUCKET": BUCKET, "IMAGE": IMAGE, "IDLE_MINUTES": str(IDLE_MINUTES), "HIBERNAR": HIBERNAR}.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    if "{{" in rendered:
        raise SystemExit("unrendered placeholder in user data")
    return gzip.compress(rendered.encode())


def update_running_vm(instance_id: str) -> None:
    """Push vm/ changes: re-download the bundle and re-run the idempotent setup."""
    cmd = (
        f"set -e; aws s3 cp s3://{BUCKET}/bootstrap/bundle.tgz /tmp/bundle.tgz --only-show-errors; "
        "rm -rf /opt/agentepessoal/bundle && mkdir -p /opt/agentepessoal/bundle; "
        "tar -xzf /tmp/bundle.tgz -C /opt/agentepessoal/bundle; "
        "bash /opt/agentepessoal/bundle/setup.sh > /var/log/agentepessoal-update.log 2>&1; tail -3 /var/log/agentepessoal-update.log"
    )
    cid = ssm.send_command(
        InstanceIds=[instance_id], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [f"export PATH=$PATH:/usr/local/bin; {cmd}"]}, TimeoutSeconds=1800,
    )["Command"]["CommandId"]
    log("updating running VM (setup.sh)…")
    for _ in range(360):
        time.sleep(5)
        try:
            r = ssm.get_command_invocation(CommandId=cid, InstanceId=instance_id)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            log(f"update {r['Status']}: {r['StandardOutputContent'].strip()[-500:]}")
            return


def find_instance() -> dict | None:
    res = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [f"{NAME}-agent"]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )
    for r in res["Reservations"]:
        for i in r["Instances"]:
            return i
    return None


def ensure_instance(profile_arn: str, subnet: str, sg: str) -> str:
    existing = find_instance()
    if existing:
        log(f"reusing instance {existing['InstanceId']} ({existing['State']['Name']})")
        return existing["InstanceId"]
    ami = ssm.get_parameter(Name=AMI_PARAM)["Parameter"]["Value"]
    for attempt in range(5):
        try:
            inst = ec2.run_instances(
                ImageId=ami,
                InstanceType=INSTANCE_TYPE,
                MinCount=1,
                MaxCount=1,
                IamInstanceProfile={"Arn": profile_arn},
                NetworkInterfaces=[
                    {"DeviceIndex": 0, "SubnetId": subnet, "Groups": [sg], "AssociatePublicIpAddress": True}
                ],
                BlockDeviceMappings=[
                    {"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": DISK_GB, "VolumeType": "gp3", "Encrypted": True}}
                ],
                MetadataOptions={"HttpTokens": "required", "HttpEndpoint": "enabled"},
                HibernationOptions={"Configured": True},
                InstanceInitiatedShutdownBehavior="stop",
                UserData=user_data(),
                TagSpecifications=[
                    {"ResourceType": "instance", "Tags": TAGS + [{"Key": "Name", "Value": f"{NAME}-agent"}]},
                    {"ResourceType": "volume", "Tags": TAGS},
                ],
            )["Instances"][0]
            log(f"launched instance {inst['InstanceId']} ({INSTANCE_TYPE}, ami {ami})")
            return inst["InstanceId"]
        except ClientError as e:
            # A freshly created instance profile can take a few seconds to be usable.
            if "InvalidParameterValue" in str(e) and "iamInstanceProfile" in str(e) and attempt < 4:
                time.sleep(10)
                continue
            raise
    raise SystemExit("could not launch instance")


def ensure_wake_schedule(instance_id: str) -> None:
    """Role that EventBridge Scheduler uses to start the VM: for the agent's next scheduled task
    (proximo_despertar.py, set at every hibernation) and for WhatsApp messages that arrive while
    it is still hibernating. The old fixed 4-times-a-day wake-up is removed."""
    name = WAKE_ROLE
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": account}}}]}
    try:
        iam.get_role(RoleName=name)
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Tags=TAGS)
        time.sleep(10)
    iam.put_role_policy(RoleName=name, PolicyName="start-vm", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "ec2:StartInstances",
                                                "Resource": f"arn:aws:ec2:{REGION}:{account}:instance/{instance_id}"}]}))
    scheduler = boto3.client("scheduler", region_name=REGION)
    try:
        scheduler.delete_schedule(Name=f"{NAME}-acordar-vm")
        log("removed the fixed wake-up schedule")
    except scheduler.exceptions.ResourceNotFoundException:
        pass
    ensure_safety_wake(instance_id)


def ensure_safety_wake(instance_id: str) -> None:
    """Once a day (8:45, Salvador time), start the VM if it is off: if the wake-up for the next task could not be set
    at hibernation (12/10 review), routines and queued messages wait at most until the next morning. Starting a VM
    that is already running does nothing."""
    scheduler = boto3.client("scheduler", region_name=REGION)
    args = dict(
        Name=f"{NAME}-acordar-diario", ScheduleExpression="cron(45 8 * * ? *)",
        ScheduleExpressionTimezone="America/Bahia", FlexibleTimeWindow={"Mode": "OFF"},
        Target={"Arn": "arn:aws:scheduler:::aws-sdk:ec2:startInstances",
                "RoleArn": f"arn:aws:iam::{account}:role/{WAKE_ROLE}",
                "Input": json.dumps({"InstanceIds": [instance_id]}),
                "RetryPolicy": {"MaximumRetryAttempts": 10, "MaximumEventAgeInSeconds": 3600}},
    )
    try:
        scheduler.create_schedule(**args)
        log("created the daily safety wake-up (8:45)")
    except scheduler.exceptions.ConflictException:
        scheduler.update_schedule(**args)


# ---------------------------------------------------------------- VM travada (23/10)

RECOVERY_FUNCTION = f"{NAME}-recuperar-vm"
ALARM_REBOOT = f"{NAME}-vm-travada"
ALARM_RESTART = f"{NAME}-vm-travada-religar"
PARAM_RECOVERY = f"/{NAME}/recuperacao"


def recovery_alarms(instance_id: str, function_arn: str) -> list[dict]:
    """The stuck-VM alarms (two stages on the status check, plus "running but no network" since 24/10): defined next
    to the function they call, infra/control/recuperar.py (alarmes), so its tests cover them."""
    sys.path.insert(0, str(HERE / "control"))
    from recuperar import alarmes

    return alarmes(instance_id, function_arn, REGION, TAGS)


def ensure_recovery(instance_id: str) -> None:
    role_arn = ensure_role(
        RECOVERY_FUNCTION, "lambda.amazonaws.com", ["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"],
        {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"], "Resource": "*"},
            {"Effect": "Allow", "Action": ["ec2:GetConsoleOutput", "ec2:StopInstances", "ec2:StartInstances"],
             "Resource": f"arn:aws:ec2:{REGION}:{account}:instance/{instance_id}"},
            {"Effect": "Allow", "Action": "s3:PutObject", "Resource": f"arn:aws:s3:::{BUCKET}/incidentes/*"},
            {"Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:PutParameter"],
             "Resource": f"arn:aws:ssm:{REGION}:{account}:parameter{PARAM_RECOVERY}"},
            {"Effect": "Allow", "Action": "ssm:GetParameter",  # Telegram notice (same settings as the control page)
             "Resource": f"arn:aws:ssm:{REGION}:{account}:parameter{PARAM_WHATSAPP}"},
            {"Effect": "Allow", "Action": "kms:Decrypt", "Resource": "*",
             "Condition": {"StringEquals": {"kms:ViaService": f"ssm.{REGION}.amazonaws.com"}}},
        ]},
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(HERE / "control/recuperar.py", "recuperar.py")
    env = {"Variables": {"INSTANCE_ID": instance_id, "BUCKET": BUCKET, "PARAM_ESTADO": PARAM_RECOVERY,
                         "WHATSAPP_PARAM": PARAM_WHATSAPP}}
    try:
        lam.get_function(FunctionName=RECOVERY_FUNCTION)
        lam.update_function_code(FunctionName=RECOVERY_FUNCTION, ZipFile=buf.getvalue())
        lam.get_waiter("function_updated_v2").wait(FunctionName=RECOVERY_FUNCTION)
        lam.update_function_configuration(FunctionName=RECOVERY_FUNCTION, Environment=env, Timeout=900)
        lam.get_waiter("function_updated_v2").wait(FunctionName=RECOVERY_FUNCTION)
        log("updated recovery function")
    except lam.exceptions.ResourceNotFoundException:
        for attempt in range(6):  # new roles take a few seconds before Lambda can assume them
            try:
                lam.create_function(FunctionName=RECOVERY_FUNCTION, Runtime="python3.12", Role=role_arn,
                                    Handler="recuperar.handler", Code={"ZipFile": buf.getvalue()}, Timeout=900,
                                    MemorySize=128, Environment=env, Tags={"Project": NAME})
                break
            except lam.exceptions.InvalidParameterValueException:
                if attempt == 5:
                    raise
                time.sleep(10)
        lam.get_waiter("function_active_v2").wait(FunctionName=RECOVERY_FUNCTION)
        log("created recovery function")
    function_arn = lam.get_function(FunctionName=RECOVERY_FUNCTION)["Configuration"]["FunctionArn"]
    cw = session.client("cloudwatch")
    for alarm in recovery_alarms(instance_id, function_arn):
        try:
            lam.add_permission(FunctionName=RECOVERY_FUNCTION, StatementId=f"alarme-{alarm['AlarmName']}",
                               Action="lambda:InvokeFunction", Principal="lambda.alarms.cloudwatch.amazonaws.com",
                               SourceAccount=account,
                               SourceArn=f"arn:aws:cloudwatch:{REGION}:{account}:alarm:{alarm['AlarmName']}")
        except lam.exceptions.ResourceConflictException:
            pass
        cw.put_metric_alarm(**alarm)
        log(f"alarm {alarm['AlarmName']}: {alarm['EvaluationPeriods']} x {alarm['Period'] // 60} min")


# ---------------------------------------------------------------- control page

def ensure_whatsapp_queue() -> str:
    """Messages from WhatsApp wait here while the VM wakes up (kept 4 days)."""
    url = sqs.create_queue(QueueName=WHATSAPP_QUEUE, Attributes={
        "MessageRetentionPeriod": str(4 * 24 * 3600), "VisibilityTimeout": "120", "SqsManagedSseEnabled": "true",
    }, tags={"Project": NAME})["QueueUrl"]
    return url


def ensure_control_role(instance_id: str) -> str:
    return ensure_role(
        CONTROL_ROLE,
        "lambda.amazonaws.com",
        ["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"],
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": "ec2:DescribeInstances", "Resource": "*"},
                {
                    "Effect": "Allow",
                    "Action": ["ec2:StartInstances", "ec2:StopInstances"],
                    "Resource": f"arn:aws:ec2:{REGION}:{account}:instance/{instance_id}",
                },
                {
                    "Effect": "Allow",
                    "Action": ["ssm:GetParameter", "ssm:PutParameter"],
                    "Resource": [
                        f"arn:aws:ssm:{REGION}:{account}:parameter{PARAM_URL}",
                        f"arn:aws:ssm:{REGION}:{account}:parameter{PARAM_PHONE}",
                    ],
                },
                {   # 23/10: "Abrir OpenCode" (the VM publishes the tunnel address there; read only)
                    "Effect": "Allow",
                    "Action": "ssm:GetParameter",
                    "Resource": f"arn:aws:ssm:{REGION}:{account}:parameter{PARAM_OPENCODE}",
                },
                {   # "Baixar app Android": presigned GET of the APK built by android/build.sh
                    "Effect": "Allow",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{BUCKET}/app/agente.apk",
                },
                {   # "Enviar arquivos": presigned PUTs into the inbox the VM pulls from
                    "Effect": "Allow",
                    "Action": "s3:PutObject",
                    "Resource": f"arn:aws:s3:::{BUCKET}/entrada/*",
                },
                {   # WhatsApp: settings (token, app secret, numbers), filled from this page
                    "Effect": "Allow",
                    "Action": ["ssm:GetParameter", "ssm:PutParameter"],
                    "Resource": f"arn:aws:ssm:{REGION}:{account}:parameter{PARAM_WHATSAPP}",
                },
                {
                    "Effect": "Allow",
                    "Action": ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
                    "Resource": "*",
                    "Condition": {"StringEquals": {"kms:ViaService": f"ssm.{REGION}.amazonaws.com"}},
                },
                {"Effect": "Allow", "Action": "sqs:SendMessage",
                 "Resource": f"arn:aws:sqs:{REGION}:{account}:{WHATSAPP_QUEUE}"},
                {   # a message that arrives while the VM is still hibernating wakes it 2 min later
                    "Effect": "Allow",
                    "Action": ["scheduler:CreateSchedule", "scheduler:UpdateSchedule"],
                    "Resource": f"arn:aws:scheduler:{REGION}:{account}:schedule/default/{WAKE_LATER}",
                },
                {"Effect": "Allow", "Action": "iam:PassRole",
                 "Resource": f"arn:aws:iam::{account}:role/{WAKE_ROLE}"},
                {   # "Desligar agora" runs hibernate.sh on the VM (backup, then hibernate)
                    "Effect": "Allow",
                    "Action": "ssm:SendCommand",
                    "Resource": [
                        f"arn:aws:ec2:{REGION}:{account}:instance/{instance_id}",
                        f"arn:aws:ssm:{REGION}::document/AWS-RunShellScript",
                    ],
                },
            ],
        },
    )


def ensure_control(instance_id: str, password: str) -> str:
    role_arn = ensure_control_role(instance_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(HERE / "control/index.py", "index.py")
        z.write(HERE / "control/whatsapp.py", "whatsapp.py")
        z.write(HERE / "control/telegram.py", "telegram.py")
    env = {
        "Variables": {
            "INSTANCE_ID": instance_id,
            "PASSWORD_SHA256": hashlib.sha256(password.encode()).hexdigest(),
            "URL_PARAM": PARAM_URL,
            "PHONE_PARAM": PARAM_PHONE,
            "BUCKET": BUCKET,
            "WHATSAPP_PARAM": PARAM_WHATSAPP,
            "WHATSAPP_QUEUE_URL": ensure_whatsapp_queue(),
            "WAKE_ROLE_ARN": f"arn:aws:iam::{account}:role/{WAKE_ROLE}",
            "WAKE_LATER_SCHEDULE": WAKE_LATER,
        }
    }
    try:
        lam.get_function(FunctionName=FUNCTION)
        lam.update_function_code(FunctionName=FUNCTION, ZipFile=buf.getvalue())
        lam.get_waiter("function_updated_v2").wait(FunctionName=FUNCTION)
        lam.update_function_configuration(FunctionName=FUNCTION, Environment=env)
        lam.get_waiter("function_updated_v2").wait(FunctionName=FUNCTION)
        log("updated control function")
    except lam.exceptions.ResourceNotFoundException:
        for attempt in range(6):  # new roles take a few seconds before Lambda can assume them
            try:
                lam.create_function(
                    FunctionName=FUNCTION,
                    Runtime="python3.12",
                    Role=role_arn,
                    Handler="index.handler",
                    Code={"ZipFile": buf.getvalue()},
                    Timeout=20,
                    MemorySize=256,
                    Environment=env,
                    Tags={"Project": NAME},
                )
                break
            except lam.exceptions.InvalidParameterValueException:
                if attempt == 5:
                    raise
                time.sleep(10)
        lam.get_waiter("function_active_v2").wait(FunctionName=FUNCTION)
        log("created control function")

    try:
        url = lam.get_function_url_config(FunctionName=FUNCTION)["FunctionUrl"]
    except lam.exceptions.ResourceNotFoundException:
        url = lam.create_function_url_config(FunctionName=FUNCTION, AuthType="NONE")["FunctionUrl"]
    for sid, kwargs in {
        "public-url": {"Action": "lambda:InvokeFunctionUrl", "FunctionUrlAuthType": "NONE"},
        "public-url-invoke": {"Action": "lambda:InvokeFunction", "InvokedViaFunctionUrl": True},
    }.items():
        try:
            lam.add_permission(FunctionName=FUNCTION, StatementId=sid, Principal="*", **kwargs)
        except lam.exceptions.ResourceConflictException:
            pass
    ensure_upload_cors(url)
    return url


def ensure_upload_cors(page_url: str) -> None:
    """Let the control page and the agent UI PUT files into the bucket from the browser (presigned only)."""
    origin = page_url.rstrip("/")
    s3.put_bucket_cors(
        Bucket=BUCKET,
        CORSConfiguration={"CORSRules": [{
            # control page + the agent UI behind its quick tunnel (the URL changes on reboot)
            "AllowedOrigins": [origin, "https://*.trycloudflare.com"],
            "AllowedMethods": ["PUT"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }]},
    )


def main() -> None:
    if "--despertar" in sys.argv:  # only the wake-up schedules (no VM, page or password changes)
        return ensure_wake_schedule(find_instance()["InstanceId"])
    if "--recuperacao" in sys.argv:  # only the stuck-VM alarms and their function (23/10)
        return ensure_recovery(find_instance()["InstanceId"])
    if "--controle-iam" in sys.argv:  # only the control function's permissions (code: implantar.py --controle)
        ensure_control_role(find_instance()["InstanceId"])
        return log("control role policy updated")
    log(f"account {account}, region {REGION}")
    password, created = ensure_parameters()
    ensure_bucket()
    profile = ensure_vm_role()
    ensure_meta_secret_role()
    ensure_voice_role()
    upload_bundle()
    subnet, vpc = default_subnet_and_vpc()
    sg = ensure_security_group(vpc)
    existed = find_instance() is not None
    instance_id = ensure_instance(profile, subnet, sg)
    ensure_wake_schedule(instance_id)
    ensure_recovery(instance_id)
    url = ensure_control(instance_id, password)
    if existed and "--update" in sys.argv:
        update_running_vm(instance_id)
    print()
    print(f"Instance:      {instance_id}")
    print(f"Control page:  {url}")
    print(f"Personal link: {url}#k={password}")
    print(f"               stored in SSM parameter {PARAM_PASSWORD}")
    print(f"Backups:       s3://{BUCKET}/usr (hourly and before every stop)")


if __name__ == "__main__":
    main()
