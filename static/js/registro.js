const dniInput = document.getElementById("dni");
const nombreInput = document.getElementById("nombre");
const apePaternoInput = document.getElementById("apePaterno");
const apeMaternoInput = document.getElementById("apeMaterno");
const resultado = document.getElementById("resultado");

// Detectar cuando el usuario escribe en el campo DNI
dniInput.addEventListener("input", async () => {
  const dni = dniInput.value.trim();

  // Limpiar formulario y mensaje si no tiene 8 dígitos
  if (dni.length !== 8) {
    limpiarCampos();
    resultado.textContent = "";
    return;
  }

  if (/^\d{8}$/.test(dni)) {
    await consultarDNI(dni);
  }
});

async function consultarDNI(dni) {
  resultado.textContent = "";

  try {
    const response = await fetch(`/api/consultar_dni/${dni}`);
    const res = await response.json();

    if (!res.success || !res.data) {
      resultado.className = "mt-3 text-center text-danger fw-bold";
      resultado.textContent = " 