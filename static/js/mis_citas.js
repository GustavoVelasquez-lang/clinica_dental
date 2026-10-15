// ============================================================
// Clinica SELEDENT - Dashboard "Mis Citas"
// Modales de reprogramar / cancelar cita
// ============================================================
(function () {
  "use strict";

  var formRepro = document.getElementById("formReprogramar");
  var formCancel = document.getElementById("formCancelar");

  // ── Precargar datos en el modal de reprogramar ──
  var modalRepro = document.getElementById("modalReprogramar");
  if (modalRepro && formRepro) {
    modalRepro.addEventListener("show.bs.modal", function (event) {
      var btn = event.relatedTarget;
      if (!btn) return;

      formRepro.action = btn.dataset.accion || "";

      var esp = document.getElementById("rpEspecialidad");
      var fecha = document.getElementById("rpFechaActual");
      if (esp) esp.textContent = btn.dataset.especialidad || "";
      if (fecha) fecha.textContent = "· " + (btn.dataset.fecha || "");

      var inputFecha = document.getElementById("rpFecha");
      if (inputFecha) inputFecha.value = "";
    });
  }

  // ── Precargar datos en el modal de cancelar ──
  var modalCancel = document.getElementById("modalCancelar");
  if (modalCancel && formCancel) {
    modalCancel.addEventListener("show.bs.modal", function (event) {
      var btn = event.relatedTarget;
      if (!btn) return;

      formCancel.action = btn.dataset.accion || "";

      var esp = document.getElementById("cnEspecialidad");
      var fecha = document.getElementById("cnFecha");
      if (esp) esp.textContent = btn.dataset.especialidad || "";
      if (fecha) fecha.textContent = "del " + (btn.dataset.fecha || "");

      var motivo = document.getElementById("cnMotivo");
      if (motivo) motivo.value = "";
    });
  }
})();
