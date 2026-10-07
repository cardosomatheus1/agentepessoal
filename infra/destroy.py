"""Remove everything deploy.py created.

Backups in S3 are kept unless --delete-backups is passed.
Usage:  python infra/destroy.py [--delete-backups]
"""

import sys
import time

import boto3
from botocore.exceptions import ClientError

from deploy import BUCKET, CONTROL_ROLE, FUNCTION, NAME, PARAM_PASSWORD, PARAM_PHONE, PARAM_URL, REGION, VM_ROLE, find_instance

session = boto3.Session(region_name=REGION)
ec2, iam, ssm, lam, s3 = (session.client(n) for n in ("ec2", "iam", "ssm", "lambda", "s3"))


def quiet(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ClientError as e:
        print(f"  skip: {e.response['Error']['Code']}")


def delete_role(name: str) -> None:
    try:
        for p in iam.list_attached_role_policies(RoleName=name)["AttachedPolicies"]:
            iam.detach_role_policy(RoleName=name, PolicyArn=p["PolicyArn"])
        for p in iam.list_role_policies(RoleName=name)["PolicyNames"]:
            iam.delete_role_policy(RoleName=name, PolicyName=p)
        iam.delete_role(RoleName=name)
    except iam.exceptions.NoSuchEntityException:
        pass


def main() -> None:
    inst = find_instance()
    if inst:
        print(f"terminating {inst['InstanceId']}")
        ec2.terminate_instances(InstanceIds=[inst["InstanceId"]])
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[inst["InstanceId"]])

    print("deleting control function")
    quiet(lam.delete_function_url_config, FunctionName=FUNCTION)
    quiet(lam.delete_function, FunctionName=FUNCTION)

    print("deleting IAM roles")
    try:
        iam.remove_role_from_instance_profile(InstanceProfileName=VM_ROLE, RoleName=VM_ROLE)
    except ClientError:
        pass
    quiet(iam.delete_instance_profile, InstanceProfileName=VM_ROLE)
    delete_role(VM_ROLE)
    delete_role(CONTROL_ROLE)

    print("deleting security group")
    for sg in ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [f"{NAME}-vm"]}])["SecurityGroups"]:
        for _ in range(10):
            try:
                ec2.delete_security_group(GroupId=sg["GroupId"])
                break
            except ClientError:
                time.sleep(10)

    print("deleting parameters")
    quiet(ssm.delete_parameters, Names=[PARAM_PASSWORD, PARAM_URL, PARAM_PHONE])

    if "--delete-backups" in sys.argv:
        print(f"deleting bucket {BUCKET} and all backups")
        bucket = session.resource("s3").Bucket(BUCKET)
        bucket.object_versions.delete()
        quiet(s3.delete_bucket, Bucket=BUCKET)
    else:
        print(f"kept backups in s3://{BUCKET} (use --delete-backups to remove)")


if __name__ == "__main__":
    main()
