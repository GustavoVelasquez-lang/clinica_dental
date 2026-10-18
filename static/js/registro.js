// ============================================================
// Clinica Sele Dent - Registro (validacion + autocompletado DNI)
// ============================================================
(function () {
  "use strict";

  var form = document.getElementById("formRegistro");
  if (!form) return;

  var correo = document.getElementById("correo");
  var clave = document.getElementById("clave");
  var confirmar = document.getElementById("confirmar");
  var boton = document.getElementById("btnRegistro");

  var RE_CORREO = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

  /* ---------- Mostrar / ocultar contrasenas ---------- */
  function enlazarToggle(toggleId, inputId) {
    var toggle = document.getElementById(toggleId);
    var input = document.getElementById(inputId);
    if (!toggle || !input) return;
    toggle.addEventListener("click", function () {
      var visible = input.type === "text";
      input.type = visible ? "password" : "text";
      toggle.innerHTML = visible
        ? '<i class="fa-regular fa-eye" aria-hidden="true"></i>'
        : '<i class="fa-regular fa-eye-slash" aria-hidden="true"></i>';
    });
  }
  enlazarToggle("toggleClave", "clave");
  enlazarToggle("toggleConfirmar", "confirmar");

  /* ---------- Fecha de nacimiento ---------- */
  var fecha = document.getElementById("fenacimiento");
  if (fecha) {
    fecha.max = new Date().toISOString().slice(0, 10);
  }

  /* ---------- Autocompletado por DNI ---------- */
  if (window.SeleDentDNI) {
    window.SeleDentDNI.attach({
      dniId: "dni",
      btnId: "btnConsultarDni",
      statusId: "dniStatus",
      nombreId: "nombre",
      apePaternoId: "apePaterno",
      apeMaternoId: "apeMaterno"
    });
  }

  /* ---------- Validacion al enviar ---------- */
  form.addEventListener("submit", function (ev) {
    var errores = [];

    var dni = document.getElementById("dni");
    if (dni && dni.value.trim() && !/^\d{8}$/.test(dni.value.trim())) {
      errores.push("El DNI debe tener 8 dígitos.");
    }

    if (fecha && !fecha.value) {
      errores.push("Ingresa tu fecha de nacimiento.");
    } else if (fecha && fecha.max && fecha.value > fecha.max) {
      errores.push("La fecha de nacimiento no puede ser futura.");
    }

    if (!correo.value.trim() || !RE_CORREO.test(correo.value.trim().toLowerCase())) {
      errores.push("Ingresa un correo electronico valido.");
    }

    if (!clave.value || clave.value.length < 4) {
      errores.push("La contrasena debe tener al menos 4 caracteres.");
    } else if (clave.value !== document.getElementById("confirmar").value) {
      errores.push("Las contrasenas no coinciden.");
    }

    if (errores.length) {
      ev.preventDefault();
      window.alert(errores.join("\n"));
      return;
    }

    var btn = document.getElementById("btnRegistro");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Creando cuenta...";
    }
  });
})();
