// Fondos decorativos de la portada (RF-58, RNF-20; plan sec. 6.3, CHG-035): el campo de
// caracteres de la tarjeta principal y el diamante de puntos. Se cargan con `defer` solo en `/`
// y dibujan en <canvas aria-hidden="true">: sin JavaScript no se ven y no falta contenido.
// Se pausan al salir de la pantalla y, con `prefers-reduced-motion`, se dibujan una sola vez.
(function () {
  "use strict";

  var reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Tope de puntos del diamante (RNF-20): la mitad en pantallas angostas, donde el diamante es pequeño.
  var MAX_PUNTOS = 10000;

  // Mide el lienzo (con la densidad de píxeles, máximo 2), lo redibuja al cambiar el tamaño y
  // anima con requestAnimationFrame mientras esté en pantalla.
  function ejecutar(lienzo, medir, dibujar) {
    var visible = true;
    function ajustar() {
      var densidad = Math.min(window.devicePixelRatio || 1, 2);
      var caja = lienzo.getBoundingClientRect();
      lienzo.width = Math.round(caja.width * densidad);
      lienzo.height = Math.round(caja.height * densidad);
      var ctx = lienzo.getContext("2d");
      ctx.setTransform(densidad, 0, 0, densidad, 0, 0);
      medir(ctx, caja.width, caja.height);
      if (reducido) dibujar(0);
    }
    ajustar();
    window.addEventListener("resize", ajustar);
    if (reducido) return;
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entradas) {
        visible = entradas[0].isIntersecting;
      }).observe(lienzo);
    }
    (function bucle(ms) {
      if (visible) dibujar(ms);
      window.requestAnimationFrame(bucle);
    })(0);
  }

  // --- Campo de caracteres de la tarjeta principal -------------------------------------------

  function campoDeCaracteres(lienzo) {
    var glifos = "·∙+:01<>/".split("");
    var paso = 20;
    var ctx, ancho, alto, celdas;

    function medir(contexto, w, h) {
      ctx = contexto;
      ancho = w;
      alto = h;
      celdas = [];
      var columnas = Math.ceil(w / paso);
      var filas = Math.ceil(h / paso);
      for (var y = 0; y < filas; y++) {
        for (var x = 0; x < columnas; x++) {
          // Número pseudoaleatorio estable por celda: el campo no cambia al redimensionar.
          var a = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
          a -= Math.floor(a);
          // Más denso hacia los bordes y abajo; el centro (el texto) queda despejado.
          var borde = Math.max(Math.abs((x * paso) / w - 0.5) * 2, (y * paso) / h);
          var presencia = Math.pow(borde, 1.8);
          if (a < 0.1 + presencia * 0.6) {
            celdas.push({
              x: x * paso + paso / 2,
              y: y * paso + paso / 2,
              glifo: glifos[Math.floor(a * 97) % glifos.length],
              alfa: 0.05 + 0.16 * presencia,
              fase: a * 6.28,
              velocidad: 0.5 + a,
            });
          }
        }
      }
    }

    function dibujar(ms) {
      ctx.clearRect(0, 0, ancho, alto);
      ctx.font = "14px ui-monospace, Menlo, Consolas, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      var t = ms / 1000;
      for (var i = 0; i < celdas.length; i++) {
        var c = celdas[i];
        var parpadeo = reducido ? 1 : 0.55 + 0.45 * Math.sin(t * c.velocidad + c.fase);
        ctx.fillStyle = "rgba(255,255,255," + c.alfa * parpadeo + ")";
        ctx.fillText(c.glifo, c.x, c.y);
      }
    }

    ejecutar(lienzo, medir, dibujar);
  }

  // --- Diamante de puntos ----------------------------------------------------------------------

  function generador(semilla) {
    return function () {
      semilla |= 0;
      semilla = (semilla + 0x6d2b79f5) | 0;
      var t = Math.imul(semilla ^ (semilla >>> 15), 1 | semilla);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function restar(a, b) {
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  }

  function cruz(a, b) {
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  }

  function normalizar(v) {
    var l = Math.hypot(v[0], v[1], v[2]) || 1;
    return [v[0] / l, v[1] / l, v[2] / l];
  }

  // Talla brillante: mesa octogonal, corona (estrellas y cometas), cintura de 16 vértices y pabellón.
  function construirDiamante(calidad) {
    var aleatorio = generador(11);
    var mesa = [];
    var cintura = [];
    var punta = [0, -1.15, 0];
    var i;
    for (i = 0; i < 8; i++) {
      var a = (i * Math.PI) / 4;
      mesa.push([0.56 * Math.cos(a), 0.62, 0.56 * Math.sin(a)]);
    }
    for (i = 0; i < 16; i++) {
      var b = (i * Math.PI) / 8;
      cintura.push([Math.cos(b), 0.22, Math.sin(b)]);
    }
    var triangulos = [];
    var centro = [0, 0.62, 0];
    for (i = 0; i < 8; i++) triangulos.push([centro, mesa[i], mesa[(i + 1) % 8]]);
    for (i = 0; i < 8; i++) {
      var t0 = mesa[i];
      var t1 = mesa[(i + 1) % 8];
      triangulos.push(
        [t0, t1, cintura[(2 * i + 1) % 16]],
        [t0, cintura[(2 * i + 15) % 16], cintura[(2 * i) % 16]],
        [t0, cintura[(2 * i) % 16], cintura[(2 * i + 1) % 16]],
        [t1, cintura[(2 * i + 1) % 16], cintura[(2 * i + 2) % 16]]
      );
    }
    for (i = 0; i < 16; i++) triangulos.push([punta, cintura[i], cintura[(i + 1) % 16]]);

    var caras = [];
    var puntos = [];
    triangulos.forEach(function (t, k) {
      var c = cruz(restar(t[1], t[0]), restar(t[2], t[0]));
      var area = Math.hypot(c[0], c[1], c[2]) / 2;
      var normal = normalizar(c);
      var cen = [
        (t[0][0] + t[1][0] + t[2][0]) / 3,
        (t[0][1] + t[1][1] + t[2][1]) / 3 - 0.1,
        (t[0][2] + t[1][2] + t[2][2]) / 3,
      ];
      // La normal apunta hacia afuera del diamante.
      if (normal[0] * cen[0] + normal[1] * cen[1] + normal[2] * cen[2] < 0) {
        normal = [-normal[0], -normal[1], -normal[2]];
      }
      caras.push({ normal: normal, tono: (k * 47) % 40 });
      var cantidad = Math.round(area * 620 * calidad);
      for (var j = 0; j < cantidad; j++) {
        var u = aleatorio();
        var v = aleatorio();
        if (u + v > 1) {
          u = 1 - u;
          v = 1 - v;
        }
        puntos.push({
          x: t[0][0] + u * (t[1][0] - t[0][0]) + v * (t[2][0] - t[0][0]),
          y: t[0][1] + u * (t[1][1] - t[0][1]) + v * (t[2][1] - t[0][1]),
          z: t[0][2] + u * (t[1][2] - t[0][2]) + v * (t[2][2] - t[0][2]),
          cara: k,
          arista: 0,
        });
      }
      // Las aristas llevan puntos más brillantes: marcan el corte de las facetas.
      for (var e = 0; e < 3; e++) {
        var p = t[e];
        var q = t[(e + 1) % 3];
        var largo = Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]);
        var muestras = Math.max(2, Math.round(largo * 26 * calidad));
        for (var s = 0; s < muestras; s++) {
          var w = s / muestras;
          puntos.push({
            x: p[0] + (q[0] - p[0]) * w,
            y: p[1] + (q[1] - p[1]) * w,
            z: p[2] + (q[2] - p[2]) * w,
            cara: k,
            arista: 1,
          });
        }
      }
    });
    return {
      puntos: puntos,
      caras: caras,
      destellos: [mesa[0], mesa[3], mesa[5], cintura[2], cintura[7], cintura[12], centro],
    };
  }

  function girar(x, y, z, cosY, senY, cosT, senT) {
    var x1 = x * cosY + z * senY;
    var z1 = -x * senY + z * cosY;
    return [x1, y * cosT - z1 * senT, y * senT + z1 * cosT];
  }

  // Destello en forma de estrella de cuatro puntas.
  function destello(ctx, x, y, r, alfa) {
    ctx.save();
    ctx.globalAlpha = alfa;
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.moveTo(x, y - r);
    ctx.quadraticCurveTo(x, y, x + r * 0.28, y);
    ctx.quadraticCurveTo(x, y, x, y + r);
    ctx.quadraticCurveTo(x, y, x - r * 0.28, y);
    ctx.quadraticCurveTo(x, y, x, y - r);
    ctx.moveTo(x - r * 0.7, y);
    ctx.quadraticCurveTo(x, y, x, y - r * 0.22);
    ctx.quadraticCurveTo(x, y, x + r * 0.7, y);
    ctx.quadraticCurveTo(x, y, x, y + r * 0.22);
    ctx.quadraticCurveTo(x, y, x - r * 0.7, y);
    ctx.fill();
    ctx.restore();
  }

  function diamanteDePuntos(lienzo) {
    var modelo = construirDiamante(window.innerWidth < 768 ? 0.5 : 1);
    var luz = normalizar([-0.45, 0.8, 0.55]);
    var media = normalizar([luz[0], luz[1], luz[2] + 1]);
    var insignias = ["◆", "✓", "↗"];
    var inclinacion = 0.38;
    var cosT = Math.cos(inclinacion);
    var senT = Math.sin(inclinacion);
    var ctx, ancho, alto;
    lienzo.dataset.puntos = String(modelo.puntos.length);

    function medir(contexto, w, h) {
      ctx = contexto;
      ancho = w;
      alto = h;
    }

    function dibujar(ms) {
      if (!ancho || !alto) return;
      var giro = reducido ? 0.7 : (ms / 1000) * 0.42;
      var cosY = Math.cos(giro);
      var senY = Math.sin(giro);
      var escala = Math.min(ancho * 0.29, alto * 0.4);
      var ox = ancho / 2;
      var oy = alto * 0.46;
      var foco = 4;
      ctx.clearRect(0, 0, ancho, alto);

      var halo = ctx.createRadialGradient(ox, oy, escala * 0.1, ox, oy, Math.min(escala * 2.6, alto * 0.5));
      halo.addColorStop(0, "rgba(47,107,255,.22)");
      halo.addColorStop(0.5, "rgba(47,107,255,.06)");
      halo.addColorStop(1, "rgba(47,107,255,0)");
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, ancho, alto);

      // Brillo de cada cara: luz difusa más un reflejo especular que cruza las facetas al girar.
      var brillos = modelo.caras.map(function (cara) {
        var r = girar(cara.normal[0], cara.normal[1], cara.normal[2], cosY, senY, cosT, senT);
        var difusa = Math.max(0, r[0] * luz[0] + r[1] * luz[1] + r[2] * luz[2]);
        var especular = Math.max(0, r[0] * media[0] + r[1] * media[1] + r[2] * media[2]);
        return { z: r[2], brillo: 0.2 + 0.5 * difusa + Math.pow(especular, 16) * 1.2, tono: cara.tono };
      });
      var lista = modelo.puntos.map(function (p) {
        return { r: girar(p.x, p.y, p.z, cosY, senY, cosT, senT), cara: brillos[p.cara], arista: p.arista };
      });
      lista.sort(function (a, b) {
        return a.r[2] - b.r[2];
      });
      var grande = ancho > 600;
      for (var k = 0; k < lista.length; k++) {
        var it = lista[k];
        var perspectiva = foco / (foco - it.r[2] * 0.9);
        var x = ox + it.r[0] * escala * perspectiva;
        var y = oy - it.r[1] * escala * perspectiva;
        var frente = it.cara.z > 0;
        var brillo = Math.min(1.2, it.cara.brillo);
        var alfa = frente ? 0.4 + 0.6 * Math.min(1, brillo) : 0.14;
        if (it.arista) alfa = Math.min(1, alfa + 0.3);
        var luminosidad = frente ? (brillo > 1 ? 88 : 36 + brillo * 50) : 28;
        var saturacion = frente ? 88 - Math.max(0, brillo - 0.7) * 120 : 70;
        var tono = 212 + (frente ? it.cara.tono * (0.4 + brillo * 0.4) : 0);
        ctx.fillStyle =
          "hsla(" + tono + "," + saturacion + "%," + (it.arista ? Math.min(94, luminosidad + 14) : luminosidad) + "%," + alfa + ")";
        var d = (frente ? (it.arista ? 2.2 : 1.6) : 1.1) * perspectiva * (grande ? 1.15 : 0.9);
        ctx.fillRect(x - d / 2, y - d / 2, d, d);
      }

      modelo.destellos.forEach(function (v, i) {
        var q = girar(v[0], v[1], v[2], cosY, senY, cosT, senT);
        if (q[2] < 0.1) return;
        var fase = reducido ? (i % 2 ? 0.9 : -1) : Math.sin((ms / 1000) * 1.6 + i * 1.9);
        if (fase < 0.55) return;
        var perspectiva = foco / (foco - q[2] * 0.9);
        destello(ctx, ox + q[0] * escala * perspectiva, oy - q[1] * escala * perspectiva, escala * 0.2 * ((fase - 0.55) / 0.45), 0.95);
      });

      // Insignias en órbita, unidas al diamante por arcos punteados.
      var rx = Math.min(escala * 2.1, ancho / 2 - escala * 0.35);
      var ry = escala * 0.62;
      for (var n = 0; n < 3; n++) {
        var orbita = (reducido ? 0 : (ms / 1000) * 0.32) + n * 2.094 + 0.4;
        var profundidad = Math.sin(orbita);
        var bx = ox + Math.cos(orbita) * rx;
        var by = oy - escala * 0.2 + Math.sin(orbita) * ry;
        var radio = escala * 0.19 * (0.85 + 0.2 * profundidad);
        var cercania = (profundidad + 1) / 2;
        ctx.globalAlpha = 0.25 + 0.35 * cercania;
        ctx.strokeStyle = "#8fb0ff";
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 5]);
        ctx.beginPath();
        ctx.moveTo(bx, by);
        ctx.quadraticCurveTo((bx + ox) / 2, Math.min(by, oy) - escala * 0.7, ox, oy - escala * 0.2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 0.6 + 0.4 * cercania;
        ctx.beginPath();
        ctx.arc(bx, by, radio, 0, 7);
        ctx.fillStyle = "rgba(47,107,255,.95)";
        ctx.fill();
        ctx.strokeStyle = "rgba(143,176,255,.65)";
        ctx.beginPath();
        ctx.arc(bx, by, radio + 5, 0, 7);
        ctx.stroke();
        ctx.fillStyle = "#fff";
        ctx.font = "600 " + Math.round(radio * 1.1) + "px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(insignias[n], bx, by + 1);
        ctx.globalAlpha = 1;
      }
    }

    ejecutar(lienzo, medir, dibujar);
  }

  var fondo = document.getElementById("fondo-ascii");
  var diamante = document.getElementById("diamante");
  if (fondo) campoDeCaracteres(fondo);
  if (diamante) diamanteDePuntos(diamante);
})();
