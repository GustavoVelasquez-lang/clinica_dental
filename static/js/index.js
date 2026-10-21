/* ============================================================
   Clinica SELEDENT - Home (navbar + buscador)
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Navbar: sombra al hacer scroll ---------- */
  var navbar = document.getElementById("navbar");
  if (navbar) {
    window.addEventListener("scroll", function () {
      navbar.classList.toggle("scrolled", window.scrollY > 20);
    });
  }

  /* ---------- Buscador de especialidades ---------- */
  var input = document.getElementById("busqueda");
  var btn   = document.getElementById("btnBuscar");

  if (input && btn) {
    function buscar() {
      var texto = input.value.trim();

      if (!texto) {
        input.focus();
        return;
      }

      window.location.href = "/buscar?q=" + encodeURIComponent(texto);
    }

    btn.addEventListener("click", buscar);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") buscar();
    });
  }
})();