/* ============================================================
   PANEL DE USUARIO · sidebar responsive + edición en caliente
   ============================================================ */

/* ── Fecha de hoy en la topbar ── */
(function () {
  const fh = document.getElementById('fechaHoy');
  if (!fh) return;
  const now = new Date();
  const dias = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
  const meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  fh.textContent = `${dias[now.getDay()]}, ${now.getDate()} de ${meses[now.getMonth()]} de ${now.getFullYear()}`;
})();

/* ── Menú lateral responsive ── */
(function () {
  const sidebar = document.querySelector('.sidebar');
  const toggle = document.getElementById('sbToggle');
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

/* ── Toast de feedback ── */
function mostrarToast(mensaje, tipo) {
  let cont = document.querySelector('.pn-toast-stack');
  if (!cont) {
    cont = document.createElement('div');
    cont.className = 'pn-toast-stack';
    document.body.appendChild(cont);
  }
  const toast = document.createElement('div');
  toast.className = 'pn-toast pn-toast--' + (tipo || 'ok');
  const icono = tipo === 'error' ? 'fa-circle-xmark' : 'fa-circle-check';
  toast.innerHTML = `<i class="fa-solid ${icono}"></i><span>${mensaje}</span>`;
  cont.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('pn-toast--out');
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

/* ── Edición en caliente (teléfono / correo / dirección) ── */
(function () {
  const filas = document.querySelectorAll('.cf-row');
  if (!filas.length) return;

  const endpoint = (typeof PANEL_CONFIG !== 'undefined' && PANEL_CONFIG.endpoint) || '';

  /* Rellena nombres/apellidos tras consultar el DNI. */
  const aplicarNombres = (nombres) => {
    const mapa = {
      nombre: nombres.nombre,
      apepaterno: nombres.apepaterno,
      apematerno: nombres.apematerno
    };
    Object.keys(mapa).forEach(clave => {
      const fila = document.querySelector('.cf-row[data-campo="' + clave + '"]');
      if (!fila) return;
      const valorEl = fila.querySelector('.cf-value');
      const inputEl = fila.querySelector('.cf-input');
      if (valorEl) valorEl.textContent = mapa[clave] || '—';
      if (inputEl) inputEl.value = mapa[clave] || '';
    });
    const header = document.getElementById('perfilNombre');
    if (header) {
      header.textContent = [nombres.nombre, nombres.apepaterno, nombres.apematerno]
        .filter(Boolean).join(' ');
    }
  };

  filas.forEach(fila => {
    const valorEl = fila.querySelector('.cf-value');
    const inputEl = fila.querySelector('.cf-input');
    const btn = fila.querySelector('.cf-edit');
    if (!valorEl || !inputEl || !btn) return;

    const campo = fila.dataset.campo;
    let original = inputEl.value;

    if (campo === 'dni') {
      inputEl.addEventListener('input', () => {
        inputEl.value = inputEl.value.replace(/\D/g, '').slice(0, 8);
      });
    }

    const modoEdicion = (activo) => {
      fila.classList.toggle('is-editing', activo);
      inputEl.hidden = !activo;
      valorEl.hidden = activo;
      btn.innerHTML = activo
        ? '<i class="fa-solid fa-check"></i> Guardar'
        : 'Editar <i class="fa-solid fa-chevron-right"></i>';
      if (activo) { inputEl.focus(); inputEl.select(); }
    };

    const cancelar = () => {
      inputEl.value = original;
      modoEdicion(false);
    };

    const guardar = async () => {
      const valor = inputEl.value.trim();
      if (valor === '' && campo !== 'direccion') {
        mostrarToast('El campo no puede estar vacío.', 'error');
        return;
      }
      btn.disabled = true;
      try {
        const resp = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ campo: campo, valor: valor })
        });
        const data = await resp.json();
        if (!data.ok) {
          mostrarToast(data.mensaje || 'No se pudo guardar.', 'error');
          btn.disabled = false;
          return;
        }
        original = data.valor != null ? data.valor : valor;
        inputEl.value = original;
        let valorMostrado = original || '—';
        if (campo === 'fenacimiento' && original) {
          const partes = String(original).split('-');
          if (partes.length === 3) valorMostrado = partes[2] + '/' + partes[1] + '/' + partes[0];
        }
        valorEl.textContent = valorMostrado;
        if (campo === 'dni' && data.nombres) {
          aplicarNombres(data.nombres);
          const dniPerfil = document.getElementById('perfilDni');
          if (dniPerfil) dniPerfil.textContent = original;
        }
        if (campo === 'fenacimiento' && typeof data.edad === 'number') {
          const edadEl = document.getElementById('perfilEdad');
          if (edadEl) edadEl.textContent = data.edad;
        }
        modoEdicion(false);
        mostrarToast(data.mensaje || 'Datos actualizados correctamente.', 'ok');
      } catch (err) {
        mostrarToast('Error de conexión al guardar.', 'error');
      } finally {
        btn.disabled = false;
      }
    };

    btn.addEventListener('click', () => {
      if (fila.classList.contains('is-editing')) {
        guardar();
      } else {
        document.querySelectorAll('.cf-row.is-editing').forEach(f => {
          if (f !== fila) {
            const b = f.querySelector('.cf-edit');
            if (b) b.click();
          }
        });
        modoEdicion(true);
      }
    });

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); guardar(); }
      if (e.key === 'Escape') { e.preventDefault(); cancelar(); }
    });
  });
})();
