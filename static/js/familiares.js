// ============================================================
// Clinica Sele Dent - Panel Familiares
// Autocompletado de datos por DNI y validacion del formulario.
// ============================================================
(function () {
  "use strict";

  var form = document.getElementById("formFamiliar");
  if (!form) return;

  var dni = document.getElementById("famDni");
  var nombre = document.getElementById("famNombres");
  var apePaterno = document.getElementById("famApePaterno");
  var apeMaterno = document.getElementById("famApeMaterno");
  var fenacimiento = document.getElementById("famFenacimiento");

  // DNI: solo digitos, maximo 8.
  if (dni) {
    dni.addEventListener("input", function () {
      this.value = this.value.replace(/\D/g, "").slice(0, 8);
    });
  }

  // Autocompletado de nombres/apellidos a partir del DNI.
  if (window.SeleDentDNI && dni) {
    window.SeleDentDNI.attach({
      dniId: "famDni",
      btnId: "btnFamConsultarDni",
      statusId: "famDniStatus",
      nombreId: "famNombres",
      apePaternoId: "famApePaterno",
      apeMaternoId: "famApeMaterno"
    });
  }

  form.addEventListener("submit", function (e) {
    var errores = [];

    if (!dni || !/^\d{8}$/.test(dni.value.trim())) {
      errores.push("El DNI es obligatorio y debe tener 8 dígitos.");
    }
    if (!nombre || !nombre.value.trim()) {
      errores.push("Ingresa los nombres del familiar.");
    }
    if (!apePaterno || !apePaterno.value.trim()) {
      errores.push("Ingresa el apellido paterno del familiar.");
    }
    if (!fenacimiento || !fenacimiento.value) {
      errores.push("La fecha de nacimiento es obligatoria.");
    }

    if (errores.length) {
      e.preventDefault();
      window.alert(errores.join("\n"));
    }
  });
})();
