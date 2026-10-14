// Topo (logo + rótulo da seção) e rodapé (progresso + perfil) iguais em todo slide.
// Cada .slide pode ter data-rot="RÓTULO"; .claro usa o logo para fundo claro.
(function () {
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
