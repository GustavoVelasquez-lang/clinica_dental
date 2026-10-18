document.addEventListener('DOMContentLoaded', function () {
  // El filtrado y la paginación ahora se resuelven en el servidor; los chips y
  // los botones de página son enlaces que conservan los filtros activos. Aquí
  // solo añadimos el auto-envío del buscador (por el formulario GET).
  const form = document.getElementById('ctcFiltrosForm');
  const buscar = document.getElementById('ctcBuscar');
  if (form && buscar) {
    // Si venimos de una búsqueda, devolvemos el foco al campo para seguir tecleando.
    if (buscar.value.trim()) {
      buscar.focus();
      buscar.setSelectionRange(buscar.value.length, buscar.value.length);
    }

    let timer = null;
    buscar.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { form.submit(); }, 500);
    });
  }
});

// ── Modal: previsualizar voucher de Yape ──
document.addEventListener('DOMContentLoaded', function () {
  const modal = document.getElementById('modalVoucher');
  if (!modal) return;

  // Mover el modal directamente al <body> para que no herede ningún
  // "transform" de un ancestro (evita que el backdrop quede por encima
  // del modal y bloquee los clics).
  if (modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }

  // Al cerrarse, limpiar cualquier backdrop sobrante y restaurar el scroll.
  modal.addEventListener('hidden.bs.modal', function () {
    if (!document.querySelector('.modal.show')) {
      document.querySelectorAll('.modal-backdrop').forEach(function (b) { b.remove(); });
      document.body.classList.remove('modal-open');
      document.body.style.removeProperty('overflow');
      document.body.style.removeProperty('padding-right');
    }
  });

  modal.addEventListener('show.bs.modal', function (event) {
    const boton = event.relatedTarget;
    if (!boton) return;

    const set = function (id, valor) {
      const el = document.getElementById(id);
      if (el) el.textContent = valor || '—';
    };

    set('mvCita', boton.dataset.cita);
    set('mvPaciente', boton.dataset.paciente);
    set('mvEspecialidad', boton.dataset.especialidad);
    set('mvTratamiento', boton.dataset.tratamiento);
    set('mvFecha', boton.dataset.fecha);
    set('mvMonto', boton.dataset.monto);
    set('mvOperacion', boton.dataset.operacion);

    const url = boton.dataset.voucher || '';
    const img = document.getElementById('mvVoucher');
    const descarga = document.getElementById('mvDescargar');
    if (img) img.src = url;
    if (descarga) descarga.href = url;
  });

  // ── Cerrar el modal (X, botón Cerrar y click en el fondo) ──
  function cerrarVoucher() {
    if (window.bootstrap && bootstrap.Modal) {
      const inst = bootstrap.Modal.getInstance(modal) || bootstrap.Modal.getOrCreateInstance(modal);
      inst.hide();
      return;
    }
    // Respaldo por si Bootstrap no está disponible.
    modal.classList.remove('show');
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    document.querySelectorAll('.modal-backdrop').forEach(function (b) { b.remove(); });
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
  }

  const cerrarX = document.getElementById('mvCerrarX');
  const cerrarBtn = document.getElementById('mvCerrarBtn');
  if (cerrarX) cerrarX.addEventListener('click', cerrarVoucher);
  if (cerrarBtn) cerrarBtn.addEventListener('click', cerrarVoucher);

  // Click en el fondo oscuro cierra el modal.
  modal.addEventListener('click', function (event) {
    if (event.target === modal) cerrarVoucher();
  });

  // Tecla Escape cierra el modal.
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && modal.classList.contains('show')) cerrarVoucher();
  });
});
