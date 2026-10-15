/* ============================================================
   Clinica Seledent - Seccion Especialidades
   Filtro por pestanas de categoria
   ============================================================ */
(function () {
    "use strict";

    const grid = document.getElementById("espGrid");
    if (!grid) return;

    /* ---------- Sombra de la barra al hacer scroll ---------- */
    const navbar = document.getElementById("navbar");
    if (navbar) {
        window.addEventListener("scroll", () => {
            navbar.classList.toggle("scrolled", window.scrollY > 20);
        });
    }

    const columnas = Array.from(grid.querySelectorAll(".esp-col"));
    const pestanas = Array.from(document.querySelectorAll(".esp-tab"));

    /* ---------- Comparacion sin acentos ni mayusculas ---------- */
    function normalizar(texto) {
        return (texto || "")
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");
    }

    /* Duracion (ms) que debe coincidir con la transicion CSS de .esp-col */
    const DURACION_FADE = 280;

    /* ---------- Mostrar una tarjeta con transicion de entrada ---------- */
    function mostrarColumna(col) {
        col.dataset.estado = "visible";
        col.classList.remove("is-oculto");
        /* Forzar reflow para que la transicion de entrada se reproduzca */
        void col.offsetWidth;
        col.classList.remove("is-fade-out");
    }

    /* ---------- Ocultar una tarjeta con transicion de salida ---------- */
    function ocultarColumna(col) {
        col.dataset.estado = "oculto";
        col.classList.add("is-fade-out");
        window.setTimeout(() => {
            /* Solo se retira del flujo si sigue debiendo ocultarse */
            if (col.dataset.estado === "oculto") {
                col.classList.add("is-oculto");
            }
        }, DURACION_FADE);
    }

    /* ---------- Filtro por categoria ---------- */
    function filtrar(categoria) {
        const objetivo = normalizar(categoria);
        const mostrarTodas = objetivo === "todas";

        let visibles = 0;

        columnas.forEach((col) => {
            /* La tarjeta destacada solo aparece en la vista "Todas" */
            const esDestacada = col.classList.contains("esp-col--destacada");
            const visible = esDestacada
                ? mostrarTodas
                : mostrarTodas || normalizar(col.dataset.categoria) === objetivo;

            if (visible) {
                mostrarColumna(col);
                if (!esDestacada) visibles++;
            } else {
                ocultarColumna(col);
            }
        });

        return visibles;
    }

    function marcarPestana(pestanaActiva) {
        pestanas.forEach((tab) => {
            const activo = tab === pestanaActiva;
            tab.classList.toggle("is-active", activo);
            tab.setAttribute("aria-selected", activo ? "true" : "false");
        });
    }

    pestanas.forEach((tab) => {
        tab.addEventListener("click", () => {
            filtrar(tab.dataset.filtro);
            marcarPestana(tab);
        });
    });

    /* Estado inicial: todas las especialidades visibles */
    filtrar("todas");
})();