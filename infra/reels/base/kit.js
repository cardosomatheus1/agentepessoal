const $=id=>document.getElementById(id);
const $$=(s,r=document)=>[...r.querySelectorAll(s)];
const cl=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const p=(t,a,d)=>cl((t-a)/d);
const eo=x=>1-Math.pow(1-x,3);
const eo5=x=>1-Math.pow(1-x,5);
const eio=x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;
const eb=x=>{const c=1.70158,c3=c+1;return 1+c3*Math.pow(x-1,3)+c*Math.pow(x-1,2)};
const el=x=>x===0?0:x===1?1:Math.pow(2,-10*x)*Math.sin((x*10-.75)*2*Math.PI/3)+1;
const lerp=(a,b,x)=>a+(b-a)*x;
const brl=v=>(v<-0.004?'-':'')+'R$ '+Math.abs(v).toFixed(2).replace('.',',');
const brl0=v=>(v<-0.4?'-':'')+'R$ '+Math.round(Math.abs(v));
const rnd=i=>{const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x)};
// quebra o texto de .rv em palavras com máscara
function prepara(){$$('.rv').forEach(e=>{if(e.dataset.ok)return;e.dataset.ok=1;
  const walk=n=>{[...n.childNodes].forEach(c=>{if(c.nodeType===3){const f=document.createDocumentFragment();c.textContent.split(/(\s+)/).forEach(w=>{if(!w)return;if(/^\s+$/.test(w)){f.appendChild(document.createTextNode(w));return}
    const a=document.createElement('span');a.className='ww';const b=document.createElement('span');b.className='wi';b.textContent=w;a.appendChild(b);f.appendChild(a)});c.replaceWith(f)}else if(c.nodeType===1&&c.tagName!=='BR')walk(c)})};walk(e)})}
// revela as palavras de um elemento a partir de t0
function revela(e,t,t0,pass=0.07,dur=0.55){const ws=$$('.wi',e);ws.forEach((w,i)=>{const q=eo5(p(t,t0+i*pass,dur));w.style.transform=`translateY(${(1-q)*115}%) rotate(${(1-q)*7}deg)`;})}
// cena com entrada em círculo e "câmera"
function cena(id,t,a,b,{x=540,y=960,ent=0.5,push=0.05,saida=true}={}){const e=$(id);const on=t>=a&&t<(saida?b+0.5:1e9);e.style.opacity=on?1:0;if(!on)return 0;
  const q=eio(p(t,a,ent));e.style.clipPath=q<1?`circle(${q*2300}px at ${x}px ${y}px)`:'none';
  const c=e.querySelector('.cam');if(c){const k=p(t,a,b-a+0.5);c.style.transform=`scale(${1+push*k+0.06*(1-eo(p(t,a,ent+0.3)))})`}
  return q}
// grão, bokeh
function fx(t){const g=$('grao');if(g){const i=Math.floor(t*24);g.style.transform=`translate(${(rnd(i)*320)|0}px,${(rnd(i+9)*320)|0}px)`}}
function bokeh(id,n,cores,seed=1){const c=$(id);let h='';for(let i=0;i<n;i++){const s=30+rnd(i+seed)*170;h+=`<div class="bok" data-i="${i}" style="width:${s}px;height:${s}px;background:${cores[i%cores.length]};filter:blur(${6+rnd(i*3+seed)*26}px);opacity:${.08+rnd(i*7+seed)*.25}"></div>`}c.innerHTML=h}
function bokehMove(id,t,seed=1){$$('.bok',$(id)).forEach(b=>{const i=+b.dataset.i;const x=rnd(i*5+seed)*1180-50+Math.sin(t*0.3+i)*40,y=rnd(i*11+seed)*2000-40-t*(10+rnd(i)*30);b.style.transform=`translate(${x}px,${((y%2100)+2100)%2100-100}px)`})}
// brilho no botão
function brilho(btn,t,t0){const i=btn.querySelector('i');if(!i)return;const k=((t-t0)%2.2)/2.2;i.style.left=(-20+k*140)+'%';const pu=t>t0?(Math.sin((t-t0)*4.5)+1)/2:0;btn.style.transform=`scale(${1+0.04*pu})`}
// quadros do vídeo de fundo (img + pasta de jpgs)
const VID={};
function quadro(img,pasta,n,t,fps=30){const k=Math.floor(t*fps);const per=2*(n-1);let i=k%per;if(i>=n)i=per-i;const src=`${pasta}/q${String(i+1).padStart(4,'0')}.jpg`;
  if(img.getAttribute('src')!==src){img.setAttribute('src',src);return img.decode().catch(()=>{})}return Promise.resolve()}
// corte para filmagem real (insert) por cima da cena: L=[{de,dur,pasta,cap,n,off}]
const INS_HTML=`<div id="ins" style="position:absolute;inset:0;z-index:70;opacity:0;background:#000">
 <img id="insBg" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:blur(40px) brightness(.45) saturate(1.2);transform:scale(1.25)">
 <div id="insBand" style="position:absolute;left:0;top:640px;width:1080px;height:608px;overflow:hidden;box-shadow:0 40px 120px rgba(0,0,0,.8)"><img id="insImg" style="width:100%;height:100%;object-fit:cover;filter:saturate(1.15) contrast(1.06)"></div>
 <div id="insCap" class="glass" style="position:absolute;left:90px;right:90px;top:1320px;padding:34px 30px;text-align:center;font-size:60px;font-weight:900;line-height:1.1"></div></div>`;
function insertos(t,L){const box=$('ins');let a=null;for(const x of L){if(t>=x.de&&t<x.de+x.dur){a=x;break}}
 if(!a){box.style.opacity=0;return Promise.resolve()}
 const k=t-a.de;const qi=eio(p(k,0,0.28)),qo=eio(p(k,a.dur-0.22,0.22));
 box.style.opacity=1;box.style.clipPath=`circle(${qi*(1-qo)*2300}px at 540px 960px)`;
 $('insBand').style.transform=`scale(${1.02+0.06*(k/a.dur)})`;
 const cp=$('insCap');cp.innerHTML=a.cap;const c=eo5(p(k,0.12,0.4));cp.style.transform=`translateY(${(1-c)*60}px)`;cp.style.opacity=c;
 const tt=k+(a.off||0);return Promise.all([quadro($('insImg'),a.pasta,a.n||358,tt),quadro($('insBg'),a.pasta,a.n||358,tt)])}
