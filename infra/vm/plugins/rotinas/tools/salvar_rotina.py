"""Save a routine as an Agent Zero skill (/a0/usr/skills/<name>/SKILL.md), read it, add a correction or adjust a passage.

A routine says when to use it, what it needs, the steps, how to check the result, what to deliver
and what needs the user's approval — the parts Grok Bot's skills document — plus the corrections
the user made over time, so the same mistake is not repeated. The rules live in helpers/rotinas.py
(shared with the end-of-chat reviewer); this tool turns their answers into messages for the agent.
"""

import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def rotinas():
    """helpers/rotinas.py, loaded again when the file changes (a deploy takes effect without restarting the agent)."""
    nome, caminho = "rotinas_helper", RAIZ / "helpers" / "rotinas.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _limpeza(r: dict) -> str:
    if not r.get("pede_reescrita"):
        return ""
    return (f" A rotina já acumula {r['n_correcoes']} correções: releia com `acao: ler`, reescreva os passos limpos já "
            "com as correções dentro deles e salve com `acao: salvar`, `consolidar: true` e a `versao` lida (a seção de "
            "correções sai; a versão anterior fica guardada).")


class SalvarRotina(Tool):
    async def execute(self, acao: str = "salvar", nome: str = "", descricao: str = "", quando_usar: str = "",
                      entradas: str = "", passos="", verificar: str = "", entregar: str = "", aprovacao: str = "",
                      gatilhos=None, correcao: str = "", trecho: str = "", novo: str = "", versao: str = "",
                      consolidar: bool = False, **kwargs) -> Response:
        R = rotinas()
        slug = R.slug(nome)
        acao = (acao or "salvar").lower()
        consolidar = consolidar is True or str(consolidar).strip().lower() in ("true", "1", "sim")
        dono = (self.agent.context.get_data("dono") or "").lower()
        por = dono or "usuário"

        def resp(texto: str) -> Response:
            return Response(message=texto, break_loop=False)

        if acao == "ler":
            lido = R.ler(nome)
            return resp(f"versao: {lido['hash']}\n\n{lido['texto']}" if lido else f"Rotina «{slug}» não existe.")

        if acao == "corrigir":
            r = R.corrigir(nome, correcao, por=por)
            return resp({"nao_existe": f"Rotina «{slug}» não existe. Use memory_save para guardar a correção.",
                         "vazia": "Informe `correcao`.",
                         "repetida": f"Essa correção já está na rotina «{slug}»; nada foi gravado.",
                         }.get(r["motivo"], f"Correção gravada na rotina «{slug}».") + _limpeza(r))

        if acao == "ajustar":
            r = R.ajustar(nome, trecho, novo, versao, por=por)
            return resp({"nao_existe": f"Rotina «{slug}» não existe.",
                         "nao_relida": f"A rotina «{slug}» não foi relida (ou mudou depois): leia com `acao: ler` e "
                                       "ajuste passando a `versao` que veio. Nada foi trocado.",
                         "vazio": "Informe `trecho` (o texto exato a trocar) e `novo`.",
                         "nao_achou": f"O trecho não está na rotina «{slug}». Nada foi trocado.",
                         "repetido": f"O trecho aparece {r.get('vezes')} vezes na rotina «{slug}»; mande um trecho "
                                     "maior. Nada foi trocado.",
                         }.get(r["motivo"], f"Rotina «{slug}» ajustada (versao nova: {r['hash']}).") + _limpeza(r))

        r = R.salvar(nome, descricao, passos, quando_usar=quando_usar, entradas=entradas, verificar=verificar,
                     entregar=entregar, aprovacao=aprovacao, gatilhos=gatilhos, dono=dono, consolidar=consolidar,
                     hash_lido=versao, por=por)
        if r["motivo"] == "incompleta":
            return resp("Para salvar informe ao menos `nome`, `descricao` e `passos`.")
        if r["motivo"] == "nao_relida":
            return resp(f"Para consolidar, releia a rotina «{slug}» com `acao: ler` e salve passando a `versao` que "
                        "veio. Nada foi gravado.")
        return resp(f"Rotina «{slug}» salva em {r['arquivo']}. Para usar: peça pelo nome ou digite /{slug}."
                    + (" Correções incorporadas aos passos; a versão anterior ficou guardada."
                       if r["motivo"] == "consolidada" else _limpeza(r)))
