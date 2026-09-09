function togglePassword(id) {
    const input = document.getElementById(id);

    if (input.type === "password") {
        input.type = "text";
    } else {
        input.type = "password";
    }
}

document.addEventListener("DOMContentLoaded", function () {
    let fechaInput = document.getElementById("fecha");

    if (!fechaInput) return;

    let hoy = new Date();
    hoy.setDate(hoy.getDate() + 1);

    let yyyy = hoy.getFullYear();
    let mm = String(hoy.getMonth() + 1).padStart(2, '0');
    let dd = String(hoy.getDate()).padStart(2, '0');

    let manana = `${yyyy}-${mm}-${dd}`;

    fechaInput.setAttribute("min", manana);
});

