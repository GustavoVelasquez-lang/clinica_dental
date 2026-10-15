/* ============================================================
   Clinica Seledent - Modulo Contacto
   Validacion en cliente, contador y spinner de envio
   ============================================================ */
(function () {
    "use strict";

    const form = document.getElementById("formContacto");
    if (!form) return;

    const btn = document.getElementById("ctEnviar");
    const mensaje = document.getElementById("mensaje");
    const contador = document.getElementById("ctContador");
    const LIMITE = 2000;

    /* ---------- Contador de caracteres ---------- */
    if (mensaje && contador) {
        const actualizar = () => {
            contador.textContent = String(mensaje.value.length);
        };
        mensaje.addEventListener("input", actualizar);
        actualizar();
    }

    /* ---------- Marca los campos ya tocados ---------- */
    form.querySelectorAll("input, select, textarea").forEach((campo) => {
        campo.addEventListener("blur", () => {
            if (campo.value.trim() !== "") campo.classList.add("is-touched");
        });
    });

    /* ---------- Validacion antes de enviar ---------- */
    function revisar() {
        let ok = true;
        const primerError = [];

        form.querySelectorAll("[required]").forEach((campo) => {
            let valido = campo.checkValidity();

            /* El mensaje exige ademas 10 caracteres utiles */
            if (valido && campo.name === "mensaje" && campo.value.trim().length < 10) {
                valido = false;
            }

            if (valido) {
                campo.classList.remove("is-invalid");
            } else {
                campo.classList.add("is-invalid");
                if (primerError.indexOf(campo) === -1) primerError.push(campo);
                ok = false;
            }
        });

        return { ok: ok, campos: primerError };
    }

    form.addEventListener("submit", function (e) {
        const revision = revisar();

        if (!revision.ok) {
            e.preventDefault();
            revision.campos[0].focus();
            return;
        }

        /* Envia: deshabilita controles y muestra el spinner */
        if (btn) {
            btn.classList.add("is-loading");
            btn.disabled = true;
            btn.querySelector(".ct-btn__texto").textContent = "Enviando...";
        }
        form.querySelectorAll("input, select, textarea").forEach((campo) => {
            campo.disabled = true;
        });
    });

    /* ---------- Limpia el error al corregir ---------- */
    form.querySelectorAll("input, select, textarea").forEach((campo) => {
        campo.addEventListener("input", () => {
            if (campo.classList.contains("is-invalid") && campo.checkValidity()) {
                campo.classList.remove("is-invalid");
            }
        });
    });
})();