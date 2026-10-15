const DASH = JSON.parse(document.getElementById('dashData').textContent);

/* bar chart */
const diasN = DASH.labels;
const actual = DASH.actual;
const pasado = DASH.pasado;
const maxBar = Math.max(1, ...actual, ...pasado);
const barEl = document.getElementById("barChart");
diasN.forEach((d, i) => {
  const g = document.createElement("div");
  g.className = "bar-group";
  const hA = Math.round((actual[i] / maxBar) * 140);
  const hP = Math.round((pasado[i] / maxBar) * 140);
  g.innerHTML = `<div class="bar-wrap">
    <div class="bar citas bar-inicial" data-h="${hA}" title="Actual: ${actual[i]}"></div>
    <div class="bar pacientes bar-inicial" data-h="${hP}" title="Semana pasada: ${pasado[i]}"></div>
  </div><span class="bar-label">${d}</span>`;
  barEl.appendChild(g);
});

/* donut */
const esp = DASH.esp;
const circ = 2 * Math.PI * 54;
let off = 0;
esp.forEach((e) => {
  const len = (e.pct / 100) * circ;
  const el = document.getElementById(e.id);
  setTimeout(() => {
    el.setAttribute("stroke-dasharray", `${len} ${circ - len}`);
    el.setAttribute("stroke-dashoffset", -(off - circ * 0.25));
  }, 100);
  off += len;
});
const legEl = document.getElementById("espLegend");
if (esp.length === 0) {
  legEl.innerHTML = '<span class="graf-vacio">Sin datos este mes.</span>';
}
esp.forEach((e) => {
  legEl.innerHTML += `<div class="esp-legend-item">
    <div class="esp-dot" style="background:${e.color}"></div>
    <span class="esp-legend-name">${e.nombre}</span>
    <div class="esp-legend-bar"><div class="esp-legend-bar-fill" data-w="${e.pct}" style="background:${e.color}"></div></div>
    <span class="esp-legend-pct">${e.pct}%</span>
  </div>`;
});

/* ingresos */
const ing = DASH.ing;
const ingEl = document.getElementById("ingresosList");
if (ing.length === 0) {
  ingEl.innerHTML = '<span class="graf-vacio-claro">Sin ingresos este mes.</span>';
}
ing.forEach((i) => {
  ingEl.innerHTML += `<div class="ingreso-item">
    <span class="ingreso-item-name">${i.nombre}</span>
    <div class="ingreso-item-bar-wrap"><div class="ingreso-item-bar" data-w="${i.pct}"></div></div>
    <span class="ingreso-item-val">${i.val}</span>
  </div>`;
});

/* contador */
function animateCount(el) {
  const target = parseInt(el.dataset.target);
  const prefix = el.dataset.prefix || "";
  const dur = 1200, step = 16;
  let cur = 0;
  const inc = target / (dur / step);
  const t = setInterval(() => {
    cur = Math.min(cur + inc, target);
    el.textContent = prefix + Math.round(cur).toLocaleString("es-PE");
    if (cur >= target) clearInterval(t);
  }, step);
}

/* observer */
const obs = new IntersectionObserver(
  (entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.querySelectorAll(".bar[data-h]").forEach((b) => {
        setTimeout(() => { b.style.height = b.dataset.h + "px"; b.style.transition = "height 1.1s cubic-bezier(.22,1,.36,1)"; }, 80);
      });
      e.target.querySelectorAll(".kpi-bar-fill[data-w],.esp-legend-bar-fill[data-w],.ingreso-item-bar[data-w]")
        .forEach((b) => { setTimeout(() => { b.style.width = b.dataset.w + "%"; }, 200); });
      e.target.querySelectorAll("[data-target]").forEach(animateCount);
      obs.unobserve(e.target);
    });
  },
  { threshold: 0.1 }
);
obs.observe(document.getElementById("dashContent"));