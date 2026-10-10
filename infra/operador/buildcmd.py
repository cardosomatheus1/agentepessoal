import os, sys, time, boto3  # SSM on the IA Business build machine (ros-dev-construcao)
ssm = boto3.client("ssm", region_name="us-east-1")
iid = os.environ.get("VM_ID", "i-08adac4830ec57e5a")  # ros-dev-construcao
cid = ssm.send_command(InstanceIds=[iid], DocumentName="AWS-RunShellScript", Parameters={"commands": [sys.argv[1]]}, TimeoutSeconds=600)["Command"]["CommandId"]
for _ in range(200):
    time.sleep(3)
    try:
        r = ssm.get_command_invocation(CommandId=cid, InstanceId=iid)
    except ssm.exceptions.InvocationDoesNotExist:
        continue
    if r["Status"] not in ("Pending", "InProgress", "Delayed"):
        print(r["StandardOutputContent"][-6000:]); print(r["StandardErrorContent"][-2000:]); break
