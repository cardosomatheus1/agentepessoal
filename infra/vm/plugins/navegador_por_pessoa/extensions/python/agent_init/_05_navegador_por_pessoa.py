"""Install the per-person browser profile choice (idempotent; runs as agents start)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension


def perfis():
    nome = "navegador_por_pessoa_perfis"
    if nome not in sys.modules:
        caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "perfis.py"
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


class NavegadorPorPessoa(Extension):
    def execute(self, **kwargs):  # agent_init runs in sync mode: no async here
        p = perfis()
        if getattr(p, "_fora", "") not in ("ok", "ligado", "erro"):  # agents start before any browser opens
            try:
                estado = p.guardar_perfis_fora()
            except Exception as exc:  # never retried: the browser keeps working where it was
                estado = "erro"
                print(f"navegador_por_pessoa: perfis fora do contêiner falhou: {exc}", flush=True)
            if estado != getattr(p, "_fora", "") and estado not in ("ok", "erro"):
                print(f"navegador_por_pessoa: perfis do navegador: {estado}", flush=True)
            p._fora = estado
        try:
            if p.aplicar():
                print("navegador_por_pessoa: browser profiles are now per person", flush=True)
        except Exception as exc:
            print(f"navegador_por_pessoa: not applied: {exc}", flush=True)
