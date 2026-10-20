"""Prompt-cache report from the model proxy's usage log (20/10, research item C1). Usage, from the repository root:

    python3 infra/operador/cache_relatorio.py [--horas 24] [--top 25]
    python3 infra/operador/cache_relatorio.py --arquivo uso.jsonl [--tarefas tasks.json] [--horas 24]   (a local file)

Without --arquivo it runs ON THE VM (read only, through SSM): this file goes there, reads
/var/lib/agentepessoal/uso.jsonl and the routines' names in scheduler/tasks.json, and only the report comes back.
The log has ids, numbers and hashes only (bedrock_proxy.py), never the text of a request.

For each routine and chat: calls, % of the input read from / written to the cache, estimated cost (same prices as
/gasto in ponte_whatsapp.py) and, for each cache miss, what changed at the start of the prompt compared with the
previous call of the same chat/agent/model: instructions, tools, first message, history shortened (fewer
messages: summarized, or a new run of the routine), cache expired (pause longer than its lifetime) or nothing at
the start (something in the middle changed)."""

import base64
import datetime as dt
import json
import sys
from collections import Counter, defaultdict

# same table as ponte_whatsapp.PRECOS (a test keeps them equal): US$ per million tokens
# (input, cache read, output[, cache write 5 min]); 1-hour cache writes cost 2x the input price
PRECOS = {"sol": (2.20, 0.22, 11.0), "haiku": (0.55, 0.055, 2.75, 0.1375), "nova-pro": (0.80, 0.20, 1.60, 0.0),
          "sonnet": (2.0, 0.20, 10.0, 2.5), "opus": (4.0, 0.20, 20.0, 5.0),
          "luna": (0.11, 0.011, 0.55)}
MINIMO = 1024  # below this the models do not cache at all: not a miss
FALHA = 0.10  # less than 10% of the input read from the cache = a miss
PARTES = ("instrucoes", "ferramentas", "primeira")
USO_VM = "/var/lib/agentepessoal/uso.jsonl"
TAREFAS_VM = "/opt/a0/usr/scheduler/tasks.json"


def preco(modelo: str) -> tuple:
    modelo = str(modelo or "").lower()
    return next((v for k, v in PRECOS.items() if k in modelo), PRECOS["luna"])


def custo(u: dict) -> float:
    """US$ of one usage line, the same way as ponte_whatsapp.gasto()."""
    p = preco(u.get("modelo", ""))
    p_in, p_cache, p_out = p[:3]
    p_gravar = p[3] if len(p) > 3 else p_in * 1.25
    cache, gravado = u.get("cache", 0) or 0, u.get("cache_gravado", 0) or 0
    gravado_1h = min(gravado, u.get("cache_gravado_1h", 0) or 0)
    normal = max(0, (u.get("entrada", 0) or 0) - cache - gravado)
    return (normal * p_in + cache * p_cache + (gravado - gravado_1h) * p_gravar + gravado_1h * p_in * 2
            + (u.get("saida", 0) or 0) * p_out) / 1e6


def _quando(u: dict) -> float:
    return dt.datetime.fromisoformat(str(u["em"]).replace("Z", "+00:00")).timestamp()


def validade(anterior: dict) -> float:
    """Seconds the previous call's cache lives: Claude 5 min (1 h when it wrote with ttl 1h); GPT 30 min. 20/10: Bedrock
    accepts prompt_cache_retention 24h, but a test call 32 min later read nothing, so it is still counted as 30 min:
    a miss after more than 30 min shows as "expirou" either way, which is how the report tells whether 24h works."""
    if "anthropic" in str(anterior.get("modelo", "")) or anterior.get("api") == "converse":
        return 3600 if anterior.get("cache_gravado_1h") else 300
    return 1800


def causas(atual: dict, anterior: dict | None) -> list:
    """Why a call missed the cache, from the fingerprints of the start of the prompt (bedrock_proxy.impressao)."""
    if anterior is None:
        return ["1ª chamada"]
    out = [f"mudou {p}" for p in PARTES
           if (atual.get(p) or {}).get("todo") != (anterior.get(p) or {}).get("todo")
           and (atual.get(p) or anterior.get(p))]
    if (atual.get("mensagens") or 0) < (anterior.get("mensagens") or 0):
        out.append("histórico encurtado")
    parado = _quando(atual) - _quando(anterior)
    if parado > validade(anterior):
        out.append(f"expirou ({parado / 60:.0f} min parado)" if parado < 7200 else "expirou (+2 h parado)")
    return out or ["nada mudou no começo"]


def _causa_curta(c: str) -> str:
    return c.split(" (", 1)[0]


def origem(u: dict) -> str:
    if u.get("rotina"):
        return f"rotina {u['rotina']}"
    if u.get("conversa"):
        return f"conversa {u['conversa']}"
    return "sem origem (antes do rastreio ou fora do agente)"


def analisar(linhas, desde: float, nomes: dict | None = None) -> dict:
    """{origem: totals} over the usage lines since `desde` (epoch). Lines without the tracking fields fall into
    "sem origem"; their misses get no cause (there is nothing to compare)."""
    nomes = nomes or {}
    grupos = defaultdict(lambda: {"chamadas": 0, "entrada": 0, "cache": 0, "gravado": 0, "gravado_1h": 0,
                                  "custo": 0.0, "falhas": 0, "causas": Counter(), "modelos": Counter(), "dono": ""})
    ultimo = {}
    for linha in linhas:
        try:
            u = json.loads(linha)
            antes = _quando(u) < desde
        except Exception:
            continue
        fio = (u.get("conversa"), u.get("agente"), u.get("papel"), u.get("modelo")) if u.get("conversa") else None
        if u.get("status", 200) != 200:
            continue
        if antes:  # before the window: only the previous call to compare the window's first one with
            if fio:
                ultimo[fio] = u
            continue
        nome = origem(u)
        g = grupos[nome]
        g["chamadas"] += 1
        g["entrada"] += u.get("entrada", 0) or 0
        g["cache"] += u.get("cache", 0) or 0
        g["gravado"] += u.get("cache_gravado", 0) or 0
        g["gravado_1h"] += u.get("cache_gravado_1h", 0) or 0
        g["custo"] += custo(u)
        g["modelos"][str(u.get("modelo", "?")).split(".")[-1]] += 1
        g["dono"] = g["dono"] or u.get("dono", "")
        if u.get("rotina"):
            g["nome"] = nomes.get(u["rotina"], "")
        entrada = u.get("entrada", 0) or 0
        if entrada >= MINIMO and (u.get("cache", 0) or 0) < FALHA * entrada:
            g["falhas"] += 1
            for c in (causas(u, ultimo.get(fio)) if fio else ["sem rastreio"]):
                g["causas"][_causa_curta(c)] += 1
        if fio:
            ultimo[fio] = u
    return dict(grupos)


def texto(grupos: dict, horas: float, top: int = 25) -> str:
    total = sum(g["custo"] for g in grupos.values())
    chamadas = sum(g["chamadas"] for g in grupos.values())
    linhas = [f"Cache do prompt — últimas {horas:g} h: {chamadas} chamadas, US$ {total:.2f} estimados", ""]
    ordem = sorted(grupos.items(), key=lambda kv: -kv[1]["custo"])
    for nome, g in ordem[:top]:
        ent = g["entrada"] or 1
        rot = f" «{g['nome']}»" if g.get("nome") else ""
        dono = f" [{g['dono']}]" if g["dono"] else ""
        modelos = ", ".join(f"{m} {n}" for m, n in g["modelos"].most_common(3))
        linhas.append(f"{nome}{rot}{dono} — {modelos}")
        um_h = f" (1 h: {100 * g['gravado_1h'] / ent:.0f}%)" if g["gravado_1h"] else ""
        linhas.append(f"  {g['chamadas']} chamadas · lido {100 * g['cache'] / ent:.0f}% · gravado "
                      f"{100 * g['gravado'] / ent:.0f}%{um_h} · US$ {g['custo']:.2f} · {g['falhas']} falhas de cache")
        if g["causas"]:
            linhas.append("  falhas: " + ", ".join(f"{c} {n}" for c, n in g["causas"].most_common()))
    if len(ordem) > top:
        resto = ordem[top:]
        linhas.append(f"(+{len(resto)} origens, US$ {sum(g['custo'] for _, g in resto):.2f})")
    return "\n".join(linhas)


def nomes_rotinas(caminho: str) -> dict:
    try:
        with open(caminho, encoding="utf-8") as f:
            return {t.get("uuid"): str(t.get("name") or "")[:60] for t in (json.load(f).get("tasks") or [])}
    except Exception:
        return {}


def _arg(args: list, nome: str, padrao: str) -> str:
    return args[args.index(nome) + 1] if nome in args and len(args) > args.index(nome) + 1 else padrao


def local(args: list) -> str:
    horas = float(_arg(args, "--horas", "24"))
    desde = dt.datetime.now(dt.timezone.utc).timestamp() - horas * 3600
    with open(_arg(args, "--arquivo", USO_VM), encoding="utf-8") as f:
        grupos = analisar(f, desde, nomes_rotinas(_arg(args, "--tarefas", "")))
    return texto(grupos, horas, int(_arg(args, "--top", "25")))


def na_vm(args: list) -> str:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    from implantar import vm  # read only: this file runs over the log there; only the report comes back

    codigo = base64.b64encode(open(__file__, "rb").read()).decode()
    extra = f"--horas {float(_arg(args, '--horas', '24')):g} --top {int(_arg(args, '--top', '25'))}"
    return vm(f"echo {codigo} | base64 -d | python3 - --arquivo {USO_VM} --tarefas {TAREFAS_VM} {extra}", timeout=300)


if __name__ == "__main__":
    a = sys.argv[1:]
    print(local(a) if "--arquivo" in a else na_vm(a))
