(function () {
  const tabla = document.getElementById('tablaTratamientos');
  if (!tabla) return;

  const buscador = document.getElementById('buscarTratamiento');
  const filtro = document.getElementById('filtroEspecialidad');
  const filas = Array.prototype.slice.call(
    tabla.querySelectorAll('tbody tr[data-buscar]')
  );

  // ── Buscador en vivo + filtro por especialidad ──────────────────────────
  function aplicarFiltros() {
    const texto = (buscador && buscador.value ? buscador.value : '').trim().toLowerCase();
    const esp = filtro ? filtro.value : '';
    let visibles = 0;

    filas.forEach(function (fila) {
      const coincideTexto = !texto || (fila.dataset.buscar || '').indexOf(texto) !== -1;
      const coincideEsp = !esp || fila.dataset.especialidad === esp;
      const mostrar = coincideTexto && coincideEsp;
      fila.style.display = mostrar ? '' : 'none';
      if (mostrar) visibles++;
    });

    let vacio = document.getElementById('sinResultadosTrat');
    if (!visibles) {
      if (!vacio) {
        vacio = document.createElement('tr');
        vacio.id = 'sinResultadosTrat';
        vacio.innerHTML = '<td colspan="7" class="empty">No se encontraron tratamientos.</td>';
        tabla.querySelector('tbody').appendChild(vacio);
      }
    } else if (vacio) {
      vacio.remove();
    }
  }

  if (buscador) buscador.addEventListener('input', aplicarFiltros);
  if (filtro) filtro.addEventListener('change', aplicarFiltros);

  // ── Modal Nuevo / Editar ────────────────────────────────────────────────
  const modal = document.getElementById('modalTratamiento');
  if (!modal) return;

  const titulo = document.getElementById('modalTratamientoTitulo');
  const fId = document.getElementById('tratId');
  const fNombre = document.getElementById('tratNombre');
  const fEsp = document.getElementById('tratEspecialidad');
  const fPrecio = document.getElementById('tratPrecio');
  const fAdelanto = document.getElementById('tratAdelanto');
  const fDuracion = document.getElementById('tratDuracion');
  const fDesc = document.getElementById('tratDescripcion');
  const fActivo = document.getElementById('tratActivo');

  function limpiarFormulario() {
    fId.value = '';
    fNombre.value = '';
    fEsp.value = '';
    fPrecio.value = '';
    fAdelanto.value = '';
    fDuracion.value = '';
    fDesc.value = '';
    fActivo.checked = true;
    titulo.textContent = 'Nuevo tratamiento';
  }

  const btnNuevo = document.getElementById('btnNuevoTratamiento');
  if (btnNuevo) btnNuevo.addEventListener('click', limpiarFormulario);

  document.querySelectorAll('.js-editar-tratamiento').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const d = btn.dataset;
      fId.value = d.id || '';
      fNombre.value = d.nombre || '';
      fEsp.value = d.especialidad || '';
      fPrecio.value = d.precio || '';
      fAdelanto.value = d.adelanto || '';
      fDuracion.value = d.duracion || '';
      fDesc.value = d.descripcion || '';
      fActivo.checked = d.activo === '1';
      titulo.textContent = 'Editar tratamiento';
    });
  });
})();
