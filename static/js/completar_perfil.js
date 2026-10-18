// ============================================================
// Clinica Sele Dent - Completar perfil
// ============================================================
(function () {
  "use strict";

  var form = document.getElementById("cpForm");
  if (!form) return;

  var dni = document.getElementById("dni");
  var nombre = document.getElementById("nombre");
  var apePaterno = document.getElementById("apePaterno");
  var apeMaterno = document.getElementById("apeMaterno");
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

  // Autocompletado de nombres/apellidos a partir del DNI.
  if (window.SeleDentDNI && dni) {
    window.SeleDentDNI.attach({
      dniId: "dni",
      btnId: "btnConsultarDni",
      statusId: "dniStatus",
      nombreId: "nombre",
      apePaternoId: "apePaterno",
      apeMaternoId: "apeMaterno"
    });
  }

  form.addEventListener("submit", function (e) {
    var errores = [];

    if (dni && !/^\d{8}$/.test(dni.value.trim())) {
      errores.push("El DNI debe tener 8 dígitos.");
    }

    if (nombre && !nombre.value.trim()) {
      errores.push("Ingresa tus nombres.");
    }

    if (apePaterno && !apePaterno.value.trim()) {
      errores.push("Ingresa tu apellido paterno.");
    }

    if (apeMaterno && !apeMaterno.value.trim()) {
      errores.push("Ingresa tu apellido materno.");
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
