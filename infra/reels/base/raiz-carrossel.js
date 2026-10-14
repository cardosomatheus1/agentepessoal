// Topo (logo + rótulo da seção) e rodapé (progresso + perfil) iguais em todo slide.
// Cada .slide pode ter data-rot="RÓTULO"; .claro usa o logo para fundo claro.
(function () {
  // bloco padrão do convite para a calculadora: a tela real do produto + o que ela entrega
  document.querySelectorAll('.cta-calc').forEach(el => el.innerHTML =
    `<div class="celular"><img src="../base/kit/tela-calculadora.jpg"></div><ul>` +
    `<li><span>Sem cadastro<small>abre e já começa</small></span></li>` +
    `<li><span>Produto por produto<small>custo, preço e onde vende</small></span></li>` +
    `<li><span>Quanto sobra<small>o diagnóstico no fim</small></span></li></ul>`);
  const s = [...document.querySelectorAll('.slide')], n = s.length;
  s.forEach((el, i) => {
    const claro = el.classList.contains('claro');
    const logo = claro ? 'rc-logo-light-v26.png' : 'rc-logo-dark-v26.png';
    if (!el.hasAttribute('data-sem-topo'))
      el.insertAdjacentHTML('afterbegin', `<div class="topo"><img src="../base/kit/${logo}"><span class="rot">${el.dataset.rot || ''}</span></div>`);
    const fim = i === n - 1 ? (el.dataset.fim || 'link na bio') : 'arraste →';
    el.insertAdjacentHTML('beforeend', `<div class="pe"><span>@raiz.connect</span><div class="barras">${
      s.map((_, k) => `<i class="${k <= i ? 'on' : ''}"></i>`).join('')}</div><span>${fim}</span></div>`);
  });
})();
