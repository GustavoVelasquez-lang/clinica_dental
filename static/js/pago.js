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
})();
