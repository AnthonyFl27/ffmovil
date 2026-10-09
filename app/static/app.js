// Fechas en la zona del navegador (RNF-09) y desfase para los filtros de fecha.
function prepararFragmento(raiz) {
  raiz.querySelectorAll("time[data-local]").forEach(function (t) {
    var d = new Date(t.getAttribute("datetime"));
    if (!isNaN(d)) {
      t.textContent = d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
    }
    t.removeAttribute("data-local");
  });
  raiz.querySelectorAll("input[name=tz]").forEach(function (i) {
    i.value = String(new Date().getTimezoneOffset());
  });
}

// Los scripts con defer corren antes de DOMContentLoaded: el primer htmx:load ya llega aquí.
htmx.onLoad(prepararFragmento);

document.addEventListener("DOMContentLoaded", function () {
  // Los filtros se pliegan en móvil y se muestran abiertos en escritorio (RNF-12).
  if (window.matchMedia("(min-width: 768px)").matches) {
    document.querySelectorAll("details.filtros").forEach(function (d) {
      d.open = true;
    });
  }

  // Un formulario con data-limpia="#id" vacía ese elemento al cambiar sus datos.
  document.addEventListener("input", function (e) {
    var form = e.target.closest("[data-limpia]");
    if (form) {
      var destino = document.querySelector(form.dataset.limpia);
      if (destino) destino.innerHTML = "";
    }
  });

  // Con la recarga creada (llega el fragmento del pedido) se ocultan el saldo y el
  // formulario y queda solo el pedido; ante un error se conservan para corregirlo.
  document.body.addEventListener("htmx:afterSwap", function (e) {
    var datos = document.getElementById("datos-recarga");
    var pedido = e.detail.target.id === "confirmacion" && e.detail.target.querySelector("article[id^=pedido-]");
    if (datos && pedido) {
      datos.hidden = true;
      pedido.scrollIntoView({ block: "start" });
    }
  });

  function avisar(texto) {
    var aviso = document.getElementById("aviso-global");
    if (aviso) aviso.innerHTML = '<p class="mensaje error"></p>';
    if (aviso) aviso.firstChild.textContent = texto;
  }
  document.body.addEventListener("htmx:responseError", function () {
    avisar("Ocurrió un error en el servidor. Intenta de nuevo.");
  });
  document.body.addEventListener("htmx:sendError", function () {
    avisar("No hay conexión con el servidor. Revisa tu red e intenta de nuevo.");
  });
});
