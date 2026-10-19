const tipData = JSON.parse(document.getElementById('tiposData').textContent);

const TIPOS_ESP = {};
const TIPOS_DESC = {};
tipData.forEach(function (t) {
  TIPOS_ESP[t.key] = t.esp_id === null ? null : t.esp_id;
  TIPOS_DESC[t.key] = t.descripcion;
});

const espSelect  = document.getElementById('especialidad');
const tratSelect = document.getElementById('tratamiento');
const grupoTrat  = document.getElementById('grupoTratamiento');
const docSelect  = document.getElementById('odontologo');
const grupoDoc   = document.getElementById('grupoDoctor');
const fechaInput = document.getElementById('fecha');
const horaHidden = document.getElementById('hora_selected');
const horaDisp   = document.getElementById('hora_display');
const container  = document.getElementById('horariosContainer');
const badgeEl    = document.getElementById('disponibilidadBadge');
const resumen    = document.getElementById('resumenCita');
const btnAgendar = document.getElementById('btnAgendar');
const msgArea    = document.getElementById('mensaje');
const charCount  = document.getElementById('charCount');

const tipoSelect = document.getElementById('tipo');
const grupoEsp   = document.getElementById('grupoEspecialidad');
const tipoDesc   = document.getElementById('tipoDesc');

// Aplica el tipo de atención al formulario (compartido entre el evento
// 'change' y la carga inicial desde la URL).
// `preservarEspSelect`: no limpia la especialidad ya preseleccionada
// (se usa al cargar un tratamiento de la URL, cuya especialidad ya viene fija).
function aplicarTipo(key, opciones) {
  opciones = opciones || {};
  const espFija = TIPOS_ESP[key];
  tipoDesc.textContent = key ? (TIPOS_DESC[key] || '') : '';

  if (!key) {
    // Sin tipo seleccionado: ocultar especialidad.
    grupoEsp.style.display = 'none';
    espSelect.value = '';
  } else if (espFija === null || espFija === undefined) {
    // El paciente debe elegir la especialidad.
    grupoEsp.style.display = '';
    if (!opciones.preservarEspSelect) espSelect.value = '';
  } else {
    // Especialidad fija definida por el tipo de atención.
    grupoEsp.style.display = 'none';
    espSelect.value = espFija;
  }

  // Modo urgencia: fecha de hoy + especialidad de emergencias.
  aplicarModoUrgencia(key === 'urgencia');
}

tipoSelect.addEventListener('change', () => {
  aplicarTipo(tipoSelect.value);

  resetHora();
  actualizarResumen();
  validarFormulario();
  cargarHorarios();
  cargarTratamientos();
  cargarDoctores();
});

// ── Fechas base ───────────────────────────
const hoy       = new Date();
const hoyStr    = hoy.toISOString().split('T')[0];
const manana    = new Date(hoy); manana.setDate(hoy.getDate() + 1);
const mananaStr = manana.toISOString().split('T')[0];

// ── Fecha mínima por defecto: mañana ──────
fechaInput.min = mananaStr;

// Especialidad de emergencias por defecto (Cirugía Oral) si no se resuelve.
const URGENCIA_ESPECIALIDAD_ID = '4';
let modoUrgencia = false;

// ── Contador de caracteres ────────────────
msgArea.addEventListener('input', () => {
  charCount.textContent = msgArea.value.length;
});

// ── Disparar carga de horarios ────────────
espSelect.addEventListener('change',  cargarHorarios);
espSelect.addEventListener('change',  cargarTratamientos);
espSelect.addEventListener('change',  cargarDoctores);
tratSelect.addEventListener('change', cargarDoctores);
fechaInput.addEventListener('change', cargarHorarios);

// ── Cargar tratamientos según la especialidad elegida ──
// `preseleccion`: id de tratamiento a marcar automáticamente tras cargar
// (p. ej. cuando se llega desde el catálogo público con ?tratamiento_id=).
async function cargarTratamientos(preseleccion) {
  if (!tratSelect || !grupoTrat) return;

  // Al usarse como manejador de 'change', el primer argumento es un Event.
  if (typeof preseleccion !== 'string') preseleccion = '';

  const esp = espSelect.value;
  const espVisible = grupoEsp.style.display !== 'none';

  // Sin especialidad seleccionada (o especialidad fija): ocultar tratamientos.
  if (!esp || !espVisible) {
    grupoTrat.style.display = 'none';
    tratSelect.innerHTML = '<option value="">— Selecciona un tratamiento (opcional) —</option>';
    return;
  }

  tratSelect.innerHTML = '<option value="">Cargando tratamientos…</option>';
  try {
    const res = await fetch('/tratamientos_por_especialidad?especialidad_id=' +
      encodeURIComponent(esp));
    const data = await res.json();

    tratSelect.innerHTML = '<option value="">— Selecciona un tratamiento (opcional) —</option>';
    if (Array.isArray(data) && data.length) {
      data.forEach(function (t) {
        const op = document.createElement('option');
        op.value = t.id;
        op.textContent = t.nombre;
        tratSelect.appendChild(op);
      });
      grupoTrat.style.display = '';

      // Preseleccionar el tratamiento solicitado desde la URL.
      if (preseleccion) {
        const objetivo = tratSelect.querySelector(
          'option[value="' + preseleccion + '"]'
        );
        if (objetivo) {
          tratSelect.value = preseleccion;
          tratSelect.dispatchEvent(new Event('change'));
        }
      }
    } else {
      grupoTrat.style.display = 'none';
    }
  } catch (e) {
    grupoTrat.style.display = 'none';
  }
}

// ── Cargar doctores/odontólogos según la especialidad ──
const OPCION_CUALQUIER_DOCTOR =
  'Cualquier doctor disponible (Asignación automática)';

async function cargarDoctores() {
  if (!docSelect || !grupoDoc) return;

  const esp = espSelect.value;

  // Sin especialidad seleccionada: ocultar y resetear.
  if (!esp) {
    grupoDoc.style.display = 'none';
    docSelect.innerHTML =
      '<option value="">' + OPCION_CUALQUIER_DOCTOR + '</option>';
    return;
  }

  docSelect.innerHTML = '<option value="">Cargando especialistas…</option>';
  try {
    const res = await fetch(
      '/api/doctores-por-especialidad/' + encodeURIComponent(esp)
    );
    const data = await res.json();

    docSelect.innerHTML =
      '<option value="">' + OPCION_CUALQUIER_DOCTOR + '</option>';
    if (Array.isArray(data) && data.length) {
      data.forEach(function (d) {
        const op = document.createElement('option');
        op.value = d.id;
        op.textContent = d.nombre;
        docSelect.appendChild(op);
      });
    }
    // Mostrar siempre el selector (aun sin doctores: queda "automática").
    grupoDoc.style.display = '';
  } catch (e) {
    grupoDoc.style.display = 'none';
  }
}

async function cargarHorarios() {
  const esp   = espSelect.value;
  const fecha = fechaInput.value;

  // Actualizar step visual
  if (esp) { document.getElementById('step1').classList.add('active'); }
  if (esp && fecha) { document.getElementById('step2').classList.add('active'); }

  if (!tipoSelect.value || !espSelect.value || !fecha) {
    container.innerHTML = `<div class="aviso-centro">
      🗓️ Selecciona el tipo de atención y fecha para ver horarios</div>`;
    resetHora();
    return;
  }

  // Skeleton loading
  container.innerHTML = `<div class="horarios-loading">
    ${Array(6).fill('<div class="hora-skeleton"></div>').join('')}
  </div>`;
  badgeEl.innerHTML = '';

  try {
    const res  = await fetch('/horarios_disponibles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fecha, especialidad: esp })
    });
    const disponibles = await res.json();

    const todasLasHoras = [
      { val: '09:00:00', label: '09:00 am' },
      { val: '10:00:00', label: '10:00 am' },
      { val: '11:00:00', label: '11:00 am' },
      { val: '12:00:00', label: '12:00 pm' },
      { val: '15:00:00', label: '03:00 pm' },
      { val: '16:00:00', label: '04:00 pm' },
    ];

    if (disponibles.length === 0) {
      container.innerHTML = `<div class="sin-horarios">
        <div class="sin-horarios-icon">😔</div>
        <p class="sin-horarios-title">No hay horarios disponibles para este día</p>
        <p class="sin-horarios-sub">Prueba con otra fecha</p>
      </div>`;
      resetHora();
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'horarios-grid';

    todasLasHoras.forEach(h => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hora-btn';
      btn.textContent = h.label;
      btn.dataset.val = h.val;
      const libre = disponibles.includes(h.val);
      if (!libre) {
        btn.disabled = true;
        btn.classList.add('ocupada');
        btn.title = 'Hora ocupada';
        btn.textContent = h.label + ' ✕';
      } else {
        btn.addEventListener('click', () => seleccionarHora(h.val, h.label, btn));
      }
      grid.appendChild(btn);
    });

    container.innerHTML = '';
    container.appendChild(grid);

    // Urgencia + hoy: resaltar el turno más cercano a la hora actual.
    if (modoUrgencia && fecha === hoyStr) {
      priorizarTurnoCercano(grid);
    }

  } catch(e) {
    container.innerHTML = `<p class="error-text">Error al cargar horarios. Intenta de nuevo.</p>`;
  }
}

function seleccionarHora(val, label, btn) {
  // Deselect todos
  document.querySelectorAll('.hora-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');

  horaHidden.value = val;
  horaDisp.value   = label;
  horaDisp.classList.add('success');

  badgeEl.innerHTML = `<div class="disponibilidad-badge badge-libre">
    ✅ Horario disponible — ${label}
  </div>`;

  actualizarResumen();
  validarFormulario();
}

function resetHora() {
  horaHidden.value = '';
  horaDisp.value   = '';
  horaDisp.classList.remove('success');
  badgeEl.innerHTML = '';
  ocultarResumen();
  validarFormulario();
}

function actualizarResumen() {
  const tipoLabel = tipoSelect.value ? tipoSelect.options[tipoSelect.selectedIndex].text.replace(' (Recomendado)', '') : '';
  const espVisible = grupoEsp.style.display !== 'none';
  const espLabel   = espVisible ? (espSelect.options[espSelect.selectedIndex]?.text || '') : '';
  const fecha = fechaInput.value;
  const hora  = horaDisp.value;

  if (tipoSelect.value && espSelect.value && fecha && hora) {
    const [y,m,d] = fecha.split('-');
    const fechaFmt = `${d}/${m}/${y}`;
    document.getElementById('res-esp').textContent = espVisible && espLabel ? `${tipoLabel} · ${espLabel}` : tipoLabel;
    document.getElementById('res-fecha').textContent = fechaFmt;
    document.getElementById('res-hora').textContent  = hora;
    resumen.classList.add('visible');
    document.getElementById('step3').classList.add('active');
  } else {
    ocultarResumen();
  }
}

function ocultarResumen() {
  resumen.classList.remove('visible');
  document.getElementById('step3').classList.remove('active');
}

function validarFormulario() {
  const ok = tipoSelect.value && espSelect.value && fechaInput.value && horaHidden.value;
  btnAgendar.disabled = !ok;
}

// ── Modo urgencia: atiende hoy con la especialidad de emergencias ──
function aplicarModoUrgencia(activo) {
  modoUrgencia = activo;

  if (activo) {
    // 1. Fijar especialidad de urgencias (Cirugía Oral / Emergencias).
    grupoEsp.style.display = 'none';
    espSelect.value = (TIPOS_ESP['urgencia'] != null)
      ? TIPOS_ESP['urgencia']
      : URGENCIA_ESPECIALIDAD_ID;

    // 2. Establecer la fecha de hoy (se habilita el día actual solo aquí).
    fechaInput.min = hoyStr;
    fechaInput.value = hoyStr;

    // 3. Invitar a describir el síntoma.
    resaltarMotivo();
  } else {
    // Restaurar la regla general: citas a partir de mañana.
    fechaInput.min = mananaStr;
    if (fechaInput.value && fechaInput.value < mananaStr) {
      fechaInput.value = '';
    }
  }
}

// Resalta suavemente el campo "Descripción / Motivo" invitando a escribir.
function resaltarMotivo() {
  const grupo = msgArea.closest('.field-group');
  if (!grupo) return;
  grupo.classList.add('campo-destacado');
  msgArea.focus({ preventScroll: true });
  clearTimeout(resaltarMotivo._t);
  resaltarMotivo._t = setTimeout(function () {
    grupo.classList.remove('campo-destacado');
  }, 4500);
}

// Prioriza el turno más cercano a la hora actual (aplica a citas de hoy).
function priorizarTurnoCercano(grid) {
  const botones = Array.prototype.slice.call(
    grid.querySelectorAll('.hora-btn:not(.ocupada)')
  );
  if (!botones.length) return;

  const ahora = new Date();
  const minutosAhora = ahora.getHours() * 60 + ahora.getMinutes();
  const aMinutos = function (v) {
    const partes = (v || '').split(':');
    return parseInt(partes[0], 10) * 60 + parseInt(partes[1], 10);
  };

  const elegido = botones.find(function (b) {
    return aMinutos(b.dataset.val) >= minutosAhora;
  }) || botones[0];

  elegido.classList.add('sugerido');
  elegido.title = 'Turno más cercano';
  elegido.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Tarjetas de tipo de atención (sincronizan el <select> real) ──
document.querySelectorAll('.tipo-card-input').forEach(function (radio) {
  radio.addEventListener('change', function () {
    document.querySelectorAll('.tipo-card').forEach(function (c) {
      c.classList.toggle('selected', c.dataset.key === radio.value);
    });
    tipoSelect.value = radio.value;
    tipoSelect.dispatchEvent(new Event('change'));
  });
});

espSelect.addEventListener('change',  () => { actualizarResumen(); validarFormulario(); });
fechaInput.addEventListener('change', () => { actualizarResumen(); validarFormulario(); resetHora(); });

// ── Carga inicial desde la URL ──────────────────────────────────────────
// Escenarios:
//  - ?especialidad=<id>            -> preselecciona la especialidad.
//  - ?tratamiento_id=<id>          -> el backend ya fija la especialidad y el
//                                     tipo "tratamiento"; aquí se marca el
//                                     tratamiento y se cargan los doctores.
const formCita   = document.getElementById('formCita');
const TIPO_INICIAL = (formCita.dataset.tipo || '').trim();
const TRAT_INICIAL = (formCita.dataset.tratamiento || '').trim();

(function initDesdeUrl() {
  if (TIPO_INICIAL) {
    // Reflejar el tipo en el <select> y en las tarjetas.
    tipoSelect.value = TIPO_INICIAL;
    const radio = document.querySelector(
      '.tipo-card-input[value="' + TIPO_INICIAL + '"]'
    );
    if (radio) {
      radio.checked = true;
      document.querySelectorAll('.tipo-card').forEach(function (c) {
        c.classList.toggle('selected', c.dataset.key === TIPO_INICIAL);
      });
    }
    // No limpiar la especialidad que el backend ya resolvió desde el tratamiento.
    aplicarTipo(TIPO_INICIAL, { preservarEspSelect: true });
  }

  if (!espSelect.value && !TIPO_INICIAL) return;

  resetHora();
  actualizarResumen();
  validarFormulario();
  cargarHorarios();
  cargarTratamientos(TRAT_INICIAL);
  cargarDoctores();
})();

// Validación antes de enviar
let navegarAPago = false;
document.getElementById('formCita').addEventListener('submit', function(e) {
  if (!horaHidden.value) {
    e.preventDefault();
    badgeEl.innerHTML = `<div class="disponibilidad-badge badge-ocupada">
      ⛔ Debes seleccionar un horario
    </div>`;
    return;
  }
  // La navegación a la pantalla de pago es esperada: no preguntar al salir.
  navegarAPago = true;
  btnAgendar.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Registrando...';
  btnAgendar.disabled  = true;
});

// ── Alertas de salida ──────────────────────────────────────────────────────
// Evita perder la reserva a medias: al cerrar/refrescar la pestaña
// (beforeunload) o al usar el botón "atrás" del navegador (popstate) se
// avisa de que los datos y el horario elegido se perderán.
(function () {
  if (!document.getElementById('formCita')) return;

  let modalAbierto = false;
  let bsModal = null;

  function hayDatosIngresados() {
    return !!(
      tipoSelect.value ||
      espSelect.value ||
      fechaInput.value ||
      horaHidden.value ||
      msgArea.value.trim()
    );
  }

  function obtenerModal() {
    if (bsModal) return bsModal;
    const modalEl = document.getElementById('modalAbandonar');
    if (!modalEl || !window.bootstrap || !bootstrap.Modal) return null;
    bsModal = new bootstrap.Modal(modalEl);
    modalEl.addEventListener('hidden.bs.modal', function () {
      modalAbierto = false;
    });
    return bsModal;
  }

  function mostrarModal() {
    const modal = obtenerModal();
    if (!modal) return;
    modalAbierto = true;
    modal.show();
  }

  // 1) Cerrar pestaña / refrescar / navegar a otro sitio.
  window.addEventListener('beforeunload', function (e) {
    if (navegarAPago || modalAbierto || !hayDatosIngresados()) return undefined;
    const aviso =
      'Si sales de esta página, los datos ingresados y el horario ' +
      'seleccionado se perderán.';
    e.preventDefault();
    e.returnValue = aviso;
    return aviso;
  });

  // 2) Botón "atrás" del navegador.
  history.pushState({ pantallaAgendar: true }, '', window.location.href);
  window.addEventListener('popstate', function () {
    if (navegarAPago) return;
    if (modalAbierto) {
      // Ya se está avisando: permanecer en la página mientras decide.
      history.pushState({ pantallaAgendar: true }, '', window.location.href);
      return;
    }
    if (hayDatosIngresados()) {
      history.pushState({ pantallaAgendar: true }, '', window.location.href);
      mostrarModal();
    }
    // Sin datos ingresados se permite la navegación "atrás" habitual.
  });

  const btnContinuar = document.getElementById('btnContinuarAgendamiento');
  const btnAbandonar = document.getElementById('btnAbandonarAgendamiento');

  if (btnContinuar) {
    btnContinuar.addEventListener('click', function () {
      const modal = obtenerModal();
      if (modal) modal.hide();
    });
  }

  if (btnAbandonar) {
    btnAbandonar.addEventListener('click', function () {
      navegarAPago = true; // no volver a preguntar al salir
      const modal = obtenerModal();
      if (modal) modal.hide();
      // Salir de la página de agendamiento (a la que vino el paciente).
      const referrer = document.referrer;
      window.location.href =
        referrer && referrer !== window.location.href ? referrer : '/';
    });
  }
})();