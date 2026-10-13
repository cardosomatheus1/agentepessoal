# uso: injeta.py <pasta_reel> '<lista JS de insertos>'
import sys,re
d,lista=sys.argv[1],sys.argv[2]
f=f"{d}/index.html";s=open(f).read()
s=re.sub(r"\n<!--INS-->.*?<!--/INS-->","",s,flags=re.S)
bloco=f"""
<!--INS--><script>
document.body.insertAdjacentHTML('beforeend',INS_HTML);
const _INS={lista};
const _render0=window.render;
window.render=async function(t){{await _render0(t);await insertos(t,_INS);}};
</script><!--/INS-->"""
s=s.replace("</body>",bloco+"\n</body>",1) if "</body>" in s else s+bloco
open(f,"w").write(s);print("ok",d)
