"""Let presets ask the OpenAI-compatible models for reasoning effort xhigh and max.

Agent Zero only knows minimal/low/medium/high and silently turns anything else into high, while the
Bedrock GPT models also accept xhigh and max. The allowed set is a module-level set read at call time,
so adding to it once per server is enough (idempotent).
"""

from helpers.extension import Extension


class EsforcoMaximo(Extension):
    def execute(self, **kwargs):
        try:
            from helpers import litellm_transport

            if not {"xhigh", "max"} <= litellm_transport.RESPONSES_REASONING_EFFORTS:
                litellm_transport.RESPONSES_REASONING_EFFORTS.update({"xhigh", "max"})
                print("controle_agente: esforço xhigh/max liberado", flush=True)
        except Exception as exc:  # never block the agent over this
            print(f"controle_agente: esforço máximo indisponível: {exc}", flush=True)
