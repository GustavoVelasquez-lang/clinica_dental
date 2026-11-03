// DNI lookup for registration - autofill and lock name fields
(function(){
  var dniInput = document.getElementById('dni');
  var btn = document.getElementById('btnConsultarDni');
  var statusEl = document.getElementById('dniStatus');
  var nombre = document.getElementById('nombre');
  var apeP = document.getElementById('apePaterno');
  var apeM = document.getElementById('apeMaterno');

  function setStatus(msg, ok){
    if(!statusEl) return;
    statusEl.textContent = msg || '';
    statusEl.classList.toggle('text-success', !!ok);
    statusEl.classList.toggle('text-danger', ok === false);
    statusEl.classList.toggle('text-muted', ok === undefined || ok === null);
  }

  function lockFields(){
    [nombre, apeP, apeM].forEach(function(el){
      if(!el) return;
      el.readOnly = true;
      el.classList.add('bg-light');
    });
  }

  function unlockFields(){
    [nombre, apeP, apeM].forEach(function(el){
      if(!el) return;
      el.readOnly = false;
      el.classList.remove('bg-light');
    });
  }

  lockFields();

  function consultar(){
    var dni = (dniInput.value || '').trim();
    if(!/^\d{8}$/.test(dni)){
      setStatus('Ingresa un DNI válido de 8 dígitos.', false);
      unlockFields();
      return;
    }
    if(btn){ btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>'; }
    setStatus('Consultando RENIEC...', null);
    fetch('/api/consultar-dni/' + encodeURIComponent(dni))
      .then(function(r){ return r.json(); })
      .then(function(data){
        if(data && data.success){
          if(nombre){ nombre.value = (data.nombres || '').toUpperCase(); nombre.readOnly = true; nombre.classList.add('bg-light'); }
          if(apeP){ apeP.value = (data.apePaterno || '').toUpperCase(); apeP.readOnly = true; apeP.classList.add('bg-light'); }
          if(apeM){ apeM.value = (data.apeMaterno || '').toUpperCase(); apeM.readOnly = true; apeM.classList.add('bg-light'); }
          setStatus('Datos autocompletados con RENIEC.', true);
        }else{
          setStatus(data && data.mensaje ? data.mensaje : 'No se encontraron datos.', false);
          unlockFields();
        }
      })
      .catch(function(){
        setStatus('Error al consultar el DNI.', false);
        unlockFields();
      })
      .finally(function(){
        if(btn){ btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i>'; }
      });
  }

  if(btn){ btn.addEventListener('click', consultar); }
  if(dniInput){
    dniInput.addEventListener('input', function(){
      var v = (dniInput.value || '').replace(/\D/g,'').slice(0,8);
      dniInput.value = v;
      if(v.length === 8){
        consultar();
      }else{
        setStatus('Ingresa 8 dígitos para autocompletar.', null);
        // keep locked until valid lookup
        lockFields();
      }
    });
  }
})();
