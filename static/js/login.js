/* ============================================================
   Clinica SELEDENT - Login (visibilidad de contrasena,
   validacion de correo y "recordar correo")
   ============================================================ */

(function () {
  "use strict";

  var form      = document.getElementById("loginForm");
  var clave     = document.getElementById("clave");
  var toggle    = document.getElementById("toggleClave");
  var correoInput = document.getElementById("usuario");
  var correoGroup = correoInput ? correoInput.closest(".login-doc-group") : null;
  var errCorreo = document.getElementById("errorUsuario");
  var errClave  = document.getElementById("errorClave");
  var passWrap  = clave ? clave.closest(".login-pass-wrap") : null;
  var recordar  = document.getElementById("recordar");
  var submit    = document.getElementById("loginSubmit");
  var CLAVE     = "seledent_correo";
  var RE_CORREO = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

  /* ---------- Mostrar / ocultar contrasena ---------- */
  if (toggle && clave) {
    toggle.addEventListener("click", function () {
      var visible = clave.type === "text";
      clave.type = visible ? "password" : "text";
      toggle.setAttribute("aria-pressed", String(!visible));
      toggle.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
      toggle.innerHTML = visible
        ? '<i class="fa-regular fa-eye" aria-hidden="true"></i>'
        : '<i class="fa-regular fa-eye-slash" aria-hidden="true"></i>';
      clave.focus();
      var pos = clave.value.length;
      try { clave.setSelectionRange(pos, pos); } catch (e) {}
    });
  }

  /* ---------- Validacion ---------- */
  function limpiarError(input, wrap, error) {
    if (wrap)  wrap.classList.remove("is-error");
    if (error) error.hidden = true;
    if (input) input.removeAttribute("aria-invalid");
  }

  function marcarError(input, wrap, error) {
    if (wrap)  wrap.classList.add("is-error");
    if (error) error.hidden = false;
    if (input) input.setAttribute("aria-invalid", "true");
  }

  function validarCorreo() {
    if (!correoInput) return true;
    var valor = correoInput.value.trim().toLowerCase();
    var ok = RE_CORREO.test(valor);

    if (ok) limpiarError(correoInput, correoGroup, errCorreo);
    else    marcarError(correoInput, correoGroup, errCorreo);
    return ok;
  }

  if (correoInput) {
    correoInput.addEventListener("input", function () {
      if (correoGroup && correoGroup.classList.contains("is-error")) validarCorreo();
    });
  }

  if (clave) {
    clave.addEventListener("input", function () {
      if (passWrap && passWrap.classList.contains("is-error")) {
        limpiarError(clave, passWrap, errClave);
      }
    });
  }

  if (form) {
    form.addEventListener("submit", function (ev) {
      var correoOk = validarCorreo();

      if (!clave || !clave.value.trim()) {
        marcarError(clave, passWrap, errClave);
        ev.preventDefault();
        return;
      }

      if (!correoOk) {
        if (correoInput) correoInput.focus();
        ev.preventDefault();
        return;
      }

      // Recordar correo
      try {
        if (recordar && recordar.checked) {
          localStorage.setItem(CLAVE, correoInput.value.trim());
        } else {
          localStorage.removeItem(CLAVE);
        }
      } catch (e) {}

      if (submit) {
        submit.disabled = true;
        submit.textContent = "Ingresando...";
      }
    });
  }

  /* ---------- Prefijar correo recordado ---------- */
  try {
    var guardado = localStorage.getItem(CLAVE);
    if (guardado && correoInput && !correoInput.value) {
      correoInput.value = guardado;
      if (recordar) recordar.checked = true;
    }
  } catch (e) {}
})();
