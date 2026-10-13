#!/usr/bin/env python3
"""Runs every test ficha of every template (or of the ones named) through the check, in preview mode.

    python3 testar.py                 # all templates
    python3 testar.py oferta combo    # some
    python3 testar.py --video oferta  # also renders the full videos/slides

A template passes when it has 3 or more test fichas, from at least 2 brands (2 styles), every ficha passes the
check, every format in esquema.json is covered by some ficha, a ficha in exemplos/recusadas/ is refused by the ficha check and one in
exemplos/recusadas-molde/ by the template itself (render exits 2).
Also checks that every template in catalogo.json has a folder. Exit 1 if anything fails.
"""
import json, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "motor"))
from validar import validar  # noqa: E402


def moldes():
    return sorted(p.name for p in RAIZ.iterdir() if (p / "molde.html").exists())


def testar(m, video=False):
    falhas, pasta = [], RAIZ / m
    esquema = json.loads((pasta / "esquema.json").read_text())
    fichas = sorted((pasta / "exemplos").glob("*.json"))
    if len(fichas) < 3: falhas.append(f"só {len(fichas)} fichas de teste (mínimo 3)")
    marcas, formatos = set(), set()
    for f in fichas:
        d = json.loads(f.read_text())
        marcas.add(d.get("_marca")); formatos.add(d.get("_formato") or esquema["formatos"][0])
        cmd = [sys.executable, str(RAIZ / "motor" / "render.py"), m, str(f)] + ([] if video else ["--previa"])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            falhas.append(f"{f.name}: " + (r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or ["erro"])[-1][:300] + ("" if r.returncode in (2, 3) else " | " + r.stderr.strip()[-400:]))
    if len(marcas) < 2: falhas.append("fichas de uma marca só (use pelo menos 2 marcas)")
    falta = set(esquema["formatos"]) - formatos
    if falta: falhas.append(f"formato sem ficha de teste: {sorted(falta)}")
    for f in sorted((pasta / "exemplos" / "recusadas").glob("*.json")) if (pasta / "exemplos" / "recusadas").exists() else []:
        if not validar(esquema, json.loads(f.read_text())): falhas.append(f"recusadas/{f.name}: deveria ser recusada e passou")
    # data the template itself refuses ($m.erro: deadline past, combo dearer, missing confirmation): render must exit 2
    for f in sorted((pasta / "exemplos" / "recusadas-molde").glob("*.json")) if (pasta / "exemplos" / "recusadas-molde").exists() else []:
        r = subprocess.run([sys.executable, str(RAIZ / "motor" / "render.py"), m, str(f), "--previa", "--saida", str(pasta / "saida" / ("recusada-" + f.stem))], capture_output=True, text=True, timeout=600)
        if r.returncode != 2: falhas.append(f"recusadas-molde/{f.name}: o molde deveria recusar (saída {r.returncode})")
    return falhas


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    video = "--video" in sys.argv
    cat = json.loads((RAIZ / "catalogo.json").read_text())
    alvo = args or moldes()
    total = 0
    if not args:
        sem = [x["id"] for x in cat["moldes"] if not (RAIZ / x["id"] / "molde.html").exists()]
        if sem: print(f"✗ catálogo: {len(sem)} moldes sem pasta: {', '.join(sem)}"); total += 1
    for m in alvo:
        f = testar(m, video)
        print(("✓ " if not f else "✗ ") + m + ("" if not f else "\n    " + "\n    ".join(f)), flush=True)
        total += bool(f)
    print(f"{len(alvo) - total if not args else len(alvo) - total}/{len(alvo)} moldes ok")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
