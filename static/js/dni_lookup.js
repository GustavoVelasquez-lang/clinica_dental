// ============================================================
// Clinica Sele Dent - Autocompletado por DNI (RENIEC via Decolecta)
// Helper reutilizable para los formularios de registro,
// completar perfil y "Mis datos".
// ============================================================
(function () {
  "use strict";

  var ENDPOINT = "/api/consultar-dni/";

  function soloDigitos(valor) {
    return (valor || "").replace(/\D/g, "").slice(0, 8);
  }

  function claseEstado(tipo) {
    switch (tipo) {
      case "ok": return "dni-status text-success";
      case "error": return "dni-status text-danger";
      case "warn": return "dni-status text-warning";
      case "info": return "dni-status text-muted";
      default: return "dni-status text-muted";
    }
  }

  function attach(opts) {
    var dni = document.getElementById(opts.dniId || "dni");
    if (!dni) return null;

    var btn = opts.btnId ? document.getElementById(opts.btnId) : null;
    var status = opts.statusId ? document.getElementById(opts.statusId) : null;

    var campos = {
      nombre: document.getElementById(opts.nombreId || "nombre"),
      apePaterno: document.getElementById(opts.apePaternoId || "apePaterno"),
      apeMaterno: document.getElementById(opts.apeMaternoId || "apeMaterno")
    };

    function setStatus(msg, tipo) {
      if (!status) return;
      status.textContent = msg || "";
      status.className = claseEstado(tipo);
    }

    var ultimoConsultado = "";

    dni.addEventListener("input", function () {
      this.value = soloDigitos(this.value);
      if (this.value !== ultimoConsultado) setStatus("", "");
    });

    function aplicar(datos, forzar) {
      var mapa = {
        nombre: datos.nombres,
        apePaterno: datos.apePaterno,
        apeMaterno: datos.apeMaterno
      };
      Object.keys(mapa).forEach(function (clave) {
        var el = campos[clave];
        var valor = mapa[clave];
        if (el && valor && (forzar || !el.value.trim())) {
          el.value = valor;
        }
      });
      if (typeof opts.onData === "function") opts.onData(datos);
    }

    function consultar(forzar) {
      var valor = soloDigitos(dni.value);
      if (valor.length !== 8) {
        setStatus("El DNI debe tener 8 dígitos.", "warn");
        return;
      }
      if (!forzar && valor === ultimoConsultado) return;
      ultimoConsultado = valor;

      setStatus("Buscando en RENIEC...", "info");
      if (btn) btn.disabled = true;

      fetch(ENDPOINT + valor, { headers: { Accept: "application/json" } })
        .then(function (resp) {
          return resp.json().then(function (data) {
            return { data: data };
          });
        })
        .then(function (res) {
          if (btn) btn.disabled = false;
          if (res.data && res.data.success) {
            aplicar(res.data, forzar);
            setStatus("✅ Datos encontrados.", "ok");
          } else {
            var msg = (res.data && res.data.message) || "No se encontró el DNI.";
            setStatus("❌ " + msg, "error");
          }
        })
        .catch(function () {
          if (btn) btn.disabled = false;
          setStatus("❌ No se pudo conectar. Intenta de nuevo.", "error");
        });
    }

    if (btn) {
      btn.addEventListener("click", function () { consultar(true); });
    }
    dni.addEventListener("blur", function () { consultar(false); });

    return { consultar: consultar };
  }

  window.SeleDentDNI = { attach: attach, soloDigitos: soloDigitos };
})();
