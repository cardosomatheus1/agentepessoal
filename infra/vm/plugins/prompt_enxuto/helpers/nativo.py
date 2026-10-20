"""Native tool calling for Claude on Bedrock through our proxy (20/10).

What Agent Zero does (agent.call_chat_model_turn + helpers/litellm_transport.py, read in the container on 20/10):
- the native function tools only go when the model's `a0_api_mode` is "responses";
- every chat call asks for explicit prompt caching, which puts `cache_control` on the messages; for a provider that
  takes cache markers (bedrock is one) and is not a native Responses provider, `TransportPolicy.from_request` then
  switches to Chat Completions (`_should_preserve_cache_control_on_chat`), and the Chat Completions request drops
  `a0_responses_function_tools` without turning them into `tools`: the model gets no tools at all and still the
  text-mode prompt. Responses mode on Bedrock was, in practice, text mode.
- without the markers it stays on Responses: LiteLLM's Responses bridge sends the tools as Converse toolConfig and
  the model's toolUse comes back as a function call that Agent Zero runs (tested in the container, 20/10).

Our proxy (infra/vm/bedrock_proxy.py, com_cache) already puts the cache points on every Converse call that has none
(end of the system prompt and of the last message; 1 hour for a person's chat), so Agent Zero's own markers are not
needed there. `sem_marcas_do_a0` says when to leave them out: Responses mode + Bedrock + our proxy. Anything else
(another provider, the proxy not in the way, text mode) keeps Agent Zero's markers."""

RESPONSES = {"response", "responses", "responses_api"}  # helpers/litellm_transport.RESPONSES_ALIASES
PROXY = ":8787/bedrock"  # the VM proxy (infra/vm/bedrock_proxy.py), which adds the Converse cache points


def sem_marcas_do_a0(modelo) -> bool:
    """The chat model sends native tools to Claude on Bedrock through our proxy: Agent Zero's cache markers would make
    it drop the tools, and the proxy caches anyway. Unknown = False (nothing changes)."""
    try:
        kwargs = getattr(modelo, "kwargs", None)
        if not isinstance(kwargs, dict):
            return False
        if str(kwargs.get("a0_api_mode") or "").lower().strip() not in RESPONSES:
            return False
        nome = str(getattr(modelo, "model_name", "") or "").lower()
        provedor = str(kwargs.get("custom_llm_provider") or "").lower() or nome.split("/", 1)[0]
        base = str(kwargs.get("api_base") or kwargs.get("base_url") or "").lower().rstrip("/")
        return provedor == "bedrock" and base.endswith(PROXY)
    except Exception:
        return False
