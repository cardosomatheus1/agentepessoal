// Motor da Constelação (23/10): a cena Three.js da Pasta. Os itens são instâncias de um quadradinho desenhado no
// shader (ponto ou traço arredondado, sempre de frente para a câmera); os arquivos são hexágonos; o núcleo é um sol;
// o brilho é bloom de verdade (UnrealBloomPass). Mudar de visão faz cada item voar da pose antiga para a nova.
// Os rótulos são HTML por cima (texto nítido), reposicionados a cada quadro. Só leitura: nada sai daqui.
import type { GrafoCerebro } from "@/lib/brain-graph.mjs";
import { corDoTipo, maisPerto, misturar, suavizar, type Cena, type Modo, type Pose, type PoseHex } from "@/lib/constelacao.mjs";

export type Realce = { escolhido: string | null; sobre: string | null; busca: Set<string> | null };
export type Motor = { irPara: (modo: Modo, imediato?: boolean) => void; realcar: (r: Realce) => void; tecla: (k: string) => void; destruir: () => void };

const FUNDO = 0x0a100d;
const DURACAO = 1.25; // segundos de voo entre visões
const TAM_ITEM = 0.0105;
const TAM_HEX = 0.03;
// Câmera de cada visão: elevação (0 = de frente) e se gira sozinha.
const CAMERA: Record<Modo, { elev: number; gira: boolean }> = { disco: { elev: 0, gira: false }, forca: { elev: 0, gira: false }, aneis: { elev: 0.62, gira: true } };

const VERT_ITEM = /* glsl */ `
attribute vec3 aDe; attribute vec3 aPara; attribute vec4 aFormaDe; attribute vec4 aFormaPara;
attribute vec3 aCor; attribute float aBrilho;
uniform float uT; uniform float uTam; uniform float uZoom;
varying vec2 vUv; varying vec3 vCor; varying float vBrilho; varying vec2 vEsc;
float suave(float t) { return t < 0.5 ? 4.0 * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0; }
void main() {
  float k = suave(clamp(uT, 0.0, 1.0));
  vec3 p = mix(aDe, aPara, k);
  float da = atan(sin(aFormaPara.x - aFormaDe.x), cos(aFormaPara.x - aFormaDe.x));
  float ang = aFormaDe.x + da * k;
  vec2 esc = mix(aFormaDe.yz, aFormaPara.yz, k);
  vUv = uv; vCor = aCor; vBrilho = aBrilho; vEsc = esc;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  float c = cos(ang), s = sin(ang);
  vec2 q = position.xy * esc * uTam * 2.4 * mix(1.0, 1.6, smoothstep(1.2, 2.2, aBrilho));
  mv.xy += vec2(c * q.x - s * q.y, s * q.x + c * q.y);
  gl_Position = projectionMatrix * mv;
}`;
const FRAG_ITEM = /* glsl */ `
varying vec2 vUv; varying vec3 vCor; varying float vBrilho; varying vec2 vEsc;
void main() {
  vec2 q = (vUv - 0.5) * 2.4 * vEsc;
  vec2 h = vEsc * 0.5;
  float r = min(h.x, h.y);
  vec2 dq = abs(q) - (h - r);
  float d = (length(max(dq, 0.0)) + min(max(dq.x, dq.y), 0.0) - r) / r;
  float miolo = smoothstep(0.18, -0.18, d);
  float halo = exp(-max(d, 0.0) * 2.6) * 0.32;
  float a = (miolo + halo) * clamp(vBrilho, 0.0, 1.0);
  if (a < 0.004) discard;
  gl_FragColor = vec4(vCor * (miolo * (0.75 + 0.55 * vBrilho) + halo), a);
}`;
const VERT_HEX = /* glsl */ `
attribute vec3 aDe; attribute vec3 aPara; attribute vec2 aTam; attribute vec3 aCor; attribute float aBrilho;
uniform float uT; uniform float uTam;
varying vec2 vUv; varying vec3 vCor; varying float vBrilho;
float suave(float t) { return t < 0.5 ? 4.0 * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0; }
void main() {
  float k = suave(clamp(uT, 0.0, 1.0));
  vec3 p = mix(aDe, aPara, k);
  vUv = uv; vCor = aCor; vBrilho = aBrilho;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  mv.xy += position.xy * mix(aTam.x, aTam.y, k) * uTam * 2.6 * mix(1.0, 1.35, smoothstep(1.2, 2.2, aBrilho));
  gl_Position = projectionMatrix * mv;
}`;
const FRAG_HEX = /* glsl */ `
varying vec2 vUv; varying vec3 vCor; varying float vBrilho;
float hexa(vec2 p, float r) {
  const vec3 k = vec3(-0.866025404, 0.5, 0.577350269);
  p = abs(p.yx); p -= 2.0 * min(dot(k.xy, p), 0.0) * k.xy; p -= vec2(clamp(p.x, -k.z * r, k.z * r), r);
  return length(p) * sign(p.y);
}
void main() {
  vec2 p = (vUv - 0.5) * 2.6;
  float d = hexa(p, 0.78);
  float borda = smoothstep(0.075, 0.0, abs(d + 0.03));
  float dentro = smoothstep(0.02, -0.02, d);
  float halo = exp(-max(d, 0.0) * 9.0) * 0.45;
  float v = clamp(vBrilho, 0.0, 1.0);
  vec3 cor = mix(vec3(0.045, 0.07, 0.06), vCor * 0.18, 0.5) * dentro + vCor * (borda * (0.9 + 0.6 * vBrilho) + halo * (1.0 - dentro));
  float a = max(dentro * 0.92, borda + halo) * v;
  if (a < 0.004) discard;
  gl_FragColor = vec4(cor, a);
}`;
const VERT_SOL = /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const FRAG_SOL = /* glsl */ `
varying vec2 vUv; uniform float uPulso; uniform vec3 uCor;
void main() {
  float r = length(vUv - 0.5) * 2.0;
  float miolo = smoothstep(0.11, 0.07, r);
  float coroa = exp(-r * 7.0) * 0.75 * uPulso + exp(-r * 2.6) * 0.07;
  float a = clamp(miolo + coroa, 0.0, 1.0);
  if (a < 0.003) discard;
  gl_FragColor = vec4(uCor * (miolo * 1.6 + coroa), a);
}`;

type Opcoes = {
  el: HTMLDivElement;
  camadaRotulos: HTMLDivElement;
  grafo: GrafoCerebro;
  poses: Record<Modo, Cena>;
  aoSobre: (id: string | null) => void;
  aoEscolher: (id: string | null) => void;
};

export async function criarCena({ el, camadaRotulos, grafo, poses, aoSobre, aoEscolher }: Opcoes): Promise<Motor> {
  const THREE = await import("three");
  const { EffectComposer } = await import("three/addons/postprocessing/EffectComposer.js");
  const { RenderPass } = await import("three/addons/postprocessing/RenderPass.js");
  const { UnrealBloomPass } = await import("three/addons/postprocessing/UnrealBloomPass.js");
  const { OutputPass } = await import("three/addons/postprocessing/OutputPass.js");

  const parado = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.setClearColor(FUNDO, 1);
  el.appendChild(renderer.domElement);
  renderer.domElement.style.display = "block";
  const cena = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, 0.05, 40);
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(cena, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.95, 0.48, 0.16);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  // ---- itens (pontos e traços)
  const itens = grafo.nodes.filter((n) => poses.disco.itens.has(n.id));
  const hexes = grafo.nodes.filter((n) => poses.disco.hexes.has(n.id));
  const plano = new THREE.PlaneGeometry(1, 1);
  const geoItem = new THREE.InstancedBufferGeometry();
  geoItem.index = plano.index;
  geoItem.setAttribute("position", plano.getAttribute("position"));
  geoItem.setAttribute("uv", plano.getAttribute("uv"));
  geoItem.instanceCount = itens.length;
  const attr = (n: number, k: number) => new THREE.InstancedBufferAttribute(new Float32Array(Math.max(1, n) * k), k);
  const aDe = attr(itens.length, 3), aPara = attr(itens.length, 3), aFormaDe = attr(itens.length, 4), aFormaPara = attr(itens.length, 4);
  const aCor = attr(itens.length, 3), aBrilho = attr(itens.length, 1);
  Object.entries({ aDe, aPara, aFormaDe, aFormaPara, aCor, aBrilho }).forEach(([k, a]) => geoItem.setAttribute(k, a));
  const corDeNo = (id: string) => new THREE.Color(corDoTipo(grafo.nodes.find((n) => n.id === id)?.tipo ?? ""));
  itens.forEach((n, i) => { const c = new THREE.Color(corDoTipo(n.tipo)); aCor.setXYZ(i, c.r, c.g, c.b); aBrilho.setX(i, 1); });
  const uItem = { uT: { value: 1 }, uTam: { value: TAM_ITEM }, uZoom: { value: 1 } };
  const matItem = new THREE.ShaderMaterial({ vertexShader: VERT_ITEM, fragmentShader: FRAG_ITEM, uniforms: uItem, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const malhaItens = new THREE.Mesh(geoItem, matItem);
  malhaItens.frustumCulled = false;
  cena.add(malhaItens);

  // ---- hexágonos (arquivos e fontes); cor de cada um num degradê em volta da órbita, como no vídeo
  const geoHex = new THREE.InstancedBufferGeometry();
  geoHex.index = plano.index;
  geoHex.setAttribute("position", plano.getAttribute("position"));
  geoHex.setAttribute("uv", plano.getAttribute("uv"));
  geoHex.instanceCount = hexes.length;
  const hDe = attr(hexes.length, 3), hPara = attr(hexes.length, 3), hTam = attr(hexes.length, 2), hCor = attr(hexes.length, 3), hBrilho = attr(hexes.length, 1);
  Object.entries({ aDe: hDe, aPara: hPara, aTam: hTam, aCor: hCor, aBrilho: hBrilho }).forEach(([k, a]) => geoHex.setAttribute(k, a));
  const degrade = ["#f6a14f", "#ffd36e", "#d9f07a", "#6fe7c8", "#6fd3f0", "#8fb0ff", "#c4a8ff"].map((c) => new THREE.Color(c));
  hexes.forEach((n, i) => {
    const t = (i / Math.max(1, hexes.length)) * (degrade.length - 1);
    const c = degrade[Math.floor(t)].clone().lerp(degrade[Math.min(degrade.length - 1, Math.floor(t) + 1)], t % 1);
    hCor.setXYZ(i, c.r, c.g, c.b);
    hBrilho.setX(i, 1);
  });
  const uHex = { uT: { value: 1 }, uTam: { value: TAM_HEX } };
  const matHex = new THREE.ShaderMaterial({ vertexShader: VERT_HEX, fragmentShader: FRAG_HEX, uniforms: uHex, transparent: true, depthWrite: false });
  const malhaHex = new THREE.Mesh(geoHex, matHex);
  malhaHex.frustumCulled = false;
  malhaHex.renderOrder = 2;
  cena.add(malhaHex);

  // ---- o núcleo (o Segundo Cérebro)
  const uSol = { uPulso: { value: 1 }, uCor: { value: new THREE.Color("#ffd94d") } };
  const sol = new THREE.Mesh(new THREE.PlaneGeometry(0.42, 0.42), new THREE.ShaderMaterial({ vertexShader: VERT_SOL, fragmentShader: FRAG_SOL, uniforms: uSol, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  sol.renderOrder = 3;
  cena.add(sol);

  // ---- linhas finas: os anéis do disco e as ligações (polos na Força, item escolhido em todas)
  const aneis: { linha: InstanceType<typeof THREE.LineLoop>; modo: Modo; alvo: number }[] = [];
  for (const [modo, c] of Object.entries(poses) as [Modo, Cena][]) {
    for (const l of c.linhas) {
      const pts = Array.from({ length: 256 }, (_, i) => new THREE.Vector3(l.r * Math.cos((i / 256) * 2 * Math.PI), l.r * Math.sin((i / 256) * 2 * Math.PI), 0));
      const linha = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: l.cor, transparent: true, opacity: 0 }));
      cena.add(linha);
      aneis.push({ linha, modo, alvo: 0 });
    }
  }
  const maxLig = 4096;
  const geoLig = new THREE.BufferGeometry();
  const ligPos = new Float32Array(maxLig * 6), ligCor = new Float32Array(maxLig * 6);
  geoLig.setAttribute("position", new THREE.BufferAttribute(ligPos, 3));
  geoLig.setAttribute("color", new THREE.BufferAttribute(ligCor, 3));
  const ligacoes = new THREE.LineSegments(geoLig, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
  ligacoes.frustumCulled = false;
  cena.add(ligacoes);

  // ---- estado: pose de saída e de chegada, câmera, realce
  let modo: Modo = "disco";
  let inicioVoo = -1e9;
  const cam = { elev: 0, elevDe: 0, giro: 0, zoom: 1, x: 0, y: 0, gira: false };
  let realce: Realce = { escolhido: null, sobre: null, busca: null };
  const atual = (i: number): Pose => ({ x: aPara.getX(i), y: aPara.getY(i), z: aPara.getZ(i), ang: aFormaPara.getX(i), sx: aFormaPara.getY(i), sy: aFormaPara.getZ(i) });
  const tempo = () => performance.now() / 1000;
  const progresso = () => (parado ? 1 : Math.min(1, (tempo() - inicioVoo) / DURACAO));

  function irPara(novo: Modo, imediato = false) {
    const t = imediato || parado ? 1 : progresso();
    const c = poses[novo];
    itens.forEach((n, i) => {
      // começa de onde o item está agora (mesmo no meio de outro voo)
      const agora = imediato ? { x: 0, y: 0, z: 0, ang: 0, sx: 0.4, sy: 0.4 } : misturar({ x: aDe.getX(i), y: aDe.getY(i), z: aDe.getZ(i), ang: aFormaDe.getX(i), sx: aFormaDe.getY(i), sy: aFormaDe.getZ(i) }, atual(i), t);
      const p = c.itens.get(n.id)!;
      aDe.setXYZ(i, agora.x, agora.y, agora.z); aFormaDe.setXYZ(i, agora.ang, agora.sx, agora.sy);
      aPara.setXYZ(i, p.x, p.y, p.z); aFormaPara.setXYZ(i, p.ang, p.sx, p.sy);
    });
    hexes.forEach((n, i) => {
      const k = suavizar(t);
      const de = imediato ? { x: 0, y: 0, z: 0, tam: 0.2 } : { x: hDe.getX(i) + (hPara.getX(i) - hDe.getX(i)) * k, y: hDe.getY(i) + (hPara.getY(i) - hDe.getY(i)) * k, z: hDe.getZ(i) + (hPara.getZ(i) - hDe.getZ(i)) * k, tam: hTam.getY(i) };
      const p: PoseHex = c.hexes.get(n.id)!;
      hDe.setXYZ(i, de.x, de.y, de.z); hPara.setXYZ(i, p.x, p.y, p.z); hTam.setXY(i, de.tam, p.tam);
    });
    [aDe, aPara, aFormaDe, aFormaPara, hDe, hPara, hTam].forEach((a) => (a.needsUpdate = true));
    cam.elevDe = cam.elev;
    cam.gira = CAMERA[novo].gira;
    if (novo !== "aneis") cam.giro = Math.atan2(Math.sin(cam.giro), Math.cos(cam.giro));
    modo = novo;
    inicioVoo = tempo(); // na primeira entrada (imediato), tudo sai do centro
    for (const a of aneis) a.alvo = a.modo === novo ? 1 : 0;
    montarRotulos();
  }

  function realcar(r: Realce) {
    realce = r;
    const viz = new Set<string>();
    if (r.escolhido) for (const e of grafo.edges) if (e.relacao !== "proveniencia") { if (e.de === r.escolhido) viz.add(e.para); if (e.para === r.escolhido) viz.add(e.de); }
    const brilho = (id: string) => {
      if (id === r.escolhido) return 2.4;
      if (id === r.sobre) return 2.0;
      if (viz.has(id)) return 1.7;
      if (r.busca && !r.busca.has(id)) return 0.12;
      if (r.escolhido) return 0.3;
      return r.busca ? 1.5 : 1;
    };
    itens.forEach((n, i) => aBrilho.setX(i, brilho(n.id)));
    hexes.forEach((n, i) => hBrilho.setX(i, brilho(n.id) === 0.3 ? 0.55 : brilho(n.id)));
    aBrilho.needsUpdate = true; hBrilho.needsUpdate = true;
  }

  // ---- rótulos HTML
  type Rot = { div: HTMLDivElement; x: number; y: number; z: number; centrado: boolean; larg?: number };
  let rotulos: Rot[] = [];
  function montarRotulos() {
    camadaRotulos.replaceChildren();
    rotulos = poses[modo].rotulos.map((r) => {
      const div = document.createElement("div");
      div.textContent = r.texto;
      div.dataset.estilo = r.estilo;
      div.style.setProperty("--cor", r.cor);
      camadaRotulos.appendChild(div);
      return { div, x: r.x, y: r.y, z: r.z, centrado: true };
    });
    if (modo === "disco") {
      for (const n of hexes) {
        if (n.tipo !== "fonte") continue;
        const p = poses.disco.hexes.get(n.id)!;
        const div = document.createElement("div");
        div.textContent = n.rotulo.toLocaleUpperCase("pt-BR");
        div.dataset.estilo = "orbita";
        div.dataset.lado = p.x >= 0 ? "direita" : "esquerda";
        camadaRotulos.appendChild(div);
        rotulos.push({ div, x: p.x * 1.07, y: p.y * 1.07, z: 0, centrado: false });
      }
    }
  }

  // ---- tamanho, câmera, desenho
  const v = new THREE.Vector3();
  let largura = 1, altura = 1;
  function ajustar() {
    largura = el.clientWidth || 1; altura = el.clientHeight || 1;
    renderer.setSize(largura, altura, false);
    renderer.domElement.style.width = `${largura}px`;
    renderer.domElement.style.height = `${altura}px`;
    composer.setSize(largura, altura);
    bloom.resolution.set(largura, altura);
    camera.aspect = largura / altura;
    camera.updateProjectionMatrix();
  }
  const obs = new ResizeObserver(ajustar);
  obs.observe(el);
  ajustar();

  const naTela = new Map<string, { x: number; y: number }>();
  let quadro = 0, vivo = true, ultimo = tempo();
  function desenhar() {
    if (!vivo) return;
    const agora = tempo(), dt = Math.min(0.05, agora - ultimo);
    ultimo = agora;
    const t = progresso();
    uItem.uT.value = t; uHex.uT.value = t;
    const k = suavizar(t);
    cam.elev = cam.elevDe + (CAMERA[modo].elev - cam.elevDe) * k;
    if (cam.gira && !parado && !arrasto) cam.giro += dt * 0.12;
    if (!cam.gira) cam.giro *= Math.pow(0.02, dt); // volta de frente devagar
    const ajusteTela = Math.min(1, largura / altura);
    const dist = (1.22 / (Math.tan((camera.fov * Math.PI) / 360) * ajusteTela)) / cam.zoom;
    camera.position.set(cam.x + dist * Math.sin(cam.giro) * Math.cos(cam.elev), cam.y + dist * Math.sin(cam.elev), dist * Math.cos(cam.giro) * Math.cos(cam.elev));
    camera.lookAt(cam.x, cam.y, 0);
    sol.quaternion.copy(camera.quaternion);
    uSol.uPulso.value = parado ? 1 : 1 + 0.12 * Math.sin(agora * 1.8);
    for (const a of aneis) {
      const m = a.linha.material as InstanceType<typeof THREE.LineBasicMaterial>;
      m.opacity += ((a.alvo * 0.55) - m.opacity) * Math.min(1, dt * 4);
      a.linha.visible = m.opacity > 0.01;
    }
    // posições atuais (para clique, ligações e rótulos)
    const pos = (de: InstanceType<typeof THREE.InstancedBufferAttribute>, para: InstanceType<typeof THREE.InstancedBufferAttribute>, i: number) =>
      v.set(de.getX(i) + (para.getX(i) - de.getX(i)) * k, de.getY(i) + (para.getY(i) - de.getY(i)) * k, de.getZ(i) + (para.getZ(i) - de.getZ(i)) * k);
    const mundo = new Map<string, [number, number, number]>();
    naTela.clear();
    itens.forEach((n, i) => {
      pos(aDe, aPara, i);
      mundo.set(n.id, [v.x, v.y, v.z]);
      v.project(camera);
      naTela.set(n.id, { x: ((v.x + 1) / 2) * largura, y: ((1 - v.y) / 2) * altura });
    });
    hexes.forEach((n, i) => {
      pos(hDe, hPara, i);
      mundo.set(n.id, [v.x, v.y, v.z]);
      v.project(camera);
      naTela.set(n.id, { x: ((v.x + 1) / 2) * largura, y: ((1 - v.y) / 2) * altura });
    });
    // ligações
    let nl = 0;
    const ligar = (a: [number, number, number], b: [number, number, number], cor: InstanceType<typeof THREE.Color>, f = 1) => {
      if (nl >= maxLig) return;
      ligPos.set([...a, ...b], nl * 6);
      ligCor.set([cor.r * f, cor.g * f, cor.b * f, cor.r * f * 0.4, cor.g * f * 0.4, cor.b * f * 0.4], nl * 6);
      nl++;
    };
    if (modo === "forca") {
      for (const n of hexes) if (n.tipo === "fonte") ligar([0, 0, 0], mundo.get(n.id)!, new THREE.Color("#5e7d70"), 0.5 * t);
    }
    if (realce.escolhido && mundo.has(realce.escolhido)) {
      const a = mundo.get(realce.escolhido)!;
      const c = corDeNo(realce.escolhido);
      for (const e of grafo.edges) {
        if (e.relacao === "proveniencia") continue;
        const outro = e.de === realce.escolhido ? e.para : e.para === realce.escolhido ? e.de : null;
        if (outro && mundo.has(outro)) ligar(a, mundo.get(outro)!, c, 1);
      }
    }
    geoLig.setDrawRange(0, nl * 2);
    (geoLig.getAttribute("position") as InstanceType<typeof THREE.BufferAttribute>).needsUpdate = true;
    (geoLig.getAttribute("color") as InstanceType<typeof THREE.BufferAttribute>).needsUpdate = true;
    // rótulos: aparecem quando o voo termina
    const opac = String(Math.max(0, (t - 0.7) / 0.3));
    for (const r of rotulos) {
      v.set(r.x, r.y, r.z).project(camera);
      let x = ((v.x + 1) / 2) * largura;
      const y = ((1 - v.y) / 2) * altura;
      r.larg ??= r.div.offsetWidth;
      if (r.centrado) x = Math.min(largura - r.larg / 2 - 6, Math.max(r.larg / 2 + 6, x)); // sempre inteiro na tela
      const fora = !r.centrado && (r.div.dataset.lado === "esquerda" ? x - r.larg < 4 : x + r.larg > largura - 4);
      r.div.style.transform = `translate(${x}px, ${y}px)`;
      r.div.style.opacity = v.z < 1 && !fora ? opac : "0";
    }
    composer.render();
    quadro = requestAnimationFrame(desenhar);
  }
  quadro = requestAnimationFrame(desenhar);

  // ---- mouse e toque
  let arrasto: { x: number; y: number; moveu: boolean } | null = null;
  const canvas = renderer.domElement;
  canvas.style.touchAction = "none";
  const local = (e: PointerEvent) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const aoApertar = (e: PointerEvent) => { canvas.setPointerCapture(e.pointerId); arrasto = { x: e.clientX, y: e.clientY, moveu: false }; };
  const aoMover = (e: PointerEvent) => {
    if (arrasto) {
      const dx = e.clientX - arrasto.x, dy = e.clientY - arrasto.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) arrasto.moveu = true;
      if (modo === "aneis") cam.giro -= dx * 0.006;
      else { const f = (2.4 / Math.min(largura, altura)) / cam.zoom; cam.x -= dx * f; cam.y += dy * f; }
      arrasto.x = e.clientX; arrasto.y = e.clientY;
      return;
    }
    const p = local(e);
    aoSobre(maisPerto(naTela, p.x, p.y, 9));
  };
  const aoSoltar = (e: PointerEvent) => {
    const a = arrasto;
    arrasto = null;
    if (a && !a.moveu) { const p = local(e); aoEscolher(maisPerto(naTela, p.x, p.y, 12)); }
  };
  const aoRolar = (e: WheelEvent) => { e.preventDefault(); cam.zoom = Math.max(0.6, Math.min(7, cam.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12))); };
  const aoSair = () => aoSobre(null);
  canvas.addEventListener("pointerdown", aoApertar);
  canvas.addEventListener("pointermove", aoMover);
  canvas.addEventListener("pointerup", aoSoltar);
  canvas.addEventListener("pointerleave", aoSair);
  canvas.addEventListener("wheel", aoRolar, { passive: false });

  function tecla(k: string) {
    if (k === "+" || k === "=") cam.zoom = Math.min(7, cam.zoom * 1.2);
    else if (k === "-") cam.zoom = Math.max(0.6, cam.zoom / 1.2);
    else if (k === "0") Object.assign(cam, { zoom: 1, x: 0, y: 0 });
  }

  function destruir() {
    vivo = false;
    cancelAnimationFrame(quadro);
    obs.disconnect();
    canvas.removeEventListener("pointerdown", aoApertar);
    canvas.removeEventListener("pointermove", aoMover);
    canvas.removeEventListener("pointerup", aoSoltar);
    canvas.removeEventListener("pointerleave", aoSair);
    canvas.removeEventListener("wheel", aoRolar);
    cena.traverse((o) => {
      const m = o as unknown as { geometry?: { dispose: () => void }; material?: { dispose: () => void } };
      m.geometry?.dispose(); m.material?.dispose();
    });
    plano.dispose();
    composer.dispose();
    renderer.dispose();
    canvas.remove();
    camadaRotulos.replaceChildren();
  }

  return { irPara, realcar, tecla, destruir };
}
