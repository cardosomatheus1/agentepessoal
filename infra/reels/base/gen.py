# uso: gen.py <pasta>  (pasta/falas.json = {"voz":"carolina","motor":"nova-sonic","falas":[...]})
# Narração: Carolina, do Amazon Nova 2 Sonic, em todo vídeo dublado (Matheus, 14/10). A leitura é conferida palavra
# por palavra e refeita se a voz trocar algo (moldes/motor/render.py: narrar_sonic).
import json, subprocess, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "moldes" / "motor"))
from render import VOZ_PADRAO, narrar_sonic  # noqa: E402

d=sys.argv[1]; c=json.load(open(f"{d}/falas.json"))
voz = c.get("voz") if c.get("motor") == "nova-sonic" else VOZ_PADRAO["id"]  # Polly antigo vira Carolina
dur=[]
for i,f in enumerate(c["falas"]):
    wav=Path(f"{d}/c{i}.wav")
    if not wav.exists() or c.get("refazer"):
        narrar_sonic(f, voz, wav)
    dur.append(float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(wav)]))+c.get("pausa",0.2))
dur[-1]+=1.2
S=[0]
for x in dur: S.append(round(S[-1]+x,3))
open(f"{d}/tempos.js","w").write(f"const S={json.dumps(S)};\n")
n=len(dur); ins=sum([["-i",f"{d}/c{i}.wav"] for i in range(n)],[])
af=";".join(f"[{i}:a]apad=whole_dur={x:.3f}[a{i}]" for i,x in enumerate(dur))+";"+"".join(f"[a{i}]" for i in range(n))+f"concat=n={n}:v=0:a=1[aud]"
subprocess.run(["ffmpeg","-v","error","-y"]+ins+["-filter_complex",af,"-map","[aud]",f"{d}/voz.m4a"],check=True)
print(d, S)
