"""Create (or update) the on-demand agent VM and its control page on AWS.

Idempotent: re-running reuses existing resources (found by name/tag).
Usage:  python infra/deploy.py
"""

import base64
import gzip
import hashlib
import io
import tarfile
import json
import secrets
import string
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
NAME = "agentepessoal"
INSTANCE_TYPE = "t3.large"
DISK_GB = 40
IDLE_MINUTES = 30
LOGIN = "admin"
IMAGE = "agent0ai/agent-zero:v2.13"
PARAM_PASSWORD = f"/{NAME}/password"
PARAM_URL = f"/{NAME}/agent-url"
VM_ROLE = f"{NAME}-vm"
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
    try:
        ssm.get_parameter(Name=PARAM_URL)
    except ssm.exceptions.ParameterNotFound:
        ssm.put_parameter(Name=PARAM_URL, Value="stopped", Type="String", Tags=TAGS)
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
            ],
        },
    )
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


# ---------------------------------------------------------------- network

def default_subnet_and_vpc() -> tuple[str, str]:
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise SystemExit("No default VPC in us-east-1; create one or pick a public subnet.")
    vpc = vpcs[0]["VpcId"]
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "vpc-id", "Values": [vpc]}, {"Name": "default-for-az", "Values": ["true"]}]
    )["Subnets"]
    # t3 is not offered in every AZ (e.g. use1-az3); prefer the common ones.
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

    chat_extra = "    ctx_history: 0.7\n    vision: true\n    max_embeds: 10\n"
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
    )


def project_tgz() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        src = HERE / "vm/project-carreira"
        for path in sorted(src.rglob("*")):
            tar.add(path, arcname=str(path.relative_to(src)), recursive=False)
    return buf.getvalue()


def user_data() -> bytes:
    b64 = lambda text: base64.b64encode(text.encode()).decode()  # noqa: E731
    code_exec = json.loads((ROOT / "config/code_execution.json").read_text())
    code_exec["ssh_enabled"] = "auto"  # inside the Docker image this resolves to local shell
    rendered = (HERE / "vm/user-data.sh.tpl").read_text()
    for key, value in {
        "PROXY_PY_B64": b64((HERE / "vm/bedrock_proxy.py").read_text()),
        "REPORT_PY_B64": b64((HERE / "vm/report_url.py").read_text()),
        "WATCHDOG_B64": b64((HERE / "vm/watchdog.sh").read_text()),
        "BACKUP_B64": b64((HERE / "vm/backup.sh").read_text()),
        "PROJECT_TGZ_B64": base64.b64encode(project_tgz()).decode(),
        "BUCKET": BUCKET,
        "PRESETS_B64": b64(presets_yaml()),
        "CODEEXEC_B64": b64(json.dumps(code_exec, indent=2)),
        "IMAGE": IMAGE,
        "LOGIN": LOGIN,
        "IDLE_MINUTES": str(IDLE_MINUTES),
    }.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    if "{{" in rendered:
        raise SystemExit("unrendered placeholder in user data")
    # cloud-init accepts gzip-compressed user data; this keeps us under the 16 KB limit.
    packed = gzip.compress(rendered.encode())
    if len(packed) > 16000:
        raise SystemExit("user data too large")
    return packed


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
    ami = ssm.get_parameter(
        Name="/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    )["Parameter"]["Value"]
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
                    "Resource": f"arn:aws:ssm:{REGION}:{account}:parameter{PARAM_URL}",
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
    return url


def main() -> None:
    log(f"account {account}, region {REGION}")
    password, created = ensure_parameters()
    ensure_bucket()
    profile = ensure_vm_role()
    subnet, vpc = default_subnet_and_vpc()
    sg = ensure_security_group(vpc)
    instance_id = ensure_instance(profile, subnet, sg)
    url = ensure_control(instance_id, password)
    print()
    print(f"Instance:      {instance_id}")
    print(f"Control page:  {url}")
    print(f"Agent login:   {LOGIN}")
    print(f"Password:      {'(new) ' if created else ''}{password}")
    print(f"               stored in SSM parameter {PARAM_PASSWORD}")
    print(f"Backups:       s3://{BUCKET}/usr (hourly and on every shutdown)")


if __name__ == "__main__":
    main()
