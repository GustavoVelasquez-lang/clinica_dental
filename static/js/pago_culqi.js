(function () {
  const cfg = window.PAGO_CONFIG || {};
  const btn = document.getElementById('btnCulqi');
  if (!btn || !cfg.endpoint) return;

  const msg = document.getElementById('culqiMsg');

  function setMensaje(texto, tipo) {
    if (!msg) return;
    msg.textContent = texto || '';
    msg.className = 'culqi-msg' + (tipo ? ' culqi-msg--' + tipo : '');
  }

  function setCargando(activo) {
    btn.disabled = activo;
    btn.classList.toggle('is-loading', activo);
  }

  // Configura el Checkout v4 de Culqi (tarjeta + Yape).
  if (window.Culqi) {
    Culqi.publicKey = cfg.publicKey;
    Culqi.settings({
      title: cfg.title,
      currency: cfg.currency,
      amount: cfg.amountCents,
      description: cfg.description,
    });
  }

  btn.addEventListener('click', function (e) {
    e.preventDefault();
    setMensaje('');
    if (!window.Culqi) {
      setMensaje('No se pudo cargar la pasarela de pago. Recarga la pagina.', 'error');
      return;
    }
    Culqi.open();
  });

  // Checkout v4 invoca window.culqi() al cerrarse el popup.
  window.culqi = function () {
    if (window.Culqi && Culqi.token) {
      enviarToken(Culqi.token.id);
    } else if (window.Culqi && Culqi.order) {
      enviarToken(Culqi.order.id);
    } else if (window.Culqi && Culqi.error) {
      setMensaje(Culqi.error.user_message || Culqi.error.message || 'No se pudo procesar el pago.', 'error');
    }
  };

  function enviarToken(token) {
    if (!token) {
      setMensaje('No se recibio el token de pago.', 'error');
      return;
    }
    setCargando(true);
    setMensaje('Procesando tu pago...', 'info');

    const datos = new FormData();
    datos.append('token', token);

    fetch(cfg.endpoint, {
      method: 'POST',
      body: datos,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (resp) {
        return resp.json().catch(function () {
          return { ok: false, mensaje: 'Respuesta invalida de la pasarela.' };
        });
      })
      .then(function (data) {
        if (data.ok) {
          setMensaje(data.mensaje || 'Pago aprobado.', 'ok');
          setCargando(true);
          setTimeout(function () {
            window.location.href = cfg.redirect;
          }, 1400);
        } else {
          setCargando(false);
          setMensaje(data.mensaje || 'No se pudo procesar el pago.', 'error');
        }
      })
      .catch(function () {
        setCargando(false);
        setMensaje('Error de conexion con la pasarela. Intenta de nuevo.', 'error');
      });
  }
})();
