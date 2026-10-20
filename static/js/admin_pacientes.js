// ══ Gestión de familiares desde el panel de pacientes (admin) ══
document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("modalFamiliares");
  if (!modal) return;

  const lista = document.getElementById("famLista");
  const count = document.getElementById("famCount");
  const titular = document.getElementById("famTitular");
  const inputPacienteId = document.getElementById("famPacienteId");
  const form = document.getElementById("formFamiliarAdmin");

  // Mover el modal al <body> para evitar heredar transforms del layout.
  if (modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }

  const PARENTESCOS = {
    hijo: "Hijo/a",
    conyuge: "Cónyuge",
    padre: "Padre/Madre",
    otro: "Otro",
  };

  const escapar = (v) =>
    String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  function etiquetaParentesco(valor) {
    if (!valor) return "—";
    return PARENTESCOS[valor.toLowerCase()] || valor;
  }

  function formatearFecha(iso) {
    if (!iso) return "—";
    const [a, m, d] = iso.split("-");
    if (!a || !m || !d) return iso;
    return `${d}/${m}/${a}`;
  }

  function pintarFamiliares(familiares) {
    count.textContent = familiares.length;
    if (!familiares.length) {
      lista.innerHTML =
        '<p class="fam-vacio">Este paciente aún no tiene familiares registrados.</p>';
      return;
    }
    lista.innerHTML = familiares
      .map((f) => {
        const edad = f.edad != null ? `${f.edad} años` : "—";
        return `
        <div class="fam-item" data-familiar-id="${f.id}">
          <div class="fam-avatar">${escapar((f.nombres || "?")[0].toUpperCase())}</div>
          <div class="fam-item-info">
            <span class="fam-item-nombre">${escapar(f.nombre_completo)}</span>
            <span class="fam-item-meta">
              <span class="pill pill-gray">${escapar(etiquetaParentesco(f.parentesco))}</span>
              <span>DNI: ${escapar(f.dni || "—")}</span>
              <span>Nac.: ${escapar(formatearFecha(f.fenacimiento))} (${escapar(edad)})</span>
              <span class="fam-item-citas"><i class="fa-solid fa-calendar-check me-1"></i>${f.citas} cita${f.citas === 1 ? "" : "s"}</span>
            </span>
          </div>
          <button type="button" class="fam-del btn-a btn-red btn-fam-del"
                  data-familiar-id="${f.id}"
                  data-familiar-nombre="${escapar(f.nombre_completo)}"
                  title="Eliminar familiar">
            <i class="fa-solid fa-trash"></i>
          </button>
        </div>`;
      })
      .join("");
  }

  async function cargarFamiliares(pacienteId) {
    lista.innerHTML = '<p class="fam-vacio">Cargando familiares…</p>';
    try {
      const resp = await fetch(`/admin/pacientes/${pacienteId}/familiares`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await resp.json();
      if (!data.ok) throw new Error(data.mensaje || "Error al cargar.");
      pintarFamiliares(data.familiares || []);
    } catch (e) {
      lista.innerHTML = `<p class="fam-vacio fam-vacio--error">${escapar(e.message)}</p>`;
    }
  }

  modal.addEventListener("show.bs.modal", function (event) {
    const boton = event.relatedTarget;
    if (!boton) return;
    const pacienteId = boton.dataset.pacienteId;
    inputPacienteId.value = pacienteId;
    titular.textContent = boton.dataset.pacienteNombre || "—";
    form.reset();
    cargarFamiliares(pacienteId);
  });

  // Alta de familiar
  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const pacienteId = inputPacienteId.value;
    if (!pacienteId) return;

    const btn = form.querySelector('button[type="submit"]');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Guardando…';

    try {
      const resp = await fetch(`/admin/pacientes/${pacienteId}/familiares`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          nombres: form.elements.nombres.value.trim(),
          ape_paterno: form.elements.ape_paterno.value.trim(),
          ape_materno: form.elements.ape_materno.value.trim(),
          parentesco: form.elements.parentesco.value,
          dni: form.elements.dni.value.trim(),
          fenacimiento: form.elements.fenacimiento.value,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.mensaje || "No se pudo registrar.");
      form.reset();
      cargarFamiliares(pacienteId);
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = original;
    }
  });

  // Eliminar familiar (delegación de eventos)
  lista.addEventListener("click", async function (event) {
    const btn = event.target.closest(".btn-fam-del");
    if (!btn) return;
    const familiarId = btn.dataset.familiarId;
    const nombre = btn.dataset.familiarNombre || "este familiar";
    if (!confirm(`¿Eliminar a ${nombre}? Esta acción no se puede deshacer.`)) return;

    try {
      const resp = await fetch(`/admin/pacientes/familiares/${familiarId}`, {
        method: "DELETE",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.mensaje || "No se pudo eliminar.");
      const pacienteId = inputPacienteId.value;
      cargarFamiliares(pacienteId);
    } catch (e) {
      alert(e.message);
    }
  });
});
