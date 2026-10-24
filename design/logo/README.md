# Logo de FFMovil — «ff en cursiva con rombo»

Estado: **aprobado por el dueño y aplicado a la web el 2026-10-24**. Ícono a partir del segundo boceto del dueño (propuesta G) y nombre «ffmovil» en trazos. Si se vuelve a cambiar, editar `generar.py`, regenerar y copiar a `app/static/` como se indica en «Aplicarlo en la web».

## Concepto

- Dos F **en cursiva** (inclinación 1:2, unos 27°) que sugieren velocidad: una **trasera** (más oscura) y una **delantera** (más clara), cuya barra cruza el tronco de la trasera. Donde se cruzan, la trasera se recorta con un hueco de 4 unidades, así que la delantera queda por encima.
- A la derecha, un **rombo facetado**: 4 facetas alrededor de una mesa central, con la luz desde arriba a la izquierda. Es el diamante de Free Fire.
- Estilo: formas planas, sin contornos, espacio de 4 unidades entre piezas y extremos de las barras cortados con la misma inclinación que los troncos. Evitar escudos, círculos, brillos tipo «efecto» y degradados pesados.
- Paleta de la web pública: fondo `#0a1128`, superficie `#111c3d`, azul `#2f6bff`, enlace `#8fb0ff` (ver `app/static/inicio.css`).

## Historia y descartes

- Descartados antes: el logo original (escudo + teléfono + dorado), el teléfono con diamante, el monograma en cuadrado, el diamante con rayo, el «avance rápido» sin F y la estrella o destello sobre la gema. No volver a una sola F.
- Primera versión aprobada el 2026-10-24: «FF con gema». Eran dos F rectas lado a lado y una gema tallada como brazo central de la F delantera, en un lienzo de 122 × 100. El mismo día el dueño pidió rediseñarla con bocetos propios.
- Del primer boceto (dos F anidadas y un rombo) salieron las propuestas A–E; del segundo (dos F en cursiva cruzadas y un rombo), las F–I. El dueño eligió la **G**: cursiva con cruce y rombo facetado. El rombo, descartado antes como «gema cuadrada», volvió porque está en los bocetos del dueño.
- Las demás propuestas y la versión «FF con gema» se borraron del generador.

## Geometría (lienzo 108 × 100)

El conjunto ocupa x 4–104, y 10–90, con centro en (54, 50). Los troncos y las barras salen de `_tallo` y `_barra` en `generar.py`: los troncos bajan 1 en x por cada 2 en y, y los extremos de las barras se cortan con esa misma inclinación.

| Pieza | Definición |
| --- | --- |
| F trasera: tronco | `_tallo(44, 10, 90, 13)`: borde izquierdo en x 44 arriba, ancho 13 |
| F trasera: barra | `_barra(34, 104, 10, 12)`: de x 34 a 104 arriba, alto 12 |
| F delantera: tronco | `_tallo(54, 32, 90, 13)` |
| F delantera: barra | `_barra(14, 80, 32, 12)`: cruza el tronco trasero; la trasera se recorta con un trazo de 8 alrededor (hueco de 4) |
| Rombo | centro (77, 67), semidiagonal 19 (x 58–96, y 48–86); mesa central de semidiagonal 8 |
| Letras del nombre | base y = 90, altura x 44 (y = 46), ascendentes hasta y = 10, trazo 12, chaflanes a 45° de 12 por fuera y 5 por dentro, 8 entre letras |
| Punto de la «i» | gema de 16 × 12 (corona y pabellón a 45°, 4 facetas), 4 por encima del trazo |

Todos los trazados y colores están en `generar.py` (única fuente de verdad: editar ahí y regenerar con `python3 design/logo/generar.py`). Los PNG necesitan ImageMagick con librsvg.

### Colores y contraste

| Variante | F trasera | F delantera | Facetas (arriba-izq., arriba-der., abajo-der., abajo-izq., mesa) |
| --- | --- | --- | --- |
| oscuro (fondos `#0a1128` y `#111c3d`) | `#4068da` | `#5a90ff` | `#c4e9ff`, `#7cc4ff`, `#2160dc`, `#3b8ff5`, `#9ddcff` |
| claro (fondo blanco) | `#6a8ce8` | `#1f4fd6` | `#3a98ec`, `#2a85ec`, `#0c3a9e`, `#1a63d8`, `#8fd3ff` |

`generar.py` imprime al final el peor contraste de las F contra los fondos de su variante; el objetivo es ≥ 3:1. Valores actuales: 3,75:1 sobre `#0a1128`, 3,35:1 sobre `#111c3d` y 3,22:1 sobre blanco. La F trasera no puede ser más oscura que ≈ `#3762d4` sin bajar de 3:1 en `#111c3d`.

### Ícono de app y favicon

- Ícono de app: el conjunto centrado a escala 0,84 sobre `#111c3d`, en un cuadrado redondeado (radio 22) con un borde de 1,5 en `#25346b`. El `apple-touch-icon` es el mismo ícono a sangre, porque iOS redondea solo.
- Favicon: el mismo ícono a escala 0,92 y sin borde, porque a 32 px el borde se vuelve un halo. Se lee a 32 px y se reconoce a 16 px, tanto en una pestaña clara como en una oscura.

## Nombre (wordmark)

«ffmovil» en minúsculas, elegido por el dueño (opción B, 2026-10-24). Las letras son trazos propios (`LETRAS` en `generar.py`), sin depender de ninguna fuente, y el punto de la «i» es una gema diminuta. Va siempre junto al ícono y se muestra a 22 px de alto, la altura de un logo de 40 px:

- Cabecera y pie de las páginas públicas (siempre oscuras): `nombre.svg` (blanco); estilo en `.marca .marca-nombre` de `inicio.css`.
- Cabecera de la app (`base.html`, cliente y admin): también `nombre.svg`, porque la app usa siempre el tema oscuro (`data-theme="dark"`); el estilo está en `nav a.marca img.marca-nombre` de `app.css`. `ffmovil-nombre-claro.svg` queda en `design/` para fondos claros fuera de la web.

Los títulos y textos siguen escribiendo «FFMovil» (parte pública) o «FFmovil» (app). El título de la portada es solo «FFMovil» (decisión del dueño: los títulos largos se cortan en la pestaña).

## Archivos

| Archivo | Uso |
| --- | --- |
| `svg/ffmovil-icono.svg`, `…-claro.svg` | Ícono con fondo transparente para fondos oscuros o claros |
| `svg/ffmovil-app.svg` | Ícono en cuadrado redondeado (para `logo.png`) |
| `svg/ffmovil-app-cuadrado.svg` | Cuadrado a sangre para `apple-touch-icon.png` |
| `svg/ffmovil-favicon.svg` | Favicon (ícono más grande, sin borde) |
| `svg/ffmovil-nombre.svg`, `…-claro.svg` | Nombre «ffmovil» recortado a las letras (268 × 80) |
| `png/logo-192.png`, `png/favicon-32.png`, `png/apple-touch-icon-180.png` | Los PNG que se copian a `app/static/` |
| `png/ffmovil-icono-512.png`, `…-claro-512.png`, `ffmovil-app-512.png`, `ffmovil-nombre-240.png`, `…-claro-240.png` | Versiones grandes (redes, documentos) |

## Aplicarlo en la web

Copiar estos archivos a `app/static/` (hecho por última vez el 2026-10-24):

| Origen | Destino |
| --- | --- |
| `png/logo-192.png` | `logo.png` |
| `png/favicon-32.png` | `favicon.png` |
| `png/apple-touch-icon-180.png` | `apple-touch-icon.png` |
| `svg/ffmovil-nombre.svg` | `nombre.svg` |

Es un cambio menor, sin tocar `sdd/`. Las plantillas añaden `?v=<hash>`, pero `estatico()` lo calcula al arrancar: hay que reiniciar la app, o tocar un `.py` si corre con `--reload` (ver `AGENTS.md`). Las plantillas muestran el logo en `<img width="40" height="40">` (cabeceras y pie) y a 112 × 112 en el inicio de sesión. El repositorio es público: estos archivos no contienen datos sensibles.
