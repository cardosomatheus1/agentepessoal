# uso: gen.py <pasta>  (pasta/falas.json = {"voz":"Camila","motor":"generative","falas":[...]})
import json, subprocess, sys, os
d=sys.argv[1]; c=json.load(open(f"{d}/falas.json"))
dur=[]
for i,f in enumerate(c["falas"]):
    mp=f"{d}/c{i}.mp3"
    if not os.path.exists(mp) or c.get("refazer"):
        subprocess.run(["aws","polly","synthesize-speech","--region","us-east-1","--engine",c.get("motor","generative"),"--voice-id",c["voz"],"--output-format","mp3","--sample-rate","24000","--text",f,mp],check=True,capture_output=True)
    dur.append(float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",mp]))+c.get("pausa",0.2))
dur[-1]+=1.2
S=[0]
for x in dur: S.append(round(S[-1]+x,3))
open(f"{d}/tempos.js","w").write(f"const S={json.dumps(S)};\n")
n=len(dur); ins=sum([["-i",f"{d}/c{i}.mp3"] for i in range(n)],[])
af=";".join(f"[{i}:a]apad=whole_dur={x:.3f}[a{i}]" for i,x in enumerate(dur))+";"+"".join(f"[a{i}]" for i in range(n))+f"concat=n={n}:v=0:a=1[aud]"
subprocess.run(["ffmpeg","-v","error","-y"]+ins+["-filter_complex",af,"-map","[aud]",f"{d}/voz.m4a"],check=True)
print(d, S)
