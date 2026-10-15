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
    var RUTAS = {
      "ortodoncia":  "ortodoncia",
      "endodoncia":  "endodoncia",
      "limpieza":    "odontologia general",
      "general":     "odontologia general",
      "cirugia":     "cirugia oral",
      "extraccion":  "cirugia oral",
      "implant":     "implantologia",
      "periodoncia": "periodoncia",
      "blanqueam":   "estetica dental",
      "estetica":    "estetica dental"
    };

    function normalizar(s) {
      return s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    }

    function buscar() {
      var texto = normalizar(input.value.trim());

      if (!texto) {
        input.focus();
        return;
      }

      var encontrada = null;
      Object.keys(RUTAS).forEach(function (clave) {
        if (!encontrada && texto.indexOf(clave) !== -1) {
          encontrada = RUTAS[clave];
        }
      });

      window.location.href = encontrada
        ? "/especialidades?buscar=" + encodeURIComponent(encontrada)
        : "/especialidades";
    }

    btn.addEventListener("click", buscar);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") buscar();
    });
  }
})();