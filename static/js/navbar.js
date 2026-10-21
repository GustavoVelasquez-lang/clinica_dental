/* ============================================================
   Clinica Sele Dent - Barra de navegacion (comportamiento)
   * Sombra al hacer scroll.
   * Menu desplegable (hamburguesa) en movil / tablet (< 992px).
   Se incluye desde _navbar.html, por lo que aplica a todas las paginas.
   ============================================================ */
(function () {
  var navbar = document.getElementById('navbar');
  if (!navbar) return;

  // --- Sombra al hacer scroll ---
  var onScroll = function () {
    navbar.classList.toggle('scrolled', window.scrollY > 20);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // --- Menu desplegable (hamburguesa) ---
  var toggle = navbar.querySelector('#navToggle');
  var menu = navbar.querySelector('#navMenu');
  if (!toggle || !menu) return;

  var setEstado = function (abierto) {
    menu.classList.toggle('is-open', abierto);
    toggle.setAttribute('aria-expanded', abierto ? 'true' : 'false');
    var icono = toggle.querySelector('i');
    if (icono) {
      icono.classList.toggle('fa-bars', !abierto);
      icono.classList.toggle('fa-xmark', abierto);
    }
  };

  toggle.addEventListener('click', function () {
    setEstado(!menu.classList.contains('is-open'));
  });

  // Cierra al pulsar un enlace del menu.
  menu.addEventListener('click', function (e) {
    if (e.target.closest('a')) setEstado(false);
  });

  // Cierra al hacer clic fuera del navbar.
  document.addEventListener('click', function (e) {
    if (menu.classList.contains('is-open') && !navbar.contains(e.target)) {
      setEstado(false);
    }
  });

  // Cierra con la tecla Escape.
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && menu.classList.contains('is-open')) {
      setEstado(false);
      toggle.focus();
    }
  });

  // Al pasar a escritorio, restablece el estado (sin menu flotante).
  if (window.matchMedia) {
    var mq = window.matchMedia('(min-width: 992px)');
    var onDesktop = function (ev) {
      if (ev.matches) setEstado(false);
    };
    if (mq.addEventListener) mq.addEventListener('change', onDesktop);
    else if (mq.addListener) mq.addListener(onDesktop);
  }
})();
