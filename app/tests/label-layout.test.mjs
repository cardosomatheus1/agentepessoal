import test from 'node:test';
import assert from 'node:assert/strict';
import { labelPolicy, planLabels, sameLabelPlan } from '../lib/label-layout.mjs';

const measure = (text, size) => text.length * size * 0.6; // medida fixa e determinística no teste
const c = (id, x, y, extra = {}) => ({ id, x, y, r: 4, text: `Registro ${id}`, size: 11, priority: 1, ...extra });
const sobrepoe = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
const semColisao = (plan) => {
  const bs = [...plan.values()].map((p) => p.box);
  for (let i = 0; i < bs.length; i++) for (let j = i + 1; j < bs.length; j++) assert.ok(!sobrepoe(bs[i], bs[j]), `rótulos ${i} e ${j} se sobrepõem`);
};
// Grade densa: 158 nós como o mapa real, bem juntos.
const denso = (W, H) => Array.from({ length: 158 }, (_, i) => c(`n${String(i).padStart(3, '0')}`, 20 + (i % 14) * ((W - 40) / 13), 20 + Math.floor(i / 14) * ((H - 40) / 11), { priority: i % 7 }));

test('nenhum rótulo se sobrepõe no desktop nem no mobile com 158 nós densos', () => {
  for (const [W, H] of [[1100, 640], [360, 420]]) {
    const plan = planLabels(denso(W, H), { width: W, height: H, measure });
    assert.ok(plan.size > 0);
    semColisao(plan);
  }
});

test('mobile mostra menos rótulos que desktop (densidade menor)', () => {
  const d = planLabels(denso(1100, 640), { width: 1100, height: 640, measure });
  const m = planLabels(denso(360, 420), { width: 360, height: 420, measure });
  assert.ok(labelPolicy(360, 420).mobile && !labelPolicy(1100, 640).mobile);
  assert.ok(m.size < d.size, `mobile ${m.size} >= desktop ${d.size}`);
  assert.ok(m.size <= labelPolicy(360, 420).budget);
});

test('nó em foco sempre tem rótulo, mesmo no meio de um grupo denso, e vence o vizinho de prioridade alta', () => {
  const cands = [c('viz', 100, 100, { priority: 99 }), c('alvo', 102, 101, { pinned: true, size: 14 }), c('outro', 104, 102, { priority: 50 })];
  const plan = planLabels(cands, { width: 800, height: 600, measure });
  assert.ok(plan.has('alvo'));
  assert.ok(!plan.has('viz') || !sobrepoe(plan.get('viz').box, plan.get('alvo').box));
  semColisao(plan);
});

test('vizinhos não são todos forçados: os que colidem ficam sem rótulo', () => {
  const vizinhos = Array.from({ length: 10 }, (_, i) => c(`v${i}`, 200, 200 + i * 2, { priority: 50 }));
  const plan = planLabels([c('alvo', 200, 180, { pinned: true }), ...vizinhos], { width: 800, height: 600, measure });
  assert.ok(plan.has('alvo'));
  assert.ok(plan.size < 11);
  semColisao(plan);
});

test('borda: rótulo que sairia à direita vai para a esquerda; o que não cabe em lado nenhum some', () => {
  const W = 400, H = 300;
  const plan = planLabels([c('dir', 390, 150), c('fora', 200, 1), c('meio', 100, 100)], { width: W, height: H, measure });
  assert.equal(plan.get('dir').position, 'left');
  assert.ok(!plan.has('fora'));
  for (const { box } of plan.values()) assert.ok(box.x0 >= 0 && box.x1 <= W && box.y0 >= 0 && box.y1 <= H);
});

test('mede o texto real: rótulo longo colide onde um curto caberia', () => {
  const curto = planLabels([c('a', 100, 100, { text: 'A', priority: 2 }), c('b', 130, 100, { text: 'B' })], { width: 800, height: 600, measure });
  const longo = planLabels([c('a', 100, 100, { text: 'Um título bem comprido', priority: 2 }), c('b', 130, 100, { text: 'B' })], { width: 800, height: 600, measure });
  assert.equal(curto.size, 2);
  assert.deepEqual([...longo.keys()], ['a']);
});

test('determinístico e independente da ordem de entrada', () => {
  const cands = denso(1100, 640);
  const a = planLabels(cands, { width: 1100, height: 640, measure });
  const b = planLabels([...cands].reverse(), { width: 1100, height: 640, measure });
  assert.ok(sameLabelPlan(a, b));
  assert.deepEqual([...a.keys()].sort(), [...b.keys()].sort());
});
