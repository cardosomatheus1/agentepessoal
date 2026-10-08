"""Mask the chat owner's vault values in the step log shown on screen (e.g. a terminal command
after §§secret(NAME) was replaced by the real value), the way Agent Zero masks its own secrets.

Wraps helpers.log.Log._mask_recursive once per process (idempotent)."""

MARCA = "_cofre_mascarar_log_v1"


def aplicar(cofre_modulo) -> None:
    from helpers import log

    if getattr(log.Log, MARCA, False):
        return
    original = log.Log._mask_recursive

    def _mask_recursive(self, obj):
        obj = original(self, obj)
        try:
            ctx = getattr(self, "context", None)
            dados = cofre_modulo.carregar(cofre_modulo.dono(ctx)) if ctx is not None else {}
            return _mascarar(obj, cofre_modulo, dados) if dados else obj
        except Exception:
            return obj

    log.Log._mask_recursive = _mask_recursive
    setattr(log.Log, MARCA, True)


def _mascarar(valor, c, dados):
    if isinstance(valor, str):
        return c.mascarar(valor, dados)
    if isinstance(valor, dict):
        return {k: _mascarar(v, c, dados) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_mascarar(v, c, dados) for v in valor]
    return valor
