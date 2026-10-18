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
    // Solo mayores de edad: entre 1927 y 18 años atrás.
    var hoyFecha = new Date();
    var mes = hoyFecha.getMonth() + 1;
    var dia = hoyFecha.getDate();
    fecha.min = "1927-01-01";
    fecha.max = (hoyFecha.getFullYear() - 18) + "-" +
      (mes < 10 ? "0" + mes : mes) + "-" + (dia < 10 ? "0" + dia : dia);
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

  /* ---------- Contrasena segura (validacion dinamica) ---------- */
  var reglasPassword = [
    { id: "length", test: function (v) { return v.length >= 8; } },
    { id: "upper", test: function (v) { return /[A-Z]/.test(v); } },
    { id: "lower", test: function (v) { return /[a-z]/.test(v); } },
    { id: "number", test: function (v) { return /\d/.test(v); } },
    { id: "special", test: function (v) { return /[@$!%*?&_-]/.test(v); } }
  ];

  var passReq = document.getElementById("passRequisitos");
  var confirmMsg = document.getElementById("passConfirmMsg");
  var tocadoPassword = false;

  function passwordEsSegura(valor) {
    return reglasPassword.every(function (r) { return r.test(valor); });
  }

  function actualizarRequisitos() {
    if (!passReq) return;
    var valor = clave ? clave.value : "";
    reglasPassword.forEach(function (r) {
      var li = passReq.querySelector('[data-req="' + r.id + '"]');
      if (!li) return;
      li.classList.remove("ok", "bad");
      if (!tocadoPassword) return;
      var cumple = r.test(valor);
      li.classList.add(cumple ? "ok" : "bad");
      var icono = li.querySelector("i");
      if (icono) {
        icono.className = cumple
          ? "fa-solid fa-circle-check"
          : "fa-solid fa-circle-xmark";
      }
    });
  }

  function actualizarBoton() {
    if (boton) {
      var claveOk = passwordEsSegura(clave.value);
      var coincide = clave.value.length > 0 && clave.value === confirmar.value;
      boton.disabled = !(claveOk && coincide);
    }
    if (confirmMsg) {
      confirmMsg.hidden = !(confirmar.value.length > 0 && clave.value !== confirmar.value);
    }
  }

  function actualizarPasswordUI() {
    actualizarRequisitos();
    actualizarBoton();
  }

  if (clave) {
    clave.addEventListener("focus", function () {
      tocadoPassword = true;
      actualizarRequisitos();
    });
    clave.addEventListener("input", function () {
      tocadoPassword = true;
      actualizarPasswordUI();
    });
  }
  if (confirmar) {
    confirmar.addEventListener("input", actualizarBoton);
  }

  // Estado inicial: boton deshabilitado hasta cumplir los requisitos.
  actualizarPasswordUI();
  // Reaplica el estado si el navegador autorrellena o restaura el formulario.
  window.addEventListener("pageshow", actualizarPasswordUI);

  /* ---------- Validacion al enviar ---------- */
  form.addEventListener("submit", function (ev) {
    var errores = [];

    var dni = document.getElementById("dni");
    if (dni && !/^\d{8}$/.test(dni.value.trim())) {
      errores.push("El DNI es obligatorio y debe tener 8 dígitos.");
    }

    if (fecha && !fecha.value) {
      errores.push("Ingresa tu fecha de nacimiento.");
    } else if (fecha && fecha.max && fecha.value > fecha.max) {
      errores.push("Debes ser mayor de edad (18 años) para poder registrarte.");
    } else if (fecha && fecha.min && fecha.value < fecha.min) {
      errores.push("La fecha de nacimiento no puede ser anterior a 1927.");
    }

    if (!correo.value.trim() || !RE_CORREO.test(correo.value.trim().toLowerCase())) {
      errores.push("Ingresa un correo electronico valido.");
    }

    if (!passwordEsSegura(clave.value)) {
      errores.push("La contraseña debe tener al menos 8 caracteres, una mayúscula, una minúscula, un número y un carácter especial (@, $, !, %, *, ?, &, -, _).");
    } else if (clave.value !== confirmar.value) {
      errores.push("Las contraseñas no coinciden.");
    }

    if (errores.length) {
      ev.preventDefault();
      window.alert(errores.join("\n"));
      return;
    }

    if (boton) {
      boton.disabled = true;
      boton.textContent = "Creando cuenta...";
    }
  });
})();
