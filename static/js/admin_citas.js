document.addEventListener('DOMContentLoaded', function () {
  const filas = Array.from(document.querySelectorAll('.ctc-table .ctc-row'));
  const grupos = Array.from(document.querySelectorAll('.ctc-table .ctc-grupo'));
  const buscar = document.getElementById('ctcBuscar');
  const chips = Array.from(document.querySelectorAll('#ctcFiltros .ctc-chip'));
  const sinResultados = document.getElementById('ctcSinResultados');
  const verPendientes = document.getElementById('ctcVerPendientes');

  let filtroEstado = 'todos';
  let soloPorVerificar = false;
  let termino = '';

  // ── Estados que agrupa el chip "Atendidas" ──
  const GRUPO_ATENDIDA = ['atendida', 'atendido', 'completada'];

  function coincideEstado(fila, estado) {
    if (soloPorVerificar) return fila.dataset.pago === 'pendiente_verificacion';
    if (filtroEstado === 'todos') return true;
    if (filtroEstado === 'hoy') return fila.dataset.hoy === '1';
    if (filtroEstado === 'atendida') return GRUPO_ATENDIDA.includes(estado);
    return estado === filtroEstado;
  }

  function aplicarFiltros() {
    let visibles = 0;

    filas.forEach(function (fila) {
      const estado = (fila.dataset.estado || '').toLowerCase();
      const texto = (fila.dataset.buscar || '');
      const okEstado = coincideEstado(fila, estado);
      const okTexto = !termino || texto.includes(termino);
      const visible = okEstado && okTexto;

      fila.classList.toggle('ctc-hidden', !visible);
      if (visible) visibles++;
    });

    // Ocultar las secciones por fecha que quedaron vacías.
    grupos.forEach(function (grupo) {
      const hayVisibles = grupo.querySelector('.ctc-row:not(.ctc-hidden)');
      grupo.classList.toggle('ctc-hidden', !hayVisibles);
    });

    if (sinResultados) {
      sinResultados.hidden = !(filas.length > 0 && visibles === 0);
    }
  }

  function activarChip(filtro) {
    soloPorVerificar = false;
    if (verPendientes) verPendientes.classList.remove('active');
    chips.forEach(function (c) {
      c.classList.toggle('active', c.dataset.filtro === filtro);
    });
    filtroEstado = filtro;
    aplicarFiltros();
  }

  // ── Búsqueda ──
  if (buscar) {
    buscar.addEventListener('input', function () {
      termino = buscar.value.trim().toLowerCase();
      aplicarFiltros();
    });
  }

  // ── Chips de estado ──
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      activarChip(chip.dataset.filtro || 'todos');
    });
  });

  // ── Botón "Pago pendiente por verificar" ──
  if (verPendientes) {
    verPendientes.addEventListener('click', function () {
      soloPorVerificar = !soloPorVerificar;
      verPendientes.classList.toggle('active', soloPorVerificar);
      chips.forEach(function (c) {
        c.classList.toggle('active', !soloPorVerificar && c.dataset.filtro === filtroEstado);
      });
      if (soloPorVerificar) filtroEstado = 'todos';
      aplicarFiltros();
    });
  }

  // ── KPI: citas de hoy ──
  const kpiHoy = document.getElementById('kpiHoy');
  if (kpiHoy) {
    kpiHoy.textContent = filas.filter(function (fila) {
      return fila.dataset.hoy === '1';
    }).length;
  }

  aplicarFiltros();
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
