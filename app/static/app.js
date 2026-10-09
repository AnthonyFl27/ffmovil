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

  // Copiar un dato (botón .copiar) y mostrar/ocultar la contraseña (botón .ver-clave).
  function copiarTexto(texto) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texto);
    return new Promise(function (ok, fallo) {
      var t = document.createElement("textarea");
      t.value = texto;
      t.setAttribute("readonly", "");
      t.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(t);
      t.select();
      try {
        if (document.execCommand("copy")) ok();
        else fallo();
      } catch (e) {
        fallo(e);
      } finally {
        document.body.removeChild(t);
      }
    });
  }
  document.addEventListener("click", function (e) {
    var copiar = e.target.closest("button.copiar");
    if (copiar) {
      copiarTexto(copiar.dataset.copiar).then(function () {
        copiar.classList.add("listo");
        setTimeout(function () {
          copiar.classList.remove("listo");
        }, 1500);
      });
      return;
    }
    var ver = e.target.closest("button.ver-clave");
    if (ver) {
      var campo = ver.parentElement.querySelector("input");
      var visible = campo.type === "password";
      campo.type = visible ? "text" : "password";
      ver.classList.toggle("visible", visible);
      ver.setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
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
