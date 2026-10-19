(function () {
  const input = document.getElementById('voucher');
  const dropZone = document.getElementById('dropZone');
  const nro = document.getElementById('nro_operacion');

  // ── Número de operación: solo dígitos ──
  if (nro) {
    nro.addEventListener('input', function () {
      nro.value = nro.value.replace(/\D/g, '');
    });
    nro.addEventListener('keydown', function (e) {
      const permitidas = ['Backspace', 'Delete', 'Tab', 'ArrowLeft', 'ArrowRight', 'Home', 'End'];
      if (permitidas.includes(e.key) || e.ctrlKey || e.metaKey) return;
      if (!/^\d$/.test(e.key)) e.preventDefault();
    });
  }

  // ── Copiar número de Yape ──
  const btnCopiar = document.getElementById('btnCopiarNumero');
  if (btnCopiar) {
    btnCopiar.addEventListener('click', function () {
      const texto = '+51 ' + (btnCopiar.dataset.numero || '');
      const marcar = function () {
        const original = btnCopiar.innerHTML;
        btnCopiar.classList.add('copiado');
        btnCopiar.innerHTML = '<i class="fa-solid fa-check"></i> ¡Copiado!';
        setTimeout(function () {
          btnCopiar.classList.remove('copiado');
          btnCopiar.innerHTML = original;
        }, 1800);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(texto).then(marcar).catch(function () {
          copiarFallback(texto, marcar);
        });
      } else {
        copiarFallback(texto, marcar);
      }
    });
  }

  function copiarFallback(texto, done) {
    const tmp = document.createElement('textarea');
    tmp.value = texto;
    tmp.style.position = 'fixed';
    tmp.style.opacity = '0';
    document.body.appendChild(tmp);
    tmp.select();
    try { document.execCommand('copy'); done(); } catch (e) { /* sin soporte */ }
    document.body.removeChild(tmp);
  }

  // ── Vista previa del comprobante (selección o arrastre) ──
  if (input && dropZone) {
    const mostrarArchivo = function (file) {
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function (ev) {
        document.getElementById('dropContent').style.display = 'none';
        document.getElementById('filePreview').style.display = 'block';
        document.getElementById('previewImg').src = ev.target.result;
        document.getElementById('fileName').textContent = file.name;
      };
      reader.readAsDataURL(file);
    };

    input.addEventListener('change', function (e) {
      mostrarArchivo(e.target.files[0]);
    });

    dropZone.addEventListener('click', function () {
      input.click();
    });

    ['dragenter', 'dragover'].forEach(function (evt) {
      dropZone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropZone.classList.add('dropzone--activo');
      });
    });

    ['dragleave', 'drop'].forEach(function (evt) {
      dropZone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropZone.classList.remove('dropzone--activo');
      });
    });

    dropZone.addEventListener('drop', function (e) {
      const files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) {
        input.files = files;
        mostrarArchivo(files[0]);
      }
    });
  }

  // ── Modal de advertencia antes de "Pagar después" ──────────────────────
  // El botón #btnPagarDespues envía el formulario de reserva; aquí se
  // intercepta para avisar que, sin pago, la cita NO queda asegurada.
  const btnPagarDespues = document.getElementById('btnPagarDespues');
  const overlay = document.getElementById('modalPagarDespues');

  if (btnPagarDespues && overlay) {
    const btnSeguir = document.getElementById('btnSeguirPago');
    const btnSalir = document.getElementById('btnConfirmarSalir');
    let confirmado = false;
    let ultimoFoco = null;

    const abrirModal = function () {
      ultimoFoco = document.activeElement;
      overlay.hidden = false;
      document.body.style.overflow = 'hidden';
      if (btnSeguir) btnSeguir.focus();
    };

    const cerrarModal = function () {
      overlay.hidden = true;
      document.body.style.overflow = '';
      if (ultimoFoco && typeof ultimoFoco.focus === 'function') {
        ultimoFoco.focus();
      }
    };

    // Intercepta el envío: sin confirmación, abre el aviso.
    btnPagarDespues.addEventListener('click', function (e) {
      if (confirmado) return;
      e.preventDefault();
      abrirModal();
    });

    // Secundario: vuelve a la pasarela sin perder datos.
    if (btnSeguir) {
      btnSeguir.addEventListener('click', function () {
        cerrarModal();
      });
    }

    // Primario: guarda la reserva como pendiente (envía el formulario).
    if (btnSalir) {
      btnSalir.addEventListener('click', function () {
        confirmado = true;
        cerrarModal();
        const form = btnPagarDespues.form || btnPagarDespues.closest('form');
        if (form) {
          if (typeof form.requestSubmit === 'function') {
            form.requestSubmit(btnPagarDespues);
          } else {
            form.submit();
          }
        }
      });
    }

    // Cerrar con Escape y clic en el fondo (equivale a "volver al pago").
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !overlay.hidden) cerrarModal();
    });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) cerrarModal();
    });
  }
})();
