const now = new Date();
const dias_s = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
const meses  = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];

const fh = document.getElementById('fechaHoy');
if (fh) fh.textContent = `${dias_s[now.getDay()]}, ${now.getDate()} de ${meses[now.getMonth()]} de ${now.getFullYear()}`;

const dh = document.getElementById('diaHoy');
if (dh) dh.textContent = `Hoy: ${dias_s[now.getDay()]}`;

/* ── Menú lateral responsive ── */
(function () {
  const sidebar = document.querySelector('.sidebar');
  const toggle  = document.getElementById('sbToggle');
  const overlay = document.getElementById('sbOverlay');
  if (!sidebar || !toggle || !overlay) return;

  const abrir = () => {
    sidebar.classList.add('open');
    overlay.classList.add('show');
    document.body.style.overflow = 'hidden';
  };
  const cerrar = () => {
    sidebar.classList.remove('open');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
  };

  toggle.addEventListener('click', () =>
    sidebar.classList.contains('open') ? cerrar() : abrir()
  );
  overlay.addEventListener('click', cerrar);

  sidebar.querySelectorAll('.sb-nav a').forEach(a => a.addEventListener('click', cerrar));

  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrar(); });

  window.addEventListener('resize', () => { if (window.innerWidth > 900) cerrar(); });
})();
