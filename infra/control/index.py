"""Control page for the agent + phone VM: shows status, starts it and hibernates it.

Served through a Lambda Function URL. Every action requires the personal key (sent from the
link's #k= fragment); only its SHA-256 lives in the function's environment.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import urllib.request

import boto3
from botocore.config import Config

INSTANCE_ID = os.environ["INSTANCE_ID"]
PASSWORD_SHA256 = os.environ["PASSWORD_SHA256"]
URL_PARAM = os.environ.get("URL_PARAM", "/agentepessoal/agent-url")
PHONE_PARAM = os.environ.get("PHONE_PARAM", "/agentepessoal/phone-url")
BUCKET = os.environ.get("BUCKET", "")
INBOX = "entrada/"
MAX_UPLOAD = 5 * 1024**3  # single PUT limit

ec2 = boto3.client("ec2")
ssm = boto3.client("ssm")
s3 = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)


def _authorized(password: str) -> bool:
    digest = hashlib.sha256((password or "").encode()).hexdigest()
    return hmac.compare_digest(digest, PASSWORD_SHA256)


def _state() -> str:
    res = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    return res["Reservations"][0]["Instances"][0]["State"]["Name"]


def _param(name: str) -> str:
    try:
        return ssm.get_parameter(Name=name)["Parameter"]["Value"]
    except Exception:
        return ""


def _set(name: str, value: str) -> None:
    ssm.put_parameter(Name=name, Value=value, Type="String", Overwrite=True)


def _reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=3) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def _status() -> dict:
    state = _state()
    url = _param(URL_PARAM) if state == "running" else ""
    phone = _param(PHONE_PARAM) if state == "running" else ""
    ready = bool(url.startswith("https://") and _reachable(url))
    phone_ready = bool(phone.startswith("https://") and _reachable(phone))
    return {
        "state": state,
        "url": url if ready else "",
        "ready": ready,
        "phone_url": phone if phone_ready else "",
    }


def _hibernate() -> None:
    """Back up and hibernate from inside the VM; fall back to a direct hibernate."""
    _set(URL_PARAM, "stopped")
    _set(PHONE_PARAM, "stopped")
    try:
        ssm.send_command(
            InstanceIds=[INSTANCE_ID],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": ["nohup /opt/agentepessoal/hibernate.sh >/var/log/agentepessoal-hibernate.log 2>&1 &"]},
        )
    except Exception:
        ec2.stop_instances(InstanceIds=[INSTANCE_ID], Hibernate=True)


def _safe_name(name: str) -> str:
    name = os.path.basename(str(name or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f/]", "", name)[:180]
    return name if name not in ("", ".", "..") else "arquivo"


def _upload_url(name: str, size: int) -> dict:
    """Presigned PUT straight to S3 (no tunnel size limit; works while the VM is off)."""
    if not BUCKET:
        return {"error": "envio de arquivos não configurado"}
    if not 0 <= int(size or 0) <= MAX_UPLOAD:
        return {"error": "arquivo maior que 5 GB"}
    key = INBOX + _safe_name(name)
    url = s3.generate_presigned_url("put_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=6 * 3600)
    return {"url": url, "name": key[len(INBOX):]}


def _apk_url() -> dict:
    """Short-lived download link for the Android app built by android/build.sh."""
    if not BUCKET:
        return {"error": "app não publicado"}
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": "app/agente.apk",
                "ResponseContentDisposition": 'attachment; filename="Agente.apk"',
                "ResponseContentType": "application/vnd.android.package-archive"},
        ExpiresIn=600,
    )
    return {"url": url}


def _json(body: dict, code: int = 200) -> dict:
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def handler(event, _context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "GET":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"},
            "body": PAGE,
        }

    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        data = json.loads(raw)
    except ValueError:
        return _json({"error": "bad request"}, 400)
    if not _authorized(data.get("password", "")):
        return _json({"error": "senha incorreta"}, 401)

    action = data.get("action", "status")
    if action == "upload":
        return _json(_upload_url(data.get("name", ""), data.get("size", 0)))
    if action == "apk":
        return _json(_apk_url())
    if action == "start":
        if _state() == "stopped":
            _set(URL_PARAM, "starting")
            _set(PHONE_PARAM, "starting")
            ec2.start_instances(InstanceIds=[INSTANCE_ID])
    elif action == "stop":
        if _state() == "running":
            _hibernate()
    return _json(_status())


PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0d0d0d">
<title>Agente · Controle</title>
<style>
:root{--bg:#0d0d0d;--surface:#1b1b1b;--line:#2b2b2b;--fg:#ededed;--muted:#9a9a9a;--ok:#4ade80;--warn:#fbbf24}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;min-height:100dvh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif;padding:16px}
.card{width:100%;max-width:420px;background:var(--surface);border:1px solid var(--line);border-radius:24px;padding:28px}
h1{font-size:22px;font-weight:600;margin:0 0 4px}p{margin:0;color:var(--muted)}
.status{display:flex;align-items:center;gap:10px;margin:22px 0;font-size:16px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--muted)}.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn);animation:p 1s infinite}
@keyframes p{50%{opacity:.3}}
input{width:100%;background:#111;border:1px solid var(--line);border-radius:14px;color:var(--fg);padding:13px 14px;font-size:15px;margin-bottom:12px}
button,a.btn{display:block;width:100%;text-align:center;border:0;border-radius:999px;padding:13px;font-size:15px;font-weight:600;cursor:pointer;text-decoration:none;margin-top:10px}
.primary{background:#fff;color:#0d0d0d}.secondary{background:transparent;color:var(--muted);border:1px solid var(--line)!important}
button:disabled{opacity:.4;cursor:default}.err{color:#ff6b6b;margin-top:10px;min-height:1.5em}
label.btn{display:block;text-align:center;border-radius:999px;padding:13px;font-weight:600;cursor:pointer;margin-top:10px}
.up{margin-top:18px;border-top:1px solid var(--line);padding-top:8px}
.file{margin-top:10px;font-size:13px}.file .bar{height:6px;background:#111;border-radius:99px;overflow:hidden;margin-top:4px}
.file .bar i{display:block;height:100%;width:0;background:var(--ok)}.file.erro{color:#ff6b6b}
</style></head><body><div class="card">
<h1>Agente</h1><p>Liga a máquina só quando você for usar.</p>
<div id="nokey" hidden><div style="height:18px"></div><p>Abra esta página pelo seu link pessoal (o que tem <code>#k=</code> no final).</p></div>
<div id="panel" hidden>
<div class="status"><span id="dot" class="dot"></span><span id="label">…</span></div>
<a id="open" class="btn primary" hidden>Abrir o agente</a>
<a id="phone" class="btn secondary" target="_blank" rel="noopener" hidden>Ver celular</a>
<button id="start" class="primary" onclick="act('start')" hidden>Ligar</button>
<button id="stop" class="secondary" onclick="act('stop')" hidden>Hibernar agora</button>
<div class="up">
<label class="btn secondary" for="files">Enviar arquivos</label>
<input id="files" type="file" multiple hidden onchange="sendFiles(this.files)">
<div id="uplist"></div>
<p style="font-size:13px;margin-top:8px">Até 5 GB por arquivo. Vão direto para o armazenamento da sua conta (funciona com a máquina desligada) e aparecem na pasta <b>entrada</b> do agente (botão Files) até 30 s depois de ele estar ligado.</p>
</div>
<button id="apk" class="secondary" onclick="baixarApp()" hidden>Baixar app Android</button>
<p style="margin-top:16px;font-size:13px">Hiberna sozinha após 30 min sem uso (guarda tudo e volta de onde parou). Depois de clicar em Ligar, o agente abre sozinho quando estiver pronto.</p>
</div><div id="err" class="err"></div></div>
<script>
// The personal link carries the key in the URL fragment (never sent in requests or logs);
// it is also remembered on this device so the bare page works next time.
const $=id=>document.getElementById(id);let timer=null,autoOpen=false,key="";
const m=location.hash.match(/k=([^&]+)/);
try{if(m){key=decodeURIComponent(m[1]);localStorage.setItem("agkey",key)}else{key=localStorage.getItem("agkey")||""}}catch(e){if(m)key=decodeURIComponent(m[1])}
async function call(action){const r=await fetch(location.origin+location.pathname,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:key,action})});
const d=await r.json();if(r.status===401){try{localStorage.removeItem("agkey")}catch(e){}$("panel").hidden=true;$("nokey").hidden=false;throw new Error("Link pessoal inválido.")}return d}
function render(s){const L={running:s.ready?"Ligado e pronto":"Acordando o agente…",pending:"Ligando a máquina…",stopping:"Hibernando…",stopped:"Desligado (hibernado)"};
$("label").textContent=L[s.state]||s.state;$("dot").className="dot "+(s.ready?"ok":(s.state==="stopped"?"":"warn"));
$("open").hidden=!s.ready;if(s.ready)$("open").href=s.url;$("phone").hidden=!s.phone_url;if(s.phone_url)$("phone").href=s.phone_url;$("start").hidden=s.state!=="stopped";$("stop").hidden=s.state!=="running";
if(s.ready&&autoOpen){location.href=s.url;return}
clearTimeout(timer);if((!s.ready||!s.phone_url)&&s.state!=="stopped")timer=setTimeout(refresh,2500)}
async function refresh(){try{$("err").textContent="";render(await call("status"))}catch(e){$("err").textContent=e.message}}
async function act(a){autoOpen=a==="start";try{$("err").textContent="";render(await call(a))}catch(e){$("err").textContent=e.message}}
if(!/AgenteApp/.test(navigator.userAgent)&&/Android/i.test(navigator.userAgent))$("apk").hidden=false;
async function baixarApp(){try{$("err").textContent="";const d=await call("apk");if(!d.url)throw new Error(d.error||"falhou");location.href=d.url}catch(e){$("err").textContent=e.message}}
function sendFiles(list){[...list].forEach(sendOne);$("files").value=""}
async function sendOne(f){const row=document.createElement("div");row.className="file";
row.innerHTML='<span></span><div class="bar"><i></i></div>';row.firstChild.textContent=f.name+" — preparando…";$("uplist").appendChild(row);
const label=t=>row.firstChild.textContent=f.name+" — "+t;
try{const r=await fetch(location.origin+location.pathname,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:key,action:"upload",name:f.name,size:f.size})});
const d=await r.json();if(!d.url)throw new Error(d.error||"falhou");
await new Promise((ok,fail)=>{const x=new XMLHttpRequest();x.open("PUT",d.url);
x.upload.onprogress=e=>{if(e.lengthComputable){const p=Math.round(e.loaded*100/e.total);row.querySelector("i").style.width=p+"%";label(p+"%")}};
x.onload=()=>x.status<300?ok():fail(new Error("erro "+x.status));x.onerror=()=>fail(new Error("conexão caiu"));x.send(f)});
row.querySelector("i").style.width="100%";label("enviado ✓ (entrada/"+d.name+")")}catch(e){row.className="file erro";label(e.message)}}
if(key){$("panel").hidden=false;refresh()}else{$("nokey").hidden=false}
</script></body></html>"""
