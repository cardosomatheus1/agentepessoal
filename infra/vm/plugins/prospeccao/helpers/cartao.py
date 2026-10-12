"""The hot lead's card as a one-page PDF (12/10 review §7 item 3): written with python-docx and converted by
LibreOffice (both in the agent container), from prospeccao.cartao_lead()."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PASTA = Path("/a0/usr/prospeccao/cartoes")
GUARDAR_DIAS = 30


# One page always: a full card is tried again smaller, keeping the most recent part of the conversation
TENTATIVAS = ((10, 8), (9, 6), (8.5, 4), (8, 3))  # (font size, conversation entries)


def _paginas(pdf: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        return 1  # cannot count: keep the first try
    return len(PdfReader(str(pdf)).pages)


def gerar_pdf(dados: dict, destino: Path) -> str:
    """'' when the one-page PDF was written to `destino`, else why not."""
    try:
        import docx  # noqa: F401
    except ImportError:
        return "python-docx indisponível"
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return "LibreOffice indisponível"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cartao-") as tmp:
        for tamanho, conversa in TENTATIVAS:
            fonte = Path(tmp) / (destino.stem + ".docx")
            _documento({**dados, "conversa": dados["conversa"][-conversa:]}, tamanho).save(fonte)
            # its own LibreOffice profile: another instance running (e.g. the office plugin) does not block this one
            perfil = f"-env:UserInstallation=file://{tmp}/perfil"
            try:
                r = subprocess.run([soffice, perfil, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(fonte)],
                                   capture_output=True, text=True, timeout=180, env={**os.environ, "HOME": tmp})
            except (OSError, subprocess.TimeoutExpired) as exc:
                return f"conversão falhou: {exc}"
            pdf = Path(tmp) / (destino.stem + ".pdf")
            if not pdf.exists():
                return f"conversão falhou: {(r.stderr or r.stdout).strip()[:200]}"
            if _paginas(pdf) == 1 or (tamanho, conversa) == TENTATIVAS[-1]:
                shutil.move(str(pdf), destino)
                return ""
            pdf.unlink()
    return "não coube em 1 página"


def _documento(dados: dict, tamanho: float):
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Cm(1.4)
        sec.left_margin = sec.right_margin = Cm(1.8)
    estilo = doc.styles["Normal"]
    estilo.font.name, estilo.font.size = "Arial", Pt(tamanho)
    estilo.paragraph_format.space_after = Pt(2)
    cinza = RGBColor(0x55, 0x55, 0x55)

    titulo = doc.add_paragraph()
    t = titulo.add_run(f"{dados['nome']}  (@{dados['handle']})")
    t.bold, t.font.size = True, Pt(tamanho + 5)
    linha = " · ".join(x for x in (dados["etapa"].upper(), dados["segmento"], dados["cidade"],
                                   f"{dados['seguidores']} seguidores" if dados["seguidores"] else "",
                                   f"nota {dados['nota']}" if dados["nota"] else "", f"fonte: {dados['fonte']}") if x)
    sub = doc.add_paragraph().add_run(linha)
    sub.font.color.rgb = cinza
    if dados.get("url"):
        doc.add_paragraph().add_run(dados["url"]).font.color.rgb = cinza

    def secao(nome: str) -> None:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(tamanho * 0.7)
        r = p.add_run(nome)
        r.bold, r.font.size = True, Pt(tamanho + 1.5)

    secao("Por que encaixa")
    doc.add_paragraph(dados["motivo"] or "—")
    if dados.get("post_recente") or dados.get("vistos"):
        secao("O que vimos no perfil")
        for v in ([dados["post_recente"]] if dados.get("post_recente") else []) + dados.get("vistos", []):
            doc.add_paragraph(v, style="List Bullet")
    secao("A conversa até aqui")
    if not dados["conversa"]:
        doc.add_paragraph("—")
    for c in dados["conversa"]:
        p = doc.add_paragraph()
        cab = p.add_run(f"{c['quando']} · {c['quem']}: ")
        cab.bold = True
        p.add_run(f"«{c['texto']}»")
    secao("Próximo passo")
    doc.add_paragraph(dados["proximo_passo"])
    if dados.get("proxima"):
        p = doc.add_paragraph()
        p.add_run("Mensagem sugerida: ").bold = True
        p.add_run(f"«{dados['proxima']}»")
    rodape = doc.add_paragraph().add_run(f"Gerado em {dados['gerado']} a partir do registro da prospecção. "
                                         "Para falar você mesmo, toque em «Deixa comigo» no aviso.")
    rodape.font.size, rodape.font.color.rgb = Pt(7.5), cinza
    return doc


def limpar_antigos(agora: float) -> None:
    for velho in PASTA.glob("*.pdf") if PASTA.exists() else []:
        if agora - velho.stat().st_mtime > GUARDAR_DIAS * 86400:
            velho.unlink(missing_ok=True)
