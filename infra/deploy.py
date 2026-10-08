"""Create (or update) the on-demand agent + phone VM and its control page on AWS.

Idempotent: re-running reuses existing resources (found by name/tag).
Usage:  python infra/deploy.py            create / update cloud resources
        python infra/deploy.py --update   also push vm/ changes to the running VM (re-runs setup.sh)
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
IDLE_MINUTES = 30
IMAGE = "agent0ai/agent-zero:v2.13"
PARAM_PASSWORD = f"/{NAME}/password"
PARAM_URL = f"/{NAME}/agent-url"
PARAM_PHONE = f"/{NAME}/phone-url"
VM_ROLE = f"{NAME}-vm"
META_ROLE = f"{NAME}-segredo-meta"
CONTROL_ROLE = f"{NAME}-control"
FUNCTION = f"{NAME}-control"

HERE = Path(__file__).parent
ROOT = HERE.parent
TAGS = [{"Key": "Project", "Value": NAME}]

session = boto3.Session(region_name=REGION)
ec2 = session.client("ec2")
iam = session.client("iam")
ssm = session.client("ssm")
lam = session.client("lambda")
s3 = session.client("s3")
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
                {"Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:PutParameter"], "Resource": params},
                {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{BUCKET}"},
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                    "Resource": f"arn:aws:s3:::{BUCKET}/*",
                },
                {
                    "Effect": "Allow",
                    "Action": "kms:Decrypt",
                    "Resource": "*",
                    "Condition": {"StringEquals": {"kms:ViaService": f"ssm.{REGION}.amazonaws.com"}},
                },
                {   # the idle watchdog hibernates its own instance
                    "Effect": "Allow",
                    "Action": "ec2:StopInstances",
                    "Resource": f"arn:aws:ec2:{REGION}:{account}:instance/*",
                    "Condition": {"StringEquals": {"aws:ResourceTag/Project": NAME}},
                },
            ],
        },
    )
    # credenciais_meta.py hands the agent short-lived credentials of META_ROLE
    iam.put_role_policy(RoleName=VM_ROLE, PolicyName=f"{VM_ROLE}-segredo-meta", PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Resource": f"arn:aws:iam::{account}:role/{META_ROLE}"}],
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

    def model(slot: str, name: str, extra: str) -> str:
        return (
            f"  {slot}:\n    provider: other\n    name: {name}\n    api_base: {base}\n"
            f"    ctx_length: 200000\n{extra}    rl_requests: 0\n    rl_input: 0\n    rl_output: 0\n"
            f"    kwargs:\n{kwargs}"
        )

    def claude(slot: str, name: str, extra: str, effort: str = "") -> str:
        # Claude runs on the Bedrock runtime (Converse API) behind the proxy's /bedrock route; the
        # proxy swaps the placeholder key for a fresh bearer token
        return (
            f"  {slot}:\n    provider: bedrock\n    name: converse/{name}\n"
            f"    ctx_length: 200000\n{extra}    rl_requests: 0\n    rl_input: 0\n    rl_output: 0\n"
            "    kwargs:\n      a0_api_mode: chat\n      api_base: http://host.docker.internal:8787/bedrock\n"
            "      api_key: proxy\n      aws_region_name: us-east-1\n"
            + (f"      output_config:\n        effort: {effort}\n" if effort else "")
        )

    haiku = "us.anthropic.claude-haiku-5-5"
    chat_extra = "    ctx_history: 0.7\n    vision: true\n    max_embeds: 30\n"  # images kept in context; at 10 a 7+5 image comparison looped forever
    util_extra = "    ctx_input: 0.7\n"
    embedding = (
        "  embedding:\n    provider: huggingface\n    name: sentence-transformers/all-MiniLM-L6-v2\n"
        "    api_base: ''\n    rl_requests: 0\n    rl_input: 0\n    kwargs: {}\n"
    )
    return (
        "- name: Default\n"
        + model("chat", "openai.gpt-6.1-sol", chat_extra)
        + model("utility", "openai.gpt-6-luna", util_extra)
        + embedding
        + "- name: Rapido\n"
        + model("chat", "openai.gpt-6-luna", chat_extra)
        + model("utility", "openai.gpt-6-luna", util_extra)
        + "- name: Sol + Haiku\n"
        + model("chat", "openai.gpt-6.1-sol", chat_extra)
        + claude("utility", haiku, util_extra)
        + "- name: Haiku\n"
        + claude("chat", haiku, chat_extra)
        + claude("utility", haiku, util_extra)
        + "- name: Haiku max\n"
        + claude("chat", haiku, chat_extra, effort="max")
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
    for key, value in {"BUCKET": BUCKET, "IMAGE": IMAGE, "IDLE_MINUTES": str(IDLE_MINUTES)}.items():
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
    """The VM hibernates when idle, which would also stop the agent's own scheduled tasks.
    Start it 10 minutes before they run (00/06/12/18 America/Bahia = 03/09/15/21 UTC)."""
    name = f"{NAME}-acordar-vm"
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": account}}}]}
    try:
        role_arn = iam.get_role(RoleName=name)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        role_arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Tags=TAGS)["Role"]["Arn"]
        time.sleep(10)
    iam.put_role_policy(RoleName=name, PolicyName="start-vm", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "ec2:StartInstances",
                                                "Resource": f"arn:aws:ec2:{REGION}:{account}:instance/{instance_id}"}]}))
    scheduler = boto3.client("scheduler", region_name=REGION)
    args = dict(
        Name=name, ScheduleExpression="cron(50 2,8,14,20 * * ? *)", ScheduleExpressionTimezone="UTC",
        FlexibleTimeWindow={"Mode": "OFF"}, State="ENABLED",
        Target={"Arn": "arn:aws:scheduler:::aws-sdk:ec2:startInstances", "RoleArn": role_arn,
                "Input": json.dumps({"InstanceIds": [instance_id]})},
    )
    try:
        scheduler.create_schedule(**args)
        log(f"created schedule {name}")
    except scheduler.exceptions.ConflictException:
        scheduler.update_schedule(**args)


# ---------------------------------------------------------------- control page

def ensure_control(instance_id: str, password: str) -> str:
    role_arn = ensure_role(
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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(HERE / "control/index.py", "index.py")
    env = {
        "Variables": {
            "INSTANCE_ID": instance_id,
            "PASSWORD_SHA256": hashlib.sha256(password.encode()).hexdigest(),
            "URL_PARAM": PARAM_URL,
            "PHONE_PARAM": PARAM_PHONE,
            "BUCKET": BUCKET,
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
    log(f"account {account}, region {REGION}")
    password, created = ensure_parameters()
    ensure_bucket()
    profile = ensure_vm_role()
    ensure_meta_secret_role()
    upload_bundle()
    subnet, vpc = default_subnet_and_vpc()
    sg = ensure_security_group(vpc)
    existed = find_instance() is not None
    instance_id = ensure_instance(profile, subnet, sg)
    url = ensure_control(instance_id, password)
    ensure_wake_schedule(instance_id)
    if existed and "--update" in sys.argv:
        update_running_vm(instance_id)
    print()
    print(f"Instance:      {instance_id}")
    print(f"Control page:  {url}")
    print(f"Personal link: {url}#k={password}")
    print(f"               stored in SSM parameter {PARAM_PASSWORD}")
    print(f"Backups:       s3://{BUCKET}/usr (hourly and before every hibernation)")


if __name__ == "__main__":
    main()
