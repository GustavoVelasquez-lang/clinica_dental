// ============================================================
// Clinica SELEDENT - JS global
// Pantalla de carga (loading overlay) + utilidades comunes.
// Expone window.showLoader() / window.hideLoader() para activar el
// overlay durante navegaciones y peticiones asíncronas (DNI, perfil…).
// ============================================================
(function () {
  "use strict";

  var LOADER_ID = "global-loader";
  var TIMEOUT_MS = 8000; // Respaldo: nunca bloquear la pantalla más de 8 segundos
  var _timer = null;

  function mostrar() {
    var loader = document.getElementById(LOADER_ID);
    if (!loader) return;
    loader.classList.remove("hidden");
    loader.setAttribute("aria-hidden", "false");
    if (_timer) clearTimeout(_timer);
    _timer = setTimeout(ocultar, TIMEOUT_MS);
  }

  function ocultar() {
    if (_timer) { clearTimeout(_timer); _timer = null; }
    var loader = document.getElementById(LOADER_ID);
    if (!loader) return;
    loader.classList.add("hidden");
    loader.setAttribute("aria-hidden", "true");
  }

  // API global para usarse desde cualquier script.
  window.showLoader = mostrar;
  window.hideLoader = ocultar;

  // ── Se oculta al terminar de cargar la vista (o al volver con atrás/adelante) ──
  document.addEventListener("DOMContentLoaded", ocultar);
  window.addEventListener("load", ocultar);
  window.addEventListener("pageshow", ocultar);

  // ── Navegación: clic en enlaces internos ──
  function esNavegacion(a, ev) {
    if (!a || !a.href) return false;
    if (a.dataset && a.dataset.noLoader !== undefined) return false;
    if (a.target && a.target !== "" && a.target !== "_self") return false;
    if (a.hasAttribute("download")) return false;
    if (ev && (ev.defaultPrevented || ev.button !== 0 ||
               ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey)) return false;

    var href = a.getAttribute("href") || "";
    if (href === "" || href.charAt(0) === "#") return false;
    if (/^(mailto:|tel:|javascript:|whatsapp:)/i.test(href)) return false;

    try {
      var url = new URL(a.href, window.location.href);
      if (url.origin !== window.location.origin) return false;
      // Mismo documento y solo un ancla => no hay navegación real.
      if (url.pathname === window.location.pathname &&
          url.search === window.location.search && url.hash) {
        return false;
      }
    } catch (err) {
      return false;
    }
    return true;
  }

  document.addEventListener("click", function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
    if (!esNavegacion(a, ev)) return;
    // Diferido para respetar el preventDefault() de un onclick (p. ej. confirm()).
    setTimeout(function () {
      if (!ev.defaultPrevented) mostrar();
    }, 0);
  }, true);

  // ── Navegación: envío de formularios ──
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form || form.tagName !== "FORM") return;
    if (form.dataset && form.dataset.noLoader !== undefined) return;
    if (form.target && form.target !== "" && form.target !== "_self") return;
    setTimeout(function () {
      if (!ev.defaultPrevented) mostrar();
    }, 0);
  }, true);
})();

// Mensajes flash (alertas de Flask): fundido y cierre automático.
document.addEventListener('DOMContentLoaded', function () {
    var alerts = document.querySelectorAll('.alert');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(function () { alert.remove(); }, 500);
        }, 5000);
    });
});
