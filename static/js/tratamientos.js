/* ============================================================
   Clinica Sele Dent - Página pública de Tratamientos
   Filtro por especialidad (pestañas)
   ============================================================ */
(function () {
  "use strict";

  const cont = document.getElementById("tratGroups");
  if (!cont) return;

  /* Sombra de la barra al hacer scroll */
  const navbar = document.getElementById("navbar");
  if (navbar) {
    window.addEventListener("scroll", function () {
      navbar.classList.toggle("scrolled", window.scrollY > 20);
    });
  }

  const grupos = Array.prototype.slice.call(cont.querySelectorAll(".trat-group"));
  const tabs = Array.prototype.slice.call(document.querySelectorAll(".trat-tab"));

  function filtrar(valor) {
    grupos.forEach(function (g) {
      const visible = valor === "todas" || g.dataset.especialidad === valor;
      g.style.display = visible ? "" : "none";
    });
  }

  function marcarTab(activa) {
    tabs.forEach(function (t) {
      const on = t === activa;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      marcarTab(tab);
      filtrar(tab.dataset.filtro);
    });
  });
})();
