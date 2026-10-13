const $=id=>document.getElementById(id);
const cl=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const p=(t,a,d)=>cl((t-a)/d);
const eo=x=>1-Math.pow(1-x,3);
const eio=x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;
const eb=x=>{const c=1.70158,c3=c+1;return 1+c3*Math.pow(x-1,3)+c*Math.pow(x-1,2)};
const lerp=(a,b,x)=>a+(b-a)*x;
const brl=v=>(v<-0.004?'-':'')+'R$ '+Math.abs(v).toFixed(2).replace('.',',');
const brl0=v=>(v<-0.4?'-':'')+'R$ '+Math.round(Math.abs(v));
function set(el,o,y=0,s=1,x=0,r=0){el.style.opacity=o;el.style.transform=`translate(${x}px,${y}px) scale(${s}) rotate(${r}deg)`}
// visibilidade de um bloco do início da cena a até o fim da cena b
function vis(t,a,b=a,ind=0.35,outd=0.25){const i=eo(p(t,S[a],ind)),o=p(t,S[b+1]-outd,outd);return {i,o,v:i*(1-o)}}
