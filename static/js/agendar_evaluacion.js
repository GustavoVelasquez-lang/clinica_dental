/* ============================================================
   Clinica Sele Dent - Agendar Evaluación
   ============================================================ */
(function () {
    "use strict";

    var fecha = document.getElementById("fecha");
    if (fecha) {
        /* Solo se puede agendar desde mañana */
        var manana = new Date();
        manana.setDate(manana.getDate() + 1);
        var iso = manana.toISOString().split("T")[0];
        fecha.min = iso;
    }

    /* DNI: solo dígitos */
    var dni = document.getElementById("dni");
    if (dni) {
        dni.addEventListener("input", function () {
            dni.value = dni.value.replace(/\D/g, "").slice(0, 8);
        });
    }

    /* WhatsApp: solo dígitos, espacios y + */
    var wa = document.getElementById("whatsapp");
    if (wa) {
        wa.addEventListener("input", function () {
            wa.value = wa.value.replace(/[^\d+\s]/g, "");
        });
    }
})();
