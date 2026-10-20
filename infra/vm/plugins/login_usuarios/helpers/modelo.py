"""Which model a chat uses, by owner and by chat (20/10). Ready and OFF: with no file (or an empty one) nothing changes.

The file /a0/usr/plugins/login_usuarios/modelo_por_dono.json names presets of Agent Zero's model switcher
(_model_config, presets.yaml), never model ids or keys:

    {"donos": {"matheus": "Sonnet"}, "conversas": {"<chat id>": "Default"}, "rotinas": false}

- "conversas" wins over "donos"; "rotinas": true also applies the owner's preset to scheduled rounds (off by default:
  routines stay on the default model);
- it works through the chat's own preset choice (`chat_model_override`), the same one the switcher in the UI sets, and
  marks what it set (`modelo_auto`, saved with the chat): a choice made by hand in the UI is never changed or removed;
- a preset that does not exist leaves the chat on the default (the switcher ignores it).

To turn on: create the preset in the UI (e.g. "Sonnet") and write the file. To turn off: delete the file (each chat
it changed goes back to the default at its next message)."""

import json
from pathlib import Path

ARQUIVO = Path("/a0/usr/plugins/login_usuarios/modelo_por_dono.json")
CHAVE = "chat_model_override"
AUTO = "modelo_auto"


def ler(arquivo: Path | None = None) -> dict:
    try:
        dados = json.loads((arquivo or ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def preset_para(cfg: dict, dono: str, ctx_id: str, rotina: bool) -> str:
    conversas = cfg.get("conversas") if isinstance(cfg.get("conversas"), dict) else {}
    donos = cfg.get("donos") if isinstance(cfg.get("donos"), dict) else {}
    nome = conversas.get(ctx_id)
    if not nome and (not rotina or cfg.get("rotinas") is True):
        nome = donos.get((dono or "").strip().lower())
    return str(nome).strip() if isinstance(nome, str) and nome.strip() else ""


def aplicar(ctx, dono: str, rotina: bool, cfg: dict) -> str:
    """Set or clear the chat's preset. Returns what happened: "", "ligou:<preset>", "desligou" or "manual"."""
    atual = ctx.get_data(CHAVE)
    marcado = ctx.get_data(AUTO)
    nosso = bool(marcado) and isinstance(atual, dict) and atual.get("preset_name") == marcado
    if atual and not nosso:
        return "manual"  # chosen by hand in the UI: never touched
    alvo = preset_para(cfg, dono, ctx.id, rotina)
    if alvo:
        if nosso and marcado == alvo:
            return ""
        ctx.set_data(CHAVE, {"preset_name": alvo})
        ctx.set_data(AUTO, alvo)
        return f"ligou:{alvo}"
    if nosso:
        ctx.set_data(CHAVE, None)
        ctx.set_data(AUTO, None)
        return "desligou"
    if marcado:
        ctx.set_data(AUTO, None)
    return ""
