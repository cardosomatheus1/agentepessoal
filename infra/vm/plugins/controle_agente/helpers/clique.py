"""12/10 evening: two rounds gave up ("PRECISA DE VOCÊ") because a browser click used a reference the page had already
re-rendered (Instagram rebuilds the profile after loading) and the agent retried the same reference. Any browser task
can hit this, so the hint rides on the failed click's own result.

21/10: the other browser failures get the same treatment, with the error catalogue OpenClaw uses
(extensions/browser/src/browser/pw-tools-core.shared.ts, toAIFriendlyError): each Playwright error becomes the next
step to take, instead of a raw message after which the agent gave up."""

import re

SUMIU = re.compile(r"could not find reference|element is not attached|"
                   r"element is detached|stale element", re.I)

DICA = ("\n\n↻ A página mudou depois que você a leu (ela se redesenha ao carregar): essa referência não existe mais. "
        "Não repita o mesmo clique. Leia a página de novo (`browser` content) e use a referência nova; se o elemento "
        "tem texto visível, clique por ele (selector `text=Mensagem`, por exemplo) ou rode um `evaluate` que acha pelo "
        "texto. Se ainda falhar, recarregue a página e tente de novo.")

# (pattern in the failure, next step). First match wins; SUMIU above comes first.
OUTROS = [
    # 21/10: 55 clicks failed like this and the hint said "the page changed", which was false: the selector simply
    # matches nothing the page reading numbered. (navegador_rapido now resolves click/type selectors on the page.)
    (re.compile(r"could not resolve selector", re.I),
     "↻ Esse seletor não corresponde a nenhum elemento numerado da leitura da página (a página não mudou). Leia a "
     "página (`browser` content) e use a ref do elemento, ou clique pelas coordenadas x,y do print."),
    (re.compile(r"strict mode violation|resolved to \d+ elements", re.I),
     "↻ O seletor achou mais de um elemento. Releia a página (`browser` content) e use a ref certa, ou um seletor mais "
     "específico (o nome do campo, `text=...` ou um atributo único)."),
    (re.compile(r"intercepts pointer events|not receiving pointer events|receive pointer events", re.I),
     "↻ Tem outra coisa por cima do elemento (aviso de cookies, janela, menu aberto). Feche-a ou role até o elemento "
     "(`scroll`), releia a página e tente de novo."),
    (re.compile(r"element is not visible|not visible", re.I),
     "↻ O elemento existe mas não aparece: role até ele, abra o menu ou aba que o mostra, ou feche o que o cobre; depois "
     "releia a página e use a ref nova."),
    (re.compile(r"not an <input>|not editable|cannot be filled|contenteditable", re.I),
     "↻ Esse elemento não aceita texto. Releia a página e digite no campo de texto certo (procure pelo nome do campo)."),
    (re.compile(r"input\[type=number\]|malformed value", re.I),
     "↻ O campo recusou o formato. Use só número (ou o formato que o campo pede, como data AAAA-MM-DD)."),
    (re.compile(r"element is not enabled|is disabled|not enabled", re.I),
     "↻ O controle está desativado. Complete antes o que o libera (campos obrigatórios, caixa de aceite, escolha "
     "anterior) e tente de novo."),
    (re.compile(r"cannot select options on|not a <select>|select_option", re.I),
     "↻ Essa lista não é um <select> de verdade (é feita pelo site). Clique nela para abrir, espere as opções "
     "(`wait` com o texto da opção) e clique na opção pelo texto (`text=...`) ou pelas coordenadas do print."),
    (re.compile(r"helper-backed reference|no visible viewport box|cannot resolve point", re.I),
     "↻ O elemento está dentro de um quadro embutido (iframe) ou sem área visível. Role até ele e clique pelas "
     "coordenadas x,y do print (`click` com x e y), ou abra o endereço do quadro direto numa aba."),
    (re.compile(r"does not resolve to a file input|cannot upload files", re.I),
     "↻ Para enviar arquivo use `upload_file` só com o `path` (sem ref): o arquivo vai no campo de arquivo da página, "
     "mesmo escondido. Se não houver campo, clique antes no botão de anexar."),
    (re.compile(r"Timeout \d+ms exceeded", re.I),
     "↻ Esperou e o elemento não ficou pronto. Releia a página: pode ter mudado de aba, aberto uma janela ou precisar "
     "rolar. Use a ref nova."),
]


def dica(tool_name: str, mensagem: str) -> str:
    """The next step to add to a failed browser action, or ''."""
    mensagem = mensagem or ""
    if tool_name != "browser" or "↻" in mensagem or "failed" not in mensagem.lower() and not SUMIU.search(mensagem):
        return ""
    if SUMIU.search(mensagem):
        return DICA
    for padrao, texto in OUTROS:
        if padrao.search(mensagem):
            return "\n\n" + texto
    return ""
