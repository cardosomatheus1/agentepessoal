# Prints the last messages of one agent conversation. On the VM: bash ver_chat.sh <chat id>
python3 - "$1" <<'PY'
import json, sys
d = json.load(open(f"/opt/a0/usr/chats/{sys.argv[1]}/chat.json"))
def walk(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("content", "text", "message") and isinstance(v, str) and ("tool_name" in v or "Response" in v or len(v) < 600):
                out.append(v)
            walk(v, out)
    elif isinstance(o, list):
        for v in o: walk(v, out)
out = []; walk(d, out)
for x in out[-14:]: print("-", x.replace("\n", " ")[:300])
PY
