import os, sys, time, boto3
ssm = boto3.client("ssm", region_name="us-east-1")
iid = os.environ.get("VM_ID", "i-0498b4f39560b01a9")  # the agent VM (Agent Zero)
cmd = sys.argv[1]
for _ in range(60):
    info = ssm.describe_instance_information(Filters=[{"Key": "InstanceIds", "Values": [iid]}])["InstanceInformationList"]
    if info and info[0]["PingStatus"] == "Online": break
    time.sleep(10)
else:
    print("SSM agent not online"); sys.exit(1)
cid = ssm.send_command(InstanceIds=[iid], DocumentName="AWS-RunShellScript", Parameters={"commands": [cmd]}, TimeoutSeconds=600)["Command"]["CommandId"]
for _ in range(120):
    time.sleep(3)
    try:
        r = ssm.get_command_invocation(CommandId=cid, InstanceId=iid)
    except ssm.exceptions.InvocationDoesNotExist:
        continue
    if r["Status"] not in ("Pending", "InProgress", "Delayed"):
        print(r["StandardOutputContent"][-6000:]); print(r["StandardErrorContent"][-2000:]); break
