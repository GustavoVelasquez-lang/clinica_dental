// ============================================================
// Clinica Sele Dent - Completar perfil
// ============================================================
(function () {
  "use strict";

  var form = document.getElementById("cpForm");
  if (!form) return;

  var dni = document.getElementById("dni");
  var telefono = document.getElementById("telefono");

  // DNI: solo dígitos, máximo 8.
  if (dni) {
    dni.addEventListener("input", function () {
      this.value = this.value.replace(/\D/g, "").slice(0, 8);
    });
  }

  // Teléfono: dígitos, espacios y "+".
  if (telefono) {
    telefono.addEventListener("input", function () {
      this.value = this.value.replace(/[^\d+\s]/g, "");
    });
  }

  form.addEventListener("submit", function (e) {
    var errores = [];

    if (dni && !/^\d{8}$/.test(dni.value.trim())) {
      errores.push("El DNI debe tener 8 dígitos.");
    }

    if (telefono && !/^[0-9+\s]{6,20}$/.test(telefono.value.trim())) {
      errores.push("Ingresa un número de WhatsApp válido.");
    }

    if (errores.length) {
      e.preventDefault();
      window.alert(errores.join("\n"));
    }
  });
})();
