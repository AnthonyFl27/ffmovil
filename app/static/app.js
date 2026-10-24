// Fechas en la zona del navegador (RNF-09) y desfase para los filtros de fecha.
function prepararFragmento(raiz) {
  raiz.querySelectorAll("time[data-local]").forEach(function (t) {
    var d = new Date(t.getAttribute("datetime"));
    if (!isNaN(d)) {
      // Mes con nombre (sin ambigüedad día/mes); el año solo si no es el actual.
      var formato = { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" };
      if (d.getFullYear() !== new Date().getFullYear()) formato.year = "numeric";
      t.textContent = d.toLocaleString(undefined, formato);
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
  // Menú en línea: un indicador azul se desliza hasta la opción bajo el cursor o el foco
  // y vuelve a la página actual al salir; sobre «Recargar» se vuelve naranja (estilos en app.css).
  // Las medidas van en variables CSS por CSSOM, que la CSP permite (no hay estilos en línea).
  document.querySelectorAll("nav ul.menu-linea").forEach(function (menu) {
    var indicador = document.createElement("li");
    indicador.className = "indicador quieto";
    indicador.setAttribute("aria-hidden", "true");
    menu.prepend(indicador);
    menu.classList.add("con-indicador");
    var actual = menu.querySelector("a[aria-current=page]");
    var encendido = null;
    function mover(enlace) {
      if (encendido) encendido.classList.remove("encendido");
      encendido = enlace;
      if (!enlace || !enlace.offsetWidth) {
        indicador.classList.remove("visible");
        return;
      }
      var m = menu.getBoundingClientRect();
      var r = enlace.getBoundingClientRect();
      indicador.style.setProperty("--x", r.left - m.left + "px");
      indicador.style.setProperty("--y", r.top - m.top + "px");
      indicador.style.setProperty("--w", r.width + "px");
      indicador.style.setProperty("--h", r.height + "px");
      indicador.classList.toggle("naranja", enlace.getAttribute("href") === "/recargar");
      indicador.classList.add("visible");
      enlace.classList.add("encendido");
    }
    function enlaceDe(e) {
      return e.target.closest ? e.target.closest("a") : null;
    }
    menu.addEventListener("mouseover", function (e) {
      if (enlaceDe(e)) mover(enlaceDe(e));
    });
    menu.addEventListener("focusin", function (e) {
      if (enlaceDe(e)) mover(enlaceDe(e));
    });
    menu.addEventListener("mouseleave", function () {
      mover(actual);
    });
    menu.addEventListener("focusout", function (e) {
      if (!menu.contains(e.relatedTarget)) mover(actual);
    });
    window.addEventListener("resize", function () {
      indicador.classList.add("quieto");
      mover(encendido || actual);
      requestAnimationFrame(function () {
        indicador.classList.remove("quieto");
      });
    });
    // La primera vez aparece sin deslizarse desde la izquierda.
    mover(actual);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        indicador.classList.remove("quieto");
      });
    });
  });

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
