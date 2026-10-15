document.querySelectorAll('.js-toggle-pw').forEach(function (btn) {
  btn.addEventListener('click', function () {
    const id = btn.getAttribute('data-target');
    const input = document.getElementById(id);
    if (input) {
      input.type = input.type === 'password' ? 'text' : 'password';
    }
  });
});