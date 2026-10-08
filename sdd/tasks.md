# Tareas

- **Spec:** `sdd/spec.md` v0.5.0 · **Plan:** `sdd/plan.md`
- **Formato:** `- [ ] T-XXX descripción (refs) → criterio de hecho`
- **Estados:** `[ ]` pendiente · `[~]` en curso · `[x]` hecha · `[!]` bloqueada
- Cada tarea referencia requisitos (RF/RN/RNF/CA). Una tarea sin referencia no debería existir: o falta un requisito en la spec, o sobra la tarea.
- Tareas nuevas surgidas del desarrollo se añaden al final de su fase con el siguiente ID libre. Los IDs nunca se reutilizan.

---

## Fase 1 — Fundación

- [x] T-001 Crear repositorio con estructura del plan, `.gitignore` (`.env`, datos, respaldos, logs) y README (RNF-06) → `git status` limpio sin secretos.
- [x] T-002 `.env.example` con `VENTASFF_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE` vacíos (RNF-01, RNF-06, RNF-07, RNF-11) → variables documentadas.
- [x] T-003 `Dockerfile` y `docker-compose.yml` con `app` (puerto publicado, ej. 8000), sin `caddy` ni `db`, unido a la red externa `ffmovil_net` (RNF-07) → `docker compose up` levanta la app y conecta a la BD externa.
- [x] T-004 `config.py` con carga de variables de entorno y falla clara si falta alguna → la app no inicia sin configuración.
- [x] T-005 Conexión a la BD externa por `DATABASE_URL`, verificación al arrancar con error claro y Alembic configurado (RNF-07) → migración vacía aplicable.
- [x] T-006 Endpoint `/health` y configuración de pytest + ruff → `pytest` y `ruff` ejecutan en limpio.
- [x] T-007 Fixtures de pruebas con esquema `test` aislado, creado y eliminado por sesión, vía `TEST_DATABASE_URL` (RNF-10) → las pruebas no tocan el esquema de desarrollo.

## Fase 2 — Núcleo contable

- [x] T-010 Migración: `usuarios`, `saldos`, `movimientos`, `auditoria` con restricciones `CHECK` (RN-01, RNF-04) → migración aplicada.
- [x] T-011 Proteger `movimientos` contra `UPDATE`/`DELETE` (RF-42) → intento de modificar falla en test.
- [x] T-012 Servicio `ledger`: abono, ajuste, reserva, liberación, cargo, con `SELECT … FOR UPDATE` (RNF-02) → pruebas unitarias de cada operación.
- [x] T-013 Prueba de invariante: saldo = suma de movimientos (CA-04) → test pasa tras secuencia aleatoria de operaciones.
- [x] T-014 Prueba de concurrencia: dos reservas simultáneas con saldo para una (CA-01) → solo una prospera.
- [x] T-015 Servicio de autenticación: argon2, creación de usuario con clave temporal y `debe_cambiar_clave` (RF-01, RF-02, RNF-03) → tests.
- [x] T-016 Script/comando para crear el primer admin → admin creado por CLI.

## Fase 3 — Cliente VentasFF + simulador

- [x] T-020 `ventasff_client.py`: `saldo`, `productos`, `validar`, `recargar` con Bearer, timeouts 15/30/90 s, parseo de `success/error/code` (RNF-01) → tests con respx.
- [x] T-021 Clasificación de resultados: éxito / error de API / error previo al envío / incierto (timeout, ilegible) (RF-24, RN-04) → tabla de casos cubierta por tests.
- [x] T-022 Manejo de `Retry-After` y `RATE_LIMITED` (RN-07) → test.
- [x] T-023 `tests/fake_ventasff.py` con escenarios `ok`, `PURCHASE_FAILED`, `BUSY`, `INSUFFICIENT_CREDIT`, `INVALID_KEY`, timeout, ilegible, `nickname: null` (RNF-08) → usable desde pytest y como servidor local para desarrollo.
- [x] T-024 Enmascarado de secretos en logs (RNF-05) → test que verifica que la key no aparece.

## Fase 4 — Catálogo y precios

- [x] T-030 Migración `paquetes` y `config` (RF-10 a RF-12) → aplicada.
- [ ] T-031 Validación de `precio_venta`: decimal > 0, advertencia si `precio_venta <= precio_costo`, no se activa sin precio (RF-11, RF-12, RNF-04) → tests con 0.81 / 0.91 y casos límite.
- [ ] T-032 `sincronizar_catalogo()`: upsert de costo, filtro `free_fire`, nuevos inactivos sin precio, desactivar ausentes, sin tocar `precio_venta` (RF-10, RF-14) → test contra simulador.
- [ ] T-033 Tarea programada diaria con APScheduler, un solo worker (RF-10) → ejecuta y registra resultado.
- [x] T-034 Esquemas Pydantic del cliente sin `precio_costo` (RF-13, RF-35, CA-03) → test recorre esquemas y falla si aparece.

## Fase 5 — Recarga transaccional

- [ ] T-040 Migración `pedidos` y `pedido_eventos` con índices y `UNIQUE (usuario_id, token_idempotencia)` (RF-25, RF-30) → aplicada.
- [ ] T-041 Generación de `codigo` (`FF-000123`) (RF-30) → único y legible.
- [ ] T-042 Máquina de estados con transiciones permitidas (sec. 7 de la spec) → transiciones inválidas lanzan error.
- [ ] T-043 Endpoint de validación: formato de Player ID, `validar.php`, manejo de `no_existe`/`no_disponible` (RF-20, RF-27) → tests.
- [ ] T-044 Fase A: reserva e inserción de pedido en una transacción, con idempotencia (RF-22, RF-25) → tests, incluido reenvío con mismo token (CA-02).
- [ ] T-045 Fase B: candado global (`pg_advisory_lock`), limitador de tasa propio, verificación de `saldo.php`, `recargar.php` con un reintento ante `BUSY` (RF-23, RN-05 a RN-08) → tests contra simulador.
- [ ] T-046 Fase C: resolución según resultado, con contabilidad por caso (RF-24, RN-02) → un test por escenario del simulador.
- [ ] T-047 Recuperación al iniciar: `PROCESANDO` huérfanos → `PENDIENTE_VERIFICAR` (RN-09) → test.
- [ ] T-048 Resolución manual por admin de `PENDIENTE_VERIFICAR` (RF-52, RN-04) → tests de ambos resultados y rechazo de estados inválidos.
- [ ] T-049 Alertas al admin: crédito bajo, `INSUFFICIENT_CREDIT`, errores de cuenta (RN-08, Q-06) → alerta visible en el panel.

## Fase 6 — API cliente y admin

- [ ] T-050 Login/logout, sesión por cookie (`Secure` según `COOKIE_SECURE`), bloqueo de usuarios inactivos, limitador de intentos (RF-01, RF-04, RF-05) → tests.
- [ ] T-051 Cambio obligatorio de contraseña y middleware que restringe acceso (RF-02) → tests.
- [ ] T-052 `/me/resumen`, `/me/fondos` (RF-33, RF-34) → tests con datos de ejemplo.
- [ ] T-053 `/me/pedidos` con filtros y paginación; `/me/pedidos/{codigo}` solo del propio usuario (RF-31, RF-32, CA-05) → tests, incluido acceso a pedido ajeno → 404.
- [ ] T-054 `/paquetes` y `/recargas` (RF-13, RF-21) → tests.
- [ ] T-055 Admin usuarios: crear, bloquear, desbloquear, resetear clave (RF-03) → tests y auditoría.
- [ ] T-056 Admin saldos: abono y ajuste con nota obligatoria (RF-40, RF-41) → tests.
- [ ] T-057 Admin pedidos: filtros y detalle con costo y ganancia (RF-50, RF-51, RF-54, CA-06) → tests.
- [ ] T-058 Admin panel: saldo VentasFF vs suma de saldos de clientes (RF-53, RN-10) → test contra simulador.
- [ ] T-059 Admin catálogo: `precio_venta` por paquete, activar/desactivar, sincronizar ahora, marcador de precio bajo costo (RF-12, RF-14) → tests.
- [ ] T-060 Auditoría de acciones admin (RF-55) → cada acción registra una fila.
- [ ] T-061 `require_admin` en `/admin/*` (RNF-03) → cliente recibe 403.

## Fase 7 — Frontend

- [ ] T-070 Resolver Q-05 (Jinja2 + HTMX o SPA) y registrar decisión en `changelog.md` → decisión registrada.
- [ ] T-071 Login y cambio de contraseña.
- [ ] T-072 Inicio del cliente: saldo, gasto total, nº de recargas, botones (RF-33).
- [ ] T-073 Pantalla Recargar: Player ID → nickname → paquete → confirmación, con token de idempotencia y botón deshabilitado tras el primer clic (RF-20, RF-21, RF-25).
- [ ] T-074 Historial con filtros y estados visibles, incluidos fallidos y "En revisión" (RF-31, RF-32, CA-05).
- [ ] T-075 Pantalla Fondos (RF-34).
- [ ] T-076 Pantallas admin: usuarios, abonos, pedidos con filtros, resolución de pendientes, panel, configuración (RF-50 a RF-53).
- [ ] T-077 Verificar que ninguna plantilla muestra `precio_costo` al cliente (CA-03).

## Fase 8 — Endurecimiento y pruebas

- [ ] T-080 Suite de integración completa por escenario del simulador → todos pasan.
- [ ] T-081 Revisión de logs: sin API Key ni contraseñas (RNF-05).
- [ ] T-082 Revisión de seguridad: CSRF, cookies, cabeceras, límites (RNF-03).
- [ ] T-083 Verificación de trazabilidad: cada RF/RN/CA tiene al menos una tarea y una prueba → tabla en `changelog.md` o script.

## Fase 9 — Despliegue

- [!] T-090 Caddy con dominio e HTTPS; `COOKIE_SECURE=true`; solo 80/443 publicados (RNF-03, RNF-11) → bloqueada hasta tener dominio; requisito previo a clientes reales.
- [ ] T-091 Variables reales en el VPS (fuera del repo) (RNF-01, RNF-06).
- [ ] T-092 Respaldo periódico de PostgreSQL fuera del repositorio.
- [ ] T-093 Prueba real controlada: una recarga del paquete más barato con ID propio; verificar en el juego y en el panel de VentasFF.
- [ ] T-094 Alta del primer cliente y primer abono manual de prueba.

---

## Tareas emergentes

Se agregan aquí con el siguiente ID libre (`T-1xx`), indicando el cambio de spec que las originó (`CHG-XXX`).
