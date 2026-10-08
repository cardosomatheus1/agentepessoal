"""Save a routine as an Agent Zero skill (/a0/usr/skills/<name>/SKILL.md), or add a correction.

A routine says when to use it, what it needs, the steps, how to check the result, what to deliver
and what needs the user's approval — the parts Grok Bot's skills document — plus the corrections
the user made over time, so the same mistake is not repeated.
"""

import re
import time
from pathlib import Path

from helpers.tool import Response, Tool

SKILLS = Path("/a0/usr/skills")


def _slug(nome: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", nome.lower().translate(str.maketrans("áàâãéêíóôõúçü", "aaaaeeiooouuc"))).strip("-")
    return s[:50] or "rotina"


def _lista(texto) -> str:
    if isinstance(texto, list):
        return "\n".join(f"{i}. {p}" for i, p in enumerate(texto, 1))
    return str(texto or "").strip()


class SalvarRotina(Tool):
    async def execute(self, acao: str = "salvar", nome: str = "", descricao: str = "", quando_usar: str = "",
                      entradas: str = "", passos="", verificar: str = "", entregar: str = "", aprovacao: str = "",
                      gatilhos=None, correcao: str = "", **kwargs) -> Response:
        slug = _slug(nome)
        arquivo = SKILLS / slug / "SKILL.md"
        acao = (acao or "salvar").lower()
        if acao == "corrigir":
            if not arquivo.exists():
                return Response(message=f"Rotina «{slug}» não existe. Use memory_save para guardar a correção.", break_loop=False)
            if not correcao.strip():
                return Response(message="Informe `correcao`.", break_loop=False)
            texto = arquivo.read_text(encoding="utf-8").rstrip()
            if "## Correções do usuário" not in texto:
                texto += "\n\n## Correções do usuário (valem acima dos passos)"
            texto += f"\n- {time.strftime('%d/%m/%Y')}: {correcao.strip()}"
            arquivo.write_text(texto + "\n", encoding="utf-8")
            return Response(message=f"Correção gravada na rotina «{slug}».", break_loop=False)

        if not (nome and descricao and passos):
            return Response(message="Para salvar informe ao menos `nome`, `descricao` e `passos`.", break_loop=False)
        gat = [g for g in (gatilhos or []) if str(g).strip()] if isinstance(gatilhos, list) else \
              [g.strip() for g in str(gatilhos or "").split(",") if g.strip()]
        dono = (self.agent.context.get_data("dono") or "").lower()
        frente = ["---", f"name: {slug}", f'description: "{descricao.strip().replace(chr(34), chr(39))}"',
                  "version: 1.0.0", f'tags: ["rotina"{", " + chr(34) + dono + chr(34) if dono else ""}]']
        if gat:
            frente.append("trigger_patterns:")
            frente += [f'  - "{g}"' for g in gat[:12]]
        frente.append("---")
        corpo = [f"# {nome.strip()}", "",
                 f"Rotina salva em {time.strftime('%d/%m/%Y')}" + (f" por {dono}" if dono else "") + ".", "",
                 "## Quando usar", quando_usar.strip() or descricao.strip(), "",
                 "## Entradas e acessos", entradas.strip() or "(nenhuma)", "",
                 "## Passos", _lista(passos), "",
                 "## Como verificar que deu certo", verificar.strip() or "(confira o resultado antes de entregar)", "",
                 "## O que entregar", entregar.strip() or "(resumo curto do que foi feito)", "",
                 "## Precisa de aprovação do usuário", aprovacao.strip() or "(siga as regras de aprovações)"]
        anterior = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
        if "## Correções do usuário" in anterior:  # keep what the user taught on re-save
            corpo += ["", anterior[anterior.index("## Correções do usuário"):].strip()]
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text("\n".join(frente + corpo) + "\n", encoding="utf-8")
        return Response(message=f"Rotina «{slug}» salva em {arquivo}. Para usar: peça pelo nome ou digite /{slug}.",
                        break_loop=False)
