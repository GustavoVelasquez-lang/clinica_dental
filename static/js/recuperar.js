/* ============================================================
   Clinica SELEDENT - Recuperacion de contrasena
   (validaciones de correo, codigo y nueva contrasena)
   ============================================================ */

(function () {
  "use strict";

  var RE_CORREO = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

  /* ---------- Mostrar / ocultar contrasena ---------- */
  document.querySelectorAll(".login-eye[data-eye]").forEach(function (btn) {
    var input = document.getElementById(btn.getAttribute("data-eye"));
    if (!input) return;

    btn.addEventListener("click", function () {
      var visible = input.type === "text";
      input.type = visible ? "password" : "text";
      btn.setAttribute("aria-pressed", String(!visible));
      btn.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
      btn.innerHTML = visible
        ? '<i class="fa-regular fa-eye" aria-hidden="true"></i>'
        : '<i class="fa-regular fa-eye-slash" aria-hidden="true"></i>';
      input.focus();
    });
  });

  /* ---------- Paso 1: correo ---------- */
  var formCorreo = document.getElementById("recuperarForm");
  if (formCorreo) {
    var correo     = document.getElementById("correo");
    var errCorreo  = document.getElementById("errorCorreo");
    var grupoCorreo = correo ? correo.closest(".login-doc-group") : null;
    var submit1    = document.getElementById("recuperarSubmit");

    var validarCorreo = function () {
      if (!correo) return true;
      var ok = RE_CORREO.test(correo.value.trim().toLowerCase());
      if (grupoCorreo) grupoCorreo.classList.toggle("is-error", !ok);
      if (errCorreo) errCorreo.hidden = ok;
      if (ok) correo.removeAttribute("aria-invalid"); else correo.setAttribute("aria-invalid", "true");
      return ok;
    };

    if (correo) {
      correo.addEventListener("input", function () {
        if (grupoCorreo && grupoCorreo.classList.contains("is-error")) validarCorreo();
      });
    }

    formCorreo.addEventListener("submit", function (ev) {
      if (!validarCorreo()) {
        if (correo) correo.focus();
        ev.preventDefault();
        return;
      }
      if (submit1) { submit1.disabled = true; submit1.textContent = "Enviando..."; }
    });
  }

  /* ---------- Paso 2: codigo ---------- */
  var formCodigo = document.getElementById("codigoForm");
  if (formCodigo) {
    var codigo    = document.getElementById("codigo");
    var errCodigo = document.getElementById("errorCodigo");
    var submit2   = document.getElementById("codigoSubmit");

    if (codigo) {
      codigo.addEventListener("input", function () {
        codigo.value = codigo.value.replace(/\D/g, "").slice(0, 6);
        if (errCodigo) errCodigo.hidden = codigo.value.length === 6;
      });
    }

    formCodigo.addEventListener("submit", function (ev) {
      var ok = !!codigo && /^\d{6}$/.test(codigo.value);
      if (errCodigo) errCodigo.hidden = ok;
      if (!ok) {
        if (codigo) codigo.focus();
        ev.preventDefault();
        return;
      }
      if (submit2) { submit2.disabled = true; submit2.textContent = "Verificando..."; }
    });
  }

  /* ---------- Paso 3: nueva contrasena ---------- */
  var formReset = document.getElementById("resetForm");
  if (formReset) {
    var clave      = document.getElementById("clave");
    var confirmar  = document.getElementById("confirmar");
    var errClave   = document.getElementById("errorClave");
    var errConf    = document.getElementById("errorConfirmar");
    var submit3    = document.getElementById("resetSubmit");

    var validar = function () {
      var okClave = !!clave && clave.value.length >= 8;
      var okConf  = !!confirmar && confirmar.value === clave.value && confirmar.value.length >= 8;
      if (errClave) errClave.hidden = okClave;
      if (errConf)  errConf.hidden = okConf;
      return okClave && okConf;
    };

    [clave, confirmar].forEach(function (inp) {
      if (inp) inp.addEventListener("input", function () {
        if (errClave && !errClave.hidden || errConf && !errConf.hidden) validar();
      });
    });

    formReset.addEventListener("submit", function (ev) {
      if (!validar()) {
        ev.preventDefault();
        if (clave && clave.value.length < 8) clave.focus();
        else if (confirmar) confirmar.focus();
        return;
      }
      if (submit3) { submit3.disabled = true; submit3.textContent = "Guardando..."; }
    });
  }
})();
