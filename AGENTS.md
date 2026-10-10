# AGENTS.md — Contexto y reglas para el LLM

## Proyecto

Web de recargas de diamantes de Free Fire con cuentas prepago. Backend FastAPI en Docker; PostgreSQL externo (servidor propio en el VPS) accedido solo por `DATABASE_URL`. API y web en el mismo repositorio. Sin dominio por ahora: la app corre por HTTP y Caddy queda diferido. Consume la API de VentasFF (`https://ventasff.com/api/reseller`). Repositorio público: nunca incluir secretos, precios de costo reales, datos ni respaldos.

## Documentos (orden de autoridad)

1. `sdd/spec.md` — **qué** y **por qué**. Fuente de verdad.
2. `sdd/plan.md` — **cómo** (arquitectura, datos, flujos).
3. `sdd/tasks.md` — **pasos** de implementación.
4. `sdd/changelog.md` — historial de cambios de la spec.

Si hay conflicto: spec > plan > tasks > código.

El avance real está en `sdd/tasks.md` (`[x]` hechas); revisarlo al empezar cada sesión.

## Pedidos del usuario: significativos vs. menores

Antes de actuar, clasificar cada pedido:

- **Significativo** → se define y edita en `sdd/` **antes** del código. Es significativo si cambia o añade:
  - comportamiento visible o reglas de negocio (flujos, estados, saldos, precios, permisos, validaciones, mensajes con efecto funcional);
  - alcance (juegos, pantallas o endpoints nuevos);
  - modelo de datos (tablas, columnas, restricciones);
  - integración con VentasFF, seguridad, despliegue o infraestructura (red, Docker, BD).

  Proceso: seguir "Cómo evoluciona el SDD". La petición del usuario cuenta como aprobación del objetivo; si el texto exacto de la spec implica decisiones que el usuario no tomó, confirmarlas antes de aplicar.
- **Menor** → se hace directamente, **sin** tocar `sdd/`. Ejemplos: colores, estilos, espaciado, íconos, textos o erratas sin efecto funcional, renombres internos, refactor sin cambio de comportamiento, comentarios, ajustes de lint/formato.
- **Decisión técnica sin efecto en la spec** (librería, versión, estructura interna, red entre contenedores): se anota en `plan.md` (y en `tasks.md` si cambia el criterio de una tarea), sin `CHG` ni subir versión de la spec.
- En caso de duda, tratarlo como significativo y preguntar.

## Flujo de trabajo

1. Leer `spec.md`, `plan.md` y la tarea asignada en `tasks.md` antes de escribir código.
2. Trabajar **una tarea a la vez**, en orden de fase salvo indicación contraria.
3. Escribir pruebas junto con el código; la tarea no está hecha sin su criterio de hecho cumplido.
4. Al terminar: marcar `[x]` en `tasks.md` y citar en el commit el ID de tarea y los requisitos (ej. `T-046 RF-24 RN-02`).

## Cómo evoluciona el SDD (regla principal)

El código nunca introduce comportamiento que no esté en la spec. Si durante la implementación aparece algo nuevo (caso no cubierto, comportamiento real de la API distinto al documentado, contradicción, decisión necesaria), el LLM **detiene esa parte** y sigue este proceso:

1. **Detectar y nombrar:** describir el hallazgo en una frase y clasificarlo:
   - *Vacío:* la spec no dice nada.
   - *Contradicción:* spec, plan o tareas se oponen.
   - *Hecho nuevo:* la realidad (API, BD, entorno) difiere de lo asumido.
   - *Pregunta abierta resuelta:* se decide una `Q-XX`.
2. **Proponer, no aplicar:** presentar al usuario el cambio propuesto en `spec.md` (texto exacto, con ID nuevo o modificado) y su impacto en `plan.md` y `tasks.md`.
3. **Esperar aprobación** del usuario. Sin aprobación, no se modifica la spec ni se implementa el comportamiento.
4. **Aplicar en este orden:** `spec.md` → `plan.md` → `tasks.md` → código y pruebas.
5. **Registrar** una entrada `CHG-XXX` en `sdd/changelog.md` y subir la versión de la spec según las reglas de versionado.
6. Si el cambio genera tareas nuevas, añadirlas en "Tareas emergentes" con ID `T-1xx` e indicar el `CHG` de origen.

### Reglas de edición

- IDs (`RF-`, `RN-`, `RNF-`, `CA-`, `Q-`, `T-`, `CHG-`) son permanentes; nunca se reutilizan ni renumeran. Un requisito eliminado se marca `(retirado, CHG-XXX)`.
- Un requisito nuevo debe ser verificable (criterio claro) y tener al menos una tarea.
- Las preguntas abiertas (`Q-XX`) se cierran moviéndolas a "Decisiones resueltas" del changelog y reflejando el resultado en la spec.
- Cambios de redacción sin efecto en el comportamiento: versión *patch*, sin necesidad de aprobación previa.
- Los hallazgos sobre la API de VentasFF se documentan en la sección 9 de la spec.

## Reglas técnicas invariables

- La API Key de VentasFF solo se lee del entorno en el backend; nunca en frontend, logs, respuestas ni commits.
- Los montos son `Decimal`/`NUMERIC`; nunca `float`.
- Todo cambio de saldo pasa por el servicio `ledger`, dentro de transacción con `SELECT … FOR UPDATE`, y genera un movimiento.
- Solo `ventasff_client.py` llama a VentasFF.
- La base de datos es externa: no se agrega servicio `db` al Compose ni se asume que corre localmente.
- Los esquemas de respuesta del cliente no contienen `precio_costo`.
- Un pedido `PENDIENTE_VERIFICAR` nunca se reintenta automáticamente.
- Las pruebas usan el simulador `tests/fake_ventasff.py`; no se llama a la API real salvo en la tarea T-093.

## Base de datos

- El LLM solo necesita `DATABASE_URL` (y `TEST_DATABASE_URL`), que el usuario provee en el `.env` local.
- Nunca imprimir, registrar ni commitear credenciales.
- Todo cambio de esquema se hace con migraciones de Alembic; no ejecutar DDL manual.
- Las pruebas corren solo en el esquema `test`. Ninguna prueba ni script toca otros esquemas.
- Operaciones destructivas (`DROP`, `TRUNCATE`, `DELETE` masivo) fuera del esquema `test` requieren confirmación del usuario.
- Producción usará otra base en el mismo VPS: el cambio es solo el valor de `DATABASE_URL`.

## Entorno de desarrollo

- **Stack fijado:** Python 3.12 (uv), FastAPI, SQLAlchemy 2 async + psycopg 3, Alembic, PostgreSQL 18, pytest + pytest-asyncio (`asyncio_mode = "auto"`), ruff fijado como dependencia de desarrollo.
- **VPS:** acceso con `ssh ffmovil`. PostgreSQL corre en el contenedor `postgresql` (imagen `postgres:18`), con su propio Compose fuera de este repo (`/root/container/postgresql_testing/`). Publica el puerto solo en `127.0.0.1:5432` y está unido a la red Docker externa `ffmovil_net`.
- **App ↔ BD en el VPS:** `app` se une a `ffmovil_net` y usa como host `postgresql:5432`.
- **BD desde el equipo local:** túnel SSH `ssh -f -N -o ExitOnForwardFailure=yes -L 5433:localhost:5432 ffmovil` (comprobar con `ss -ltn | grep 5433`); el `.env` local apunta a `localhost:5433`. Sin túnel fallan Alembic, la app y las pruebas de BD. El túnel se abre al iniciar la sesión y se cierra al terminar.
- **Cambios en el VPS:** solo con pedido explícito del usuario; nunca exponer puertos de PostgreSQL a internet.
- **`.env` local:** lo crea el LLM o el usuario a partir de `.env.example`; permisos `600`; nunca mostrar su contenido.

### Comandos

```bash
uv run pytest                      # pruebas (requiere túnel para las de BD)
uv run playwright install chromium # una vez: navegador de la prueba móvil (CA-07); sin él se omite
uv run ruff check . && uv run ruff format --check .
uv run alembic upgrade head        # migra la BD de DATABASE_URL
uv run alembic revision -m "..."   # nueva migración (luego editarla a mano)
uv run uvicorn app.main:app --reload
```

**Probar la web en local sin la API real** (el usuario abre `http://127.0.0.1:8000`):

```bash
uv run python -m tests.fake_ventasff --port 8099          # simulador (crédito ficticio 100.00)
VENTASFF_URL=http://127.0.0.1:8099/api/reseller VENTASFF_API_KEY=rv_c_simulador \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

Con `--reload` la app se reinicia sola al cambiar el código; al terminar, cerrar la app y el simulador.

**Regla: túnel de Cloudflare.** Cuando el usuario pida arrancar la app, el LLM la levanta y **siempre le pregunta** si quiere abrir el túnel de Cloudflare (`cloudflared tunnel --url http://localhost:8000`, en segundo plano). Sin respuesta afirmativa no se abre. Si se abre, dar la URL temporal (cambia en cada arranque), avisar de que queda pública con las cuentas de la BD de desarrollo y, al terminar la sesión, cerrar el túnel junto con la app y el simulador.

Las variables de entorno tienen prioridad sobre el `.env`: así la app nunca llama a VentasFF real. La BD de desarrollo ya tiene el admin `admin` (creado por CLI) y un cliente de prueba; el catálogo se llena con "Sincronizar ahora" desde `/gestion/paquetes` (3 paquetes ficticios del simulador, inactivos y sin precio).

### Piezas ya construidas (fases 1 a 8 parcial, móvil, recarga en tres pasos y endurecimiento; spec v0.16.0)

Detalle de diseño en `sdd/plan.md` (sec. 3 modelo, 4.2 fases A/B/C, 4.2.1 alertas, 4.5 cliente VentasFF, 4.6 transacciones y rutas de recarga, 6 endpoints, 7 seguridad). Migración head: `ea509abd049b` (`sesiones`, aplicada en desarrollo).

- **Arranque** (`app/main.py`, `lifespan`): `configurar_logs` → verificar BD → `recuperar_pedidos_huerfanos` (RN-09) → `app.state`: `sesiones`, `cookie_secure`, `limitador_login`, `ventasff` (cliente único con límite general 50/min), `limitador_recargas` (8/min), `tareas_recarga`, `crear_cliente_ventasff` → programador APScheduler (sincronización diaria 08:00 UTC). Al apagar espera las recargas en curso (100 s) y cierra el cliente.
- `app/config.py` (`SecretStr`; `VENTASFF_URL` opcional para apuntar al simulador), `app/db.py`, `app/logs.py` (enmascara API Key, `SECRET_KEY`, clave de BD y `Bearer …`), `app/cli.py` (`python -m app.cli crear-admin <usuario>`).
- **Modelos** (`app/models/`): `Usuario`, `Auditoria`, `Saldo`, `Movimiento` (triggers impiden UPDATE/DELETE/TRUNCATE), `Paquete`, `Config` (`alerta_credito_min` = 10.00), `Pedido`, `PedidoEvento`, `Alerta`, `Sesion` (solo SHA-256 del token). `Base` mapea `Decimal` → `NUMERIC(12,2)` y `datetime` → `TIMESTAMPTZ`.
- **Servicios** (`app/services/`):
  - `montos.normalizar_monto` (Decimal, 2 decimales, > 0); `ledger` (`abrir_cuenta`, `abonar`, `ajustar`, `reservar`, `liberar`, `cargar`; `monto` positivo salvo `ajuste`).
  - `auth_service` (argon2id, `crear_usuario` → `(usuario, clave_temporal)`; clientes reciben saldo en cero; `normalizar_nombre_usuario` RF-07, `validar_clave_nueva` RF-08, `autenticar`); `sesiones` (crear, obtener con expiración de 8 h, cerrar, cerrar todas); `limitador_login` (RF-05, en memoria); `auditoria.registrar` (RF-55).
  - `ventasff_client` (`ClienteVentasFF` con `limitador` opcional, `clasificar`, `ErrorAPI`/`ErrorPrevioAlEnvio`/`ResultadoIncierto`, pausa por `Retry-After`); `limitador.LimitadorTasa`.
  - `catalogo` (`fijar_precio_venta` con aviso bajo costo, `activar`, `desactivar`, `sincronizar_catalogo`); `tareas` (job diario y "sincronizar ahora").
  - `estados` (máquina de estados), `codigos` (`FF-000123`), `recarga_service` (`validar_jugador`, `crear_pedido` = Fase A, `llamar_proveedor` = Fase B, `resolver_pedido` = Fase C, `procesar_pedido` = B+C+alertas, `resolver_pendiente` = admin), `recuperacion`, `alertas`, `consultas_pedidos` (filtros y paginación comunes).
- **Rutas** (`app/routers/`): `dependencias.py` (`Bd`, `EnSesion`, `Actual`, `Cliente`, `Admin`; CSRF por cabecera `X-CSRF-Token` en métodos no seguros), `auth` (login, logout, sesión, cambiar-clave), `me` (resumen, fondos, pedidos), `paquetes`, `recargas` (validar y crear; B+C en tarea propia), `admin/` (usuarios, saldos, pedidos + resolver, panel + alertas + config, paquetes + sincronizar, auditoría; `require_admin` a nivel de router).
- **Web** (`app/web/`, plan sec. 6.1; Q-05 → Jinja2 + HTMX 2 + Pico.css 2, ambos en `app/static`): las rutas HTML llaman a las funciones de las rutas JSON y renderizan sus esquemas (el cliente nunca recibe uno con costo). `plantillas.py` (filtros `usd`, `fecha` → `<time>` que `app.js` pasa a la zona del navegador, `texto`; `render`, `error(..., destino)` con `HX-Retarget`; `Redirigir`/`ErrorWeb`; dependencias `SesionWeb`, `ClienteWeb`, `AdminWeb`), `filtros.py` (día local + `tz` → UTC), `acceso.py` (`/`, `/login`, `/clave`, `/salir`), `cliente.py` (`/inicio`, `/recargar*`, `/historial*`, `/fondos`), `admin.py` (`/gestion*`). CSRF en `<body hx-headers>`; HTMX intercambia también los 4xx y el 502. Plantillas en `app/templates/` (`admin/` solo para el admin). Los estáticos se enlazan con `estatico("archivo")` (añade `?v=<hash>`).
- **Recarga en tres pasos** (CHG-010, plan sec. 6.1): todo ocurre dentro de `#recarga`. `/recargar` (solo Player ID) → `/recargar/validar` (valida con el paquete activo más barato; `_paso_paquetes.html` = tarjeta del jugador con la inicial y paquetes; errores en `#mensaje-id`) → `/recargar/resumen` (al tocar un paquete; `_confirmacion.html` con el token, sin llamar a VentasFF) → `/recargar/confirmar` (el pedido reemplaza toda la pantalla; errores en `#mensaje-confirmacion`).
- **Móvil** (CHG-009, plan sec. 6.2): `app/static/app.css` mobile-first con corte en 768 px: menú plegable (`ul.menu-plegable`), listados `table.tarjetas` con `data-etiqueta` (`td.secundario` se oculta, `td.accion` sin etiqueta), `dl.ficha`, `details.filtros`, áreas de 44 px (`--area-tactil`). Logo en `app/static/logo.png` (más `favicon.png` y `apple-touch-icon.png`).
- **Endurecimiento** (T-081, T-082, T-110 a T-114; CHG-016, CHG-017; plan sec. 7): middlewares ASGI propios en `app/main.py` (`LimiteCuerpo` 64 KB → 413, RNF-13; `CabecerasSeguridad` con CSP sin nada en línea y `no-store`, RNF-14: no añadir `style=`/`<script>` en línea ni `hx-on`); sin `/docs`, `/redoc` ni `/openapi.json` (RNF-15; `app.openapi()` sigue sirviendo a las pruebas); `ip_cliente` respeta `CLIENT_IP_HEADER` solo con conexión de loopback/RFC 1918 (`REDES_DE_CONFIANZA`, RNF-16); `LimitadorPorUsuario` (10 validaciones/min por cliente, RF-56) en `app.state.limitador_validaciones`; el motor usa `hide_parameters=True`. Pruebas: `test_logs_flujos`, `test_seguridad_rutas` (inventario de rutas: sesión, CSRF y rol; una ruta nueva sin protección la rompe), `test_limites_entrada`, `test_endurecimiento_web`; la prueba de navegador falla ante violaciones de CSP.
- **Esquemas:** los de cliente van en `app/schemas/` (cualquier módulo que no empiece por `admin`) y una prueba falla si declaran algo con "costo"; los de admin, en `app/schemas/admin*.py`. Montos con el tipo `Monto` (texto con 2 decimales) y `moneda: "USD"` (RF-36).

### Pruebas: cómo escribirlas

- Simulador: `tests/fake_ventasff.py` → `SimuladorVentasFF(escenario_recarga=…, escenario_validar=…, credito=…, busy_restantes=…)`; cliente con `ClienteVentasFF(sim.api_key, "http://simulador/api/reseller", transport=sim.transporte())`. `sim.recargas` dice si el proveedor cobró.
- API: fixture `api` (fábrica de `httpx.AsyncClient` contra la app; `api(ip)` fija la IP; un tarro de cookies por cliente) y fixture `simulador` (el VentasFF de la app en la prueba). `tests/utilidades_api.py`: `crear_usuario_con_clave` (confirma; clientes con saldo en cero) e `iniciar_sesion` (deja la cabecera CSRF en el cliente). Los pedidos creados con `crear_pedido` no tienen `codigo`: asignar `codigo_pedido(pedido.id)` si la prueba lo usa. Usar precios ficticios (0.50/0.75; el simulador cuesta 0.50).
- Integración (T-080): `tests/test_integracion_escenarios.py` recorre por HTTP cada escenario del simulador (abono del admin → recarga → vistas del cliente y del admin → alertas → CA-04). Si se añade un escenario a `ESCENARIOS_RECARGA`, una prueba falla hasta que se agregue su caso en `CASOS`. Suite ≈ 6 min (BUSY espera 3 s reales).
- Web: `tests/utilidades_web.py` (`cliente_web` = cliente con sesión, saldo y paquete; `htmx_post`/`htmx_get` con `HX-Request`; `csrf_de(html)`). Estructura móvil de las plantillas en `tests/test_web_movil.py`.
- Navegador (CA-07): `tests/test_movil_navegador.py`, fixtures `servidor_web` (uvicorn en el loop de pytest) y `navegador` (Chromium; se omite sin él); `medir(pagina, nombre, problemas)` comprueba desbordamiento y controles < 44 px a 360 × 740. Toda pantalla nueva debe sumarse a su recorrido.
- El esquema `test` se crea **una vez por sesión** de pytest y lo comparten todas las pruebas: usar ids/nombres únicos (`tests/utilidades.py`: `crear_usuario`, `crear_paquete`, `crear_pedido`; fixtures `cuenta`, `admin_id`), aserciones solo sobre lo propio y `rollback` cuando no haga falta persistir. Releer con `execution_options(populate_existing=True)`; tras un `rollback` no acceder a atributos de objetos ORM (expiran → `MissingGreenlet`).
- Motor y event loop son de alcance sesión. El enlace al VPS es lento (~0.5 s por consulta): minimizar ida y vuelta. Suite completa ≈ 15 min (≈ 580 pruebas tras la adaptación a móvil).
- Dos procesos de pytest con BD a la vez se pisan (cada sesión recrea `test`): no correr pruebas de BD en paralelo.

### Forma de trabajo acordada con el usuario

- Al terminar cada tarea: marcar `[x]`, commit y **push** a `origin/main` (repositorio público: revisar que no haya secretos antes). Avisar al usuario al terminar cada fase.
- El LLM principal orquesta y delega tareas básicas y acotadas a subagentes Haiku (simuladores, utilidades puras, servicios con contrato exacto, tablas de pruebas). La lógica contable, transaccional y de clasificación la hace el principal. A cada subagente: lista cerrada de archivos, sin git, sin leer `.env`, sin suite completa; revisar e integrar antes del commit.

### Pendientes y decisiones abiertas (2026-10-08, tras CHG-009 y CHG-010)

- **Hecho en esta sesión:** T-100 a T-104 (adaptación a móvil) y T-106 (recarga en tres pasos, CHG-010, spec 0.9.0), más ajustes visuales pedidos por el dueño: Player ID, jugador y referencia visibles en las tarjetas del historial; logo; resumen legible de la última sincronización; menú alineado en Firefox; estáticos con versión.
- **Sesión 2026-10-09:** T-080 a T-082 y T-110 a T-114 hechas (fase 8 salvo T-083). Pendiente de decidir para producción: con el túnel de Cloudflare definir `CLIENT_IP_HEADER=CF-Connecting-IP` en el `.env` y publicar el puerto 8000 solo en `127.0.0.1` (si no, el tope por IP del login bloquea a todos a la vez y alguien en una red privada podría falsificar la cabecera).
- **Pruebas de BD: nunca dos procesos de pytest a la vez** (ni siquiera una prueba suelta mientras corre la suite: se recrea el esquema `test`). La suite completa tarda ≈ 27 min (625 pruebas).
- **T-105:** revisión en un celular real, a cargo del dueño. Sus hallazgos se registran como tareas nuevas.
- **Próximo paso:** el dueño sigue revisando la web y avisará de inconsistencias. Clasificar cada pedido (significativo / menor / técnico) antes de tocar código. Queda T-083 (trazabilidad) de la fase 8; la fase 9 (despliegue) sigue bloqueada por el dominio.
- **Propuesto y sin respuesta:** mensaje propio en rojo con el Player ID vacío (hoy solo el aviso del navegador); mostrar el motivo del fallo en las tarjetas del historial; nickname mientras se escribe (descartado por ahora: CHG-010 lo resolvió con el botón).
- Acordado con el usuario (2026-10-08): proponer un cambio de spec para que, si `productos.php` llega vacío, la sincronización no desactive todo el catálogo (p. ej. no desactivar nada y generar alerta). Presentar el texto exacto antes de aplicarlo.
- La BD de desarrollo tiene 3 paquetes ficticios del simulador con precio de prueba: nunca conectar la API real a esa BD (un `paquete_id` real igual heredaría ese precio). Producción usa otra base.
- Un fallo inesperado (excepción) en la tarea de fases B/C deja el pedido en `PROCESANDO` hasta el siguiente arranque (RN-09); se registra en el log.
- Producción: usuario de BD dedicado con clave fuerte; rotar la API Key de VentasFF que se compartió en un chat; `--workers 1` (limitadores de login y de VentasFF en memoria).
- `.preview/` (local, ignorado por `.git/info/exclude`): arnés de vista previa (`render.py` genera las páginas con datos ficticios y `medir.py` mide a un ancho dado). No es parte del repo.
- Las sesiones en segundo plano pueden no tener credenciales para `git push`; si falla, pedir al usuario `! git push origin main`. En esta sesión el usuario hace el push.

## Convenciones

- Código, identificadores y comentarios técnicos en **español** (mismos términos que la spec: `pedidos`, `saldos`, `movimientos`, `precio_venta`…). Se aceptan términos técnicos sin traducción habitual (`router`, `schema`, `fixture`).
- Mensajes al usuario final en español.
- Commits: `T-XXX <resumen> [RF-/RN-/RNF-...]`. Cambios sin tarea: `Docs: …`, `Plan: …` o `Ajuste: …` (menores). Una tarea por commit.
- Las excepciones se capturan por tipo concreto (ruff `BLE001`); nada de `except Exception` salvo para limpiar y relanzar.
- Formato y lint: `ruff`.
- Dependencias y Python 3.12 gestionados con `uv` (`pyproject.toml` + `uv.lock`). Pruebas: `uv run pytest`; lint: `uv run ruff check .`.

## Qué no hacer

- No ampliar el alcance (p. ej. Mobile Legends) sin un cambio de spec aprobado.
- No agregar Caddy, dominio ni HTTPS hasta que se apruebe el cambio de spec correspondiente.
- No inventar campos o endpoints de VentasFF fuera de la sección 9 de la spec.
- No modificar migraciones ya aplicadas; crear una nueva.
- No subir `.env`, volcados de BD ni datos reales.
