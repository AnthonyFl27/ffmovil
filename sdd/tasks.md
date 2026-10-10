# Tareas

- **Spec:** `sdd/spec.md` v0.18.0 · **Plan:** `sdd/plan.md`
- **Formato:** `- [ ] T-XXX descripción (refs) → criterio de hecho`
- **Estados:** `[ ]` pendiente · `[~]` en curso · `[x]` hecha · `[!]` bloqueada
- Cada tarea referencia requisitos (RF/RN/RNF/CA). Una tarea sin referencia no debería existir: o falta un requisito en la spec, o sobra la tarea.
- Tareas nuevas surgidas del desarrollo se añaden al final de su fase con el siguiente ID libre. Los IDs nunca se reutilizan.

---

## Fase 1 — Fundación

- [x] T-001 Crear repositorio con estructura del plan, `.gitignore` (`.env`, datos, respaldos, logs) y README (RNF-06) → `git status` limpio sin secretos.
- [x] T-002 `.env.example` con `VENTASFF_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE` vacíos (RNF-01, RNF-06, RNF-07, RNF-11) → variables documentadas.
- [x] T-003 `Dockerfile` y `docker-compose.yml` con `app` (puerto publicado, ej. 8000), sin `caddy` ni `db`, unido a la red externa `ffmovil_net` (RNF-07) → `docker compose up` levanta la app y conecta a la BD externa.
- [x] T-004 `config.py` con carga de variables de entorno y falla clara si falta alguna (RNF-01, RNF-07) → la app no inicia sin configuración.
- [x] T-005 Conexión a la BD externa por `DATABASE_URL`, verificación al arrancar con error claro y Alembic configurado (RNF-07) → migración vacía aplicable.
- [x] T-006 Endpoint `/health` y configuración de pytest + ruff (RNF-10) → `pytest` y `ruff` ejecutan en limpio.
- [x] T-007 Fixtures de pruebas con esquema `test` aislado, creado y eliminado por sesión, vía `TEST_DATABASE_URL` (RNF-10) → las pruebas no tocan el esquema de desarrollo.

## Fase 2 — Núcleo contable

- [x] T-010 Migración: `usuarios`, `saldos`, `movimientos`, `auditoria` con restricciones `CHECK` (RN-01, RNF-04) → migración aplicada.
- [x] T-011 Proteger `movimientos` contra `UPDATE`/`DELETE` (RF-42) → intento de modificar falla en test.
- [x] T-012 Servicio `ledger`: abono, ajuste, reserva, liberación, cargo, con `SELECT … FOR UPDATE` (RNF-02) → pruebas unitarias de cada operación.
- [x] T-013 Prueba de invariante: saldo = suma de movimientos (CA-04) → test pasa tras secuencia aleatoria de operaciones.
- [x] T-014 Prueba de concurrencia: dos reservas simultáneas con saldo para una (CA-01) → solo una prospera.
- [x] T-015 Servicio de autenticación: argon2, creación de usuario con clave temporal y `debe_cambiar_clave` (RF-01, RF-02, RNF-03) → tests.
- [x] T-016 Script/comando para crear el primer admin (RF-03, RF-07) → admin creado por CLI.

## Fase 3 — Cliente VentasFF + simulador

- [x] T-020 `ventasff_client.py`: `saldo`, `productos`, `validar`, `recargar` con Bearer, timeouts 15/30/90 s, parseo de `success/error/code` (RNF-01) → tests con respx.
- [x] T-021 Clasificación de resultados: éxito / error de API / error previo al envío / incierto (timeout, ilegible) (RF-24, RN-04) → tabla de casos cubierta por tests.
- [x] T-022 Manejo de `Retry-After` y `RATE_LIMITED` (RN-07) → test.
- [x] T-023 `tests/fake_ventasff.py` con escenarios `ok`, `PURCHASE_FAILED`, `BUSY`, `INSUFFICIENT_CREDIT`, `INVALID_KEY`, timeout, ilegible, `nickname: null` (RNF-08) → usable desde pytest y como servidor local para desarrollo.
- [x] T-024 Enmascarado de secretos en logs (RNF-05) → test que verifica que la key no aparece.

## Fase 4 — Catálogo y precios

- [x] T-030 Migración `paquetes` y `config` (RF-10 a RF-12) → aplicada.
- [x] T-031 Validación de `precio_venta`: decimal > 0, advertencia si `precio_venta <= precio_costo`, no se activa sin precio (RF-11, RF-12, RNF-04) → tests con precios ficticios (0.50 / 0.75) y casos límite.
- [x] T-032 `sincronizar_catalogo()`: upsert de costo, filtro `free_fire`, nuevos inactivos sin precio, desactivar ausentes, sin tocar `precio_venta` (RF-10, RF-14) → test contra simulador.
- [x] T-033 Tarea programada diaria con APScheduler, un solo worker (RF-10) → ejecuta y registra resultado.
- [x] T-034 Esquemas Pydantic del cliente sin `precio_costo` (RF-13, RF-35, CA-03) → test recorre esquemas y falla si aparece.

## Fase 5 — Recarga transaccional

- [x] T-040 Migración `pedidos` y `pedido_eventos` con índices y `UNIQUE (usuario_id, token_idempotencia)` (RF-25, RF-30) → aplicada.
- [x] T-041 Generación de `codigo` (`FF-000123`) (RF-30) → único y legible.
- [x] T-042 Máquina de estados con transiciones permitidas (sec. 7 de la spec; RF-24, RF-52, RN-04) → transiciones inválidas lanzan error.
- [x] T-043 Validación: formato de Player ID, `validar.php`, manejo de `no_existe`/`no_disponible`, nickname desde `validar.php` (RF-20, RF-26, RF-27) → tests del servicio; la ruta `POST /recargas/validar` con sesión se expone en T-054.
- [x] T-044 Fase A: reserva e inserción de pedido en una transacción, con idempotencia (RF-22, RF-25) → tests, incluido reenvío con mismo token (CA-02).
- [x] T-045 Fase B: candado global (`pg_advisory_lock`), limitador de tasa propio, verificación de `saldo.php`, `recargar.php` con un reintento ante `BUSY` (RF-23, RN-05 a RN-08) → tests contra simulador.
- [x] T-046 Fase C: resolución según resultado, con contabilidad por caso (RF-24, RN-02) → un test por escenario del simulador.
- [x] T-047 Recuperación al iniciar: `PROCESANDO` huérfanos → `PENDIENTE_VERIFICAR` (RN-09) → test.
- [x] T-048 Resolución manual por admin de `PENDIENTE_VERIFICAR` (RF-52, RN-04) → tests de ambos resultados y rechazo de estados inválidos.
- [x] T-049 Alertas al admin: tabla `alertas`, umbral `alerta_credito_min` = 10.00 en `config`, alertas de crédito bajo, `INSUFFICIENT_CREDIT`/sin crédito y errores de cuenta, sin duplicar activas, marcar como atendida (RN-08, RN-11; CHG-006) → tests; la pantalla del panel se hace en T-076.

## Fase 6 — API cliente y admin

- [x] T-050 Migración `sesiones`; login/logout, sesión por cookie (`Secure` según `COOKIE_SECURE`) con expiración de 8 h de inactividad, CSRF por cabecera, bloqueo de usuarios inactivos, limitador de intentos (RF-01, RF-04, RF-05, RF-06, RF-07; CHG-007) → tests.
- [x] T-051 Cambio obligatorio de contraseña con política mínima y dependencia que restringe acceso; el cambio cierra las demás sesiones (RF-02, RF-06, RF-08; CHG-007) → tests.
- [x] T-052 `/me/resumen`, `/me/fondos` (RF-33, RF-34, RF-36; CHG-007) → tests con datos de ejemplo.
- [x] T-053 `/me/pedidos` con filtros y paginación; `/me/pedidos/{codigo}` solo del propio usuario (RF-31, RF-32, CA-05) → tests, incluido acceso a pedido ajeno → 404.
- [x] T-054 `/paquetes` y `/recargas` (RF-13, RF-21) → tests.
- [x] T-055 Admin usuarios: crear cliente, bloquear, desbloquear, resetear clave; bloquear y resetear cierran sesiones (RF-03, RF-06, RF-07; CHG-007) → tests y auditoría.
- [x] T-056 Admin saldos: abono y ajuste con nota obligatoria (RF-40, RF-41) → tests.
- [x] T-057 Admin pedidos: filtros y detalle con costo y ganancia (RF-50, RF-51, RF-54, CA-06) → tests.
- [x] T-058 Admin panel: saldo VentasFF vs suma de saldos de clientes, alertas activas y atenderlas, `/admin/config` (RF-53, RN-10, RN-11) → test contra simulador.
- [x] T-059 Admin catálogo: `precio_venta` por paquete, activar/desactivar, sincronizar ahora, marcador de precio bajo costo (RF-12, RF-14) → tests.
- [x] T-060 Auditoría de acciones admin (RF-55) → cada acción registra una fila.
- [x] T-061 `require_admin` en `/admin/*` (RNF-03) → cliente recibe 403.

## Fase 7 — Frontend

- [x] T-070 Resolver Q-05 (Jinja2 + HTMX o SPA) y registrar decisión en `changelog.md` (Q-05, CHG-008) → decisión registrada.
- [x] T-071 Login y cambio de contraseña (RF-01, RF-02, RF-08).
- [x] T-072 Inicio del cliente: saldo, gasto total, nº de recargas, botones (RF-33).
- [x] T-073 Pantalla Recargar: Player ID → nickname → paquete → confirmación, con token de idempotencia y botón deshabilitado tras el primer clic (RF-20, RF-21, RF-25).
- [x] T-074 Historial con filtros y estados visibles, incluidos fallidos y "En revisión", con fechas en la zona del navegador (RF-31, RF-32, RNF-09, CA-05).
- [x] T-075 Pantalla Fondos (RF-34).
- [x] T-076 Pantallas admin: usuarios, abonos, pedidos con filtros, resolución de pendientes, panel, configuración (RF-50 a RF-53).
- [x] T-077 Verificar que ninguna plantilla muestra `precio_costo` al cliente (CA-03).

## Fase 8 — Endurecimiento y pruebas

- [x] T-080 Suite de integración completa por escenario del simulador (RF-22, RF-24, RF-25, RF-52, RN-04, RN-08, RN-11, CA-02 a CA-05) → todos pasan (`tests/test_integracion_escenarios.py`: recorrido HTTP completo por cada escenario, resolución manual de pendientes, secuencia mixta y saldo insuficiente).
- [x] T-081 Revisión de logs: sin API Key ni contraseñas (RNF-05) → `tests/test_logs_flujos.py`: flujos reales sin enmascarar no emiten secretos; `hide_parameters=True` en el motor.
- [x] T-082 Revisión de seguridad: CSRF, cookies, cabeceras, límites (RNF-03) → `tests/test_seguridad_rutas.py` recorre todas las rutas (sesión, CSRF y rol); hallazgos resueltos en T-110 a T-114 (CHG-016, CHG-017).
- [x] T-083 Verificación de trazabilidad: cada RF/RN/RNF/CA tiene al menos una tarea y una prueba → `tests/trazabilidad.py` (`uv run python -m tests.trazabilidad` imprime la tabla) y `tests/test_trazabilidad.py` falla ante cualquier hueco; RNF-06 y RNF-07 se verifican por revisión (lista `SIN_PRUEBA_AUTOMATICA`). Una prueba cubre un requisito si lo nombra en su archivo.

## Fase 9 — Despliegue

- [!] T-090 Caddy con dominio e HTTPS; `COOKIE_SECURE=true`; solo 80/443 publicados (RNF-03, RNF-11) → bloqueada hasta tener dominio; requisito previo a clientes reales.
- [ ] T-091 Variables reales en el VPS (fuera del repo) (RNF-01, RNF-06).
- [x] T-092 Respaldo periódico de PostgreSQL fuera del repositorio (RNF-06, RNF-07) → cubierto por el dueño (2026-10-10), fuera del repo.
- [ ] T-093 Prueba real controlada: una recarga del paquete más barato con ID propio; verificar en el juego y en el panel de VentasFF (RF-24, RN-03).
- [ ] T-094 Alta del primer cliente y primer abono manual de prueba (RF-03, RF-40).

---

## Tareas emergentes

Se agregan aquí con el siguiente ID libre (`T-1xx`), indicando el cambio de spec que las originó (`CHG-XXX`).

### Adaptación a móvil (CHG-009, RNF-12, CA-07)

Auditoría previa (2026-10-08, 360 y 390 px): el documento se desbordaba en todas las pantallas (menú sin plegar: 445 px en cliente y 664 px en admin); el historial del cliente mide 900 px y oculta el estado; "Salir" 34 px, radios de paquete 20 px, enlaces de usuario 22 px, casilla "solo pendientes" 20 px.

- [x] T-100 Navegación plegable (menú desplegable) en pantallas angostas, para cliente y admin (RNF-12, CHG-009) → sin desbordamiento horizontal a 360 px; todas las opciones alcanzables.
- [x] T-101 Historial del cliente y detalle en tarjetas, con filtros plegables y estado visible (RNF-12, RF-31, RF-32, CA-05) → a 360 px el estado se ve sin desplazarse.
- [x] T-102 Pantallas admin en móvil: pedidos, usuarios, paquetes y auditoría en tarjetas; ajustes del panel, detalle de pedido y configuración (RNF-12, RF-50 a RF-55) → utilizables a 360 px, sin cambios en escritorio.
- [x] T-103 Áreas táctiles de 44 px: botones, enlaces de acción, casillas y opciones de paquete; cifras sin tarjetas huérfanas (RNF-12) → ningún control interactivo < 44 px a 360 px.
- [x] T-104 Prueba automatizada de viewport móvil con Playwright (dev) sobre todas las pantallas de cliente y admin (CA-07, RNF-12) → la prueba falla ante desbordamiento o un control < 44 px; se omite con aviso sin Chromium.
- [x] T-105 Revisión final en un celular real, por el dueño (RNF-12) → sin hallazgos (aprobada por el dueño, 2026-10-10).

### Recarga en tres pasos (CHG-010, RF-20, RF-21)

- [x] T-106 Pantalla Recargar en tres pasos: solo Player ID; tarjeta del jugador y paquetes; resumen al tocar un paquete y confirmación (RF-20, RF-21, RF-25, RN-03, CHG-010) → pruebas web de cada paso (incluidos `no_existe` y `no_disponible`) y prueba de navegador a 360 px del flujo completo.

### Abonos por encima del crédito de VentasFF (CHG-011, RF-53, RN-10)

- [x] T-107 Panel con saldo por cubrir: `Panel.saldo_por_cubrir` (`max(saldos − crédito, 0)`), etiqueta "Saldo por cubrir" y nota neutra en lugar del aviso de error; el abono no cambia (RF-53, RN-10, CHG-011) → pruebas: un abono mayor que el crédito se acepta, el panel informa el saldo por cubrir y no muestra error, y la recarga sin crédito sigue fallando con alerta (RF-23, RN-08).

### Últimas recargas en el inicio del cliente (CHG-012, RF-33)

- [x] T-108 Inicio del cliente con sus últimas 5 recargas de cualquier estado, con enlace a cada detalle y estado vacío; sin "Ver todo" (RF-33, CHG-012, CHG-013) → pruebas web: lista con recargas en distintos estados, estado vacío, solo pedidos propios y sin ningún dato de costo; prueba de navegador a 360 px.

### Historial de movimientos del cliente en el admin (CHG-014, RF-43)

- [x] T-109 Historial de abonos y ajustes en la ficha del cliente: `GET /admin/usuarios/{id}/movimientos` y tabla en `/gestion/usuarios/{id}` (fecha, tipo, monto, nota) con filtros (tipo, fechas) y paginación (RF-43, RF-42, CHG-014, CHG-015) → pruebas: solo abonos y ajustes (sin reservas, liberaciones ni cargos), orden descendente, paginación, filtros por tipo y fechas, 404 para un id inexistente, 403 para un cliente y solo movimientos del usuario consultado; prueba de navegador a 360 px.

### Límites de entrada (CHG-016, RNF-13)

- [x] T-110 Límite de 64 KB al cuerpo de las peticiones (413) y rechazo temprano de `usuario` > 30 o `clave` > 128 en el login (RNF-13, CHG-016) → pruebas: 413 por `Content-Length` y por flujo sin cabecera, un cuerpo de 64 KB exactos pasa, login largo = 401 genérico que cuenta como fallo y no llama a `autenticar`, y las rutas normales no cambian.

### Endurecimiento web (CHG-017, RNF-14 a RNF-16, RF-56)

- [x] T-111 Cabeceras de seguridad y `Cache-Control: no-store` en todas las respuestas; sin estilos ni scripts en línea (RNF-14, CHG-017) → pruebas: cada cabecera presente en páginas, API, errores (401, 413) y ausencia de `no-store` en `/static`; prueba de navegador sin violaciones de CSP en todo el recorrido.
- [x] T-112 Desactivar `/docs`, `/redoc` y `/openapi.json` (RNF-15, CHG-017) → las tres rutas responden 404 y el inventario de rutas lo refleja.
- [x] T-113 IP del cliente tras proxy con `CLIENT_IP_HEADER` (RNF-16, RF-05, RF-55, CHG-017) → pruebas: sin variable se ignora la cabecera; con variable y conexión loopback o privada se usa; con conexión pública se ignora; valor inválido se ignora; el limitador de login distingue dos clientes detrás del mismo proxy; `.env.example` y `config.py` documentan la variable.
- [x] T-114 Límite de 10 validaciones por minuto por usuario (RF-56, CHG-017) → pruebas: la 11.ª validación recibe 429 sin llamar a VentasFF, otro cliente no se ve afectado, la ventana se libera con el tiempo, y la web muestra el mensaje en `#mensaje-id`.

### Catálogo vacío en la sincronización (CHG-018, RF-10, RN-11, CA-08)

- [x] T-115 Si `productos.php` no trae ningún paquete `free_fire`, la sincronización no modifica el catálogo, el resultado lo indica (`resultado = "vacio"`) y se registra la alerta `catalogo_vacio` (migración que amplía el `CHECK` de `alertas.tipo`) (RF-10, RN-11, CA-08, CHG-018) → pruebas: catálogo vacío conserva paquetes activos y crea la alerta; una lista solo con otros juegos cuenta como vacía; una segunda sincronización vacía no duplica la alerta; con al menos un paquete `free_fire` se desactivan los ausentes como antes; la alerta no se atiende sola tras una sincronización correcta; el panel y `/gestion/paquetes` muestran la alerta y el aviso.

### Topes de intentos y de peticiones (CHG-019, RF-05, RF-57, RNF-17)

- [x] T-116 Tope de 10 fallos en 15 min por cuenta en el login, sin importar la IP (RF-05, CHG-019) → pruebas: el 10.º fallo desde IPs distintas bloquea la cuenta 15 min con el mismo 429 genérico, 9 fallos no bloquean, el bloqueo vence a los 15 min sin alargarse por intentos rechazados, un login correcto limpia el par pero no la cuenta, otra cuenta no se ve afectada, una clave correcta durante el bloqueo también se rechaza, el nombre de 64 KB no se guarda entero y los topes de par (5) e IP (20) siguen igual.
- [x] T-117 Tope de 5 pedidos por minuto por cliente en `POST /recargas` y `/recargar/confirmar` (RF-57, RF-25, CHG-019) → pruebas: la 6.ª solicitud recibe 429 sin reservar saldo, sin crear pedido y sin llamar a VentasFF; otro cliente no se ve afectado; la ventana se libera con el tiempo; un reenvío con el mismo token cuenta; las rechazadas no cuentan; la web muestra el mensaje en `#mensaje-confirmacion`.
- [x] T-118 Tope general de peticiones: 120/min por usuario y 60/min por IP sin sesión (RNF-17, RNF-16, CHG-019) → pruebas: la petición 121 de un usuario recibe 429 y otro usuario no se ve afectado; 60 peticiones sin sesión desde una IP no afectan a otra; `POST /auth/login` y `POST /login` cuentan por IP; `/static` y `/health` no cuentan; las rechazadas no cuentan; la ventana se libera; con sesión válida un 429 no redirige al login; el inventario de rutas de `test_seguridad_rutas` sigue pasando y la prueba de navegador completa su recorrido sin 429.
