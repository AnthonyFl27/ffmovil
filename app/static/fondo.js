// Fondo de los paneles (cliente y admin): un campo de caracteres que se enciende desde abajo,
// en una franja pareja de lado a lado, sobre la aurora de app.css. No reacciona al cursor.
// Unas pocas nubes suaves de luz cruzan el campo de lado a lado, subiendo y bajando un poco;
// donde pasan, los caracteres se encienden y se apagan sin saltos. A veces una nube lanza un
// rayo que baja en zigzag y la ilumina un instante. Un solo <canvas> a ~20 cuadros/s; el
// navegador lo pausa con la pestaña oculta. Con «reducir movimiento» o en pantallas táctiles se
// dibuja una vez, con las nubes pero sin rayos ni movimiento. Sin estilos en línea (la CSP los
// bloquea): la posición del lienzo está en app.css.
(function () {
  "use strict";
  if (!document.querySelector("nav.nav-cliente, nav.nav-admin")) return;

  var CARACTERES = "φψωλπσΣ∫√≈±∞δμθΩαβγΔ∂∇ηξζκρτχ∑∏≠≤≥÷×0123456789//··";
  var CELDA_X = 10;
  var CELDA_Y = 18;
  var INTERVALO = 50; // ms entre cuadros (~20 por segundo)
  var ALFA_MAX = 0.18; // opacidad máxima del campo fuera de las nubes
  var ALFA_NUBE = 0.9; // opacidad que suma el centro de una nube
  var AZUL = [37, 71, 184];
  var CELESTE = [79, 179, 255];
  var LUZ = [214, 240, 255]; // color de las nubes (celeste casi blanco)
  var VELOCIDAD = 1.1; // px por cuadro que avanzan las nubes (~22 px/s)
  var RAYO_CADA = 0.006; // probabilidad por cuadro y nube de lanzar un rayo (~1 cada 8 s)

  var lienzo = document.createElement("canvas");
  lienzo.className = "fondo-ascii";
  lienzo.setAttribute("aria-hidden", "true");
  document.body.prepend(lienzo);
  var ctx = lienzo.getContext("2d");
  var quieto =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    window.matchMedia("(pointer: coarse)").matches;

  var ancho, alto, cols, filas, celdas, nubes;
  var ultimo = 0;

  function azar(texto) {
    return texto.charAt(Math.floor(Math.random() * texto.length));
  }

  function preparar() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    ancho = window.innerWidth;
    alto = window.innerHeight;
    lienzo.width = Math.round(ancho * dpr);
    lienzo.height = Math.round(alto * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = "13px ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace";
    ctx.textBaseline = "top";
    cols = Math.ceil(ancho / CELDA_X);
    filas = Math.ceil(alto / CELDA_Y);
    celdas = [];
    for (var f = 0; f < filas; f++) {
      for (var c = 0; c < cols; c++) {
        var x = c * CELDA_X;
        var y = f * CELDA_Y;
        var rx = x / ancho;
        // Máscara de la franja: nada en la mitad superior y crece hacia abajo, igual de un lado
        // al otro, con un borde que se apaga en las esquinas laterales.
        var v = Math.max(0, (y / alto - 0.4) / 0.6);
        var borde = Math.min(1, 0.55 + 2.2 * Math.min(rx, 1 - rx));
        celdas.push({
          x: x,
          y: y,
          car: azar(CARACTERES),
          base: v * v * borde,
          color: [0, 1, 2].map(function (i) {
            return Math.round(AZUL[i] + (CELESTE[i] - AZUL[i]) * rx);
          }),
          fase: Math.random() * Math.PI * 2,
          grano: 0.88 + Math.random() * 0.24, // irregularidad mínima del borde de la nube
          nube: 0,
        });
      }
    }
    nubes = [];
    var n = Math.max(2, Math.min(4, Math.round(ancho / 560)));
    for (var k = 0; k < n; k++) {
      nubes.push({
        x: ((k + Math.random() * 0.6) / n) * ancho,
        y0: alto * (0.68 + Math.random() * 0.2),
        y: 0,
        rx: Math.min(150 + Math.random() * 90, ancho * 0.3),
        ry: Math.min(44 + Math.random() * 26, alto * 0.08),
        vuelo: Math.random() * Math.PI * 2, // fase del sube y baja
        rayo: [],
        visibles: 0, // cuántos tramos del rayo se ven (baja de a poco)
        brillo: 0, // destello de la nube mientras cae el rayo
      });
    }
  }

  // Cada nube es una mancha de luz con caída suave (campana): en el centro los caracteres se
  // ven casi blancos y hacia el borde vuelven al azul sin corte.
  function nublar(t) {
    var i;
    for (i = 0; i < celdas.length; i++) celdas[i].nube = 0;
    nubes.forEach(function (nube) {
      nube.y = nube.y0 + Math.sin(t * 0.0004 + nube.vuelo) * 22;
      var c0 = Math.max(0, Math.floor((nube.x - nube.rx * 1.3) / CELDA_X));
      var c1 = Math.min(cols - 1, Math.ceil((nube.x + nube.rx * 1.3) / CELDA_X));
      var f0 = Math.max(0, Math.floor((nube.y - nube.ry * 1.3) / CELDA_Y));
      var f1 = Math.min(filas - 1, Math.ceil((nube.y + nube.ry * 1.3) / CELDA_Y));
      var realce = 1 + 0.9 * nube.brillo;
      for (var f = f0; f <= f1; f++) {
        for (var c = c0; c <= c1; c++) {
          var celda = celdas[f * cols + c];
          var dx = (celda.x - nube.x) / nube.rx;
          var dy = (celda.y - nube.y) / nube.ry;
          var d = Math.exp(-(dx * dx + dy * dy) * 2.4) * celda.grano * realce;
          if (d > celda.nube) celda.nube = d;
        }
      }
    });
  }

  // Rayo: un zigzag de «/», «\» y «|» que nace en el centro de la nube y baja un poco más que ella.
  function lanzarRayo(nube) {
    var c = Math.round(nube.x / CELDA_X) + Math.floor((Math.random() - 0.5) * 6);
    var f = Math.round((nube.y - nube.ry * 0.6) / CELDA_Y);
    var fin = Math.round((nube.y + nube.ry * 1.3) / CELDA_Y);
    nube.rayo = [];
    for (; f <= fin; f++) {
      var desvio = Math.floor(Math.random() * 3) - 1;
      if (c >= 0 && c < cols && f >= 0 && f < filas) {
        nube.rayo.push({ celda: celdas[f * cols + c], car: desvio < 0 ? "/" : desvio > 0 ? "\\" : "|" });
      }
      c += desvio;
    }
    nube.visibles = 0;
    nube.brillo = 1;
  }

  function dibujar(t) {
    ctx.clearRect(0, 0, ancho, alto);
    for (var i = 0; i < celdas.length; i++) {
      var celda = celdas[i];
      var n = Math.min(celda.nube, 1);
      var alfa = celda.base * ALFA_MAX * (0.65 + 0.35 * Math.sin(t * 0.0012 + celda.fase)) + n * n * ALFA_NUBE * (0.55 + 0.45 * celda.base);
      if (alfa < 0.012) continue;
      var k = Math.min(1, n * 1.4);
      var r = Math.round(celda.color[0] + (LUZ[0] - celda.color[0]) * k);
      var g = Math.round(celda.color[1] + (LUZ[1] - celda.color[1]) * k);
      var b = Math.round(celda.color[2] + (LUZ[2] - celda.color[2]) * k);
      ctx.fillStyle = "rgba(" + r + "," + g + "," + b + "," + Math.min(alfa, 0.85).toFixed(3) + ")";
      ctx.fillText(celda.car, celda.x, celda.y);
    }
    nubes.forEach(function (nube) {
      if (nube.brillo < 0.04) return;
      ctx.fillStyle = "rgba(255,255,255," + Math.min(nube.brillo * 1.2, 1).toFixed(3) + ")";
      for (var j = 0; j < nube.visibles && j < nube.rayo.length; j++) {
        ctx.fillText(nube.rayo[j].car, nube.rayo[j].celda.x, nube.rayo[j].celda.y);
      }
    });
  }

  function paso(t) {
    window.requestAnimationFrame(paso);
    if (t - ultimo < INTERVALO) return;
    ultimo = t;
    for (var i = 0; i < celdas.length; i++) {
      if (Math.random() < 0.004) celdas[i].car = azar(CARACTERES);
    }
    nubes.forEach(function (nube) {
      nube.x += VELOCIDAD;
      if (nube.x - nube.rx * 1.3 > ancho) nube.x = -nube.rx * 1.3;
      if (nube.visibles < nube.rayo.length) nube.visibles += 2;
      else nube.brillo *= 0.86;
      if (nube.brillo < 0.04 && Math.random() < RAYO_CADA) lanzarRayo(nube);
    });
    nublar(t);
    dibujar(t);
  }

  var espera;
  window.addEventListener("resize", function () {
    window.clearTimeout(espera);
    espera = window.setTimeout(function () {
      preparar();
      if (quieto) {
        nublar(0);
        dibujar(0);
      }
    }, 150);
  });

  preparar();
  if (quieto) {
    nublar(0);
    dibujar(0);
    return;
  }
  window.requestAnimationFrame(paso);
})();
