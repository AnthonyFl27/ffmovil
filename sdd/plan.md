# Plan técnico

- **Spec de referencia:** `sdd/spec.md` v0.7.1
- **Regla:** este plan implementa la spec. Si el plan contradice la spec, gana la spec.

---

## 1. Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x async con psycopg 3, Alembic |
| Dependencias | uv (`pyproject.toml` + `uv.lock`) |
| Base de datos | PostgreSQL 18, externo (servidor propio en el VPS), acceso solo por `DATABASE_URL` |
| Frontend (Q-05, CHG-008) | Jinja2 + HTMX 2 servidos por FastAPI; Pico.css 2. HTMX y Pico se sirven desde `app/static` (sin CDN ni build) |
| HTTP cliente | httpx |
| Hash | argon2-cffi |
| Tareas programadas | APScheduler (sincronización diaria) |
| Proxy | Caddy (HTTPS automático), diferido hasta tener dominio |
| Contenedores | Docker Compose (`app`; `caddy` cuando haya dominio; sin servicio de BD) |
| Pruebas | pytest, pytest-asyncio, respx (mock HTTP) |
| Calidad | ruff, mypy (opcional) |

## 2. Estructura del repositorio

Monorepo: la API y la web viven en el mismo repositorio.

```
.
├── AGENTS.md
├── sdd/
│   ├── spec.md
│   ├── plan.md
│   ├── tasks.md
│   └── changelog.md
├── app/
│   ├── main.py
│   ├── config.py              # lee variables de entorno
│   ├── db.py
│   ├── models/                # SQLAlchemy
│   ├── schemas/               # Pydantic (respuestas cliente SIN costo)
│   ├── routers/
│   │   ├── auth.py
│   │   ├── me.py              # cliente: saldo, resumen, historial
│   │   ├── paquetes.py
│   │   ├── recargas.py
│   │   └── admin/             # usuarios, saldos, pedidos, config
│   ├── web/                   # páginas HTML (sec. 6.1)
│   ├── cli.py                 # python -m app.cli crear-admin <usuario>
│   ├── logs.py                # enmascarado de secretos (RNF-05)
│   ├── services/
│   │   ├── ventasff_client.py # único módulo que llama a VentasFF
│   │   ├── recarga_service.py # validación y fases A/B/C, resolución manual
│   │   ├── ledger.py          # movimientos y saldos
│   │   ├── montos.py          # validación común de montos Decimal
│   │   ├── catalogo.py        # precios, activación y sincronización
│   │   ├── tareas.py          # APScheduler: sincronización diaria
│   │   ├── estados.py         # máquina de estados del pedido
│   │   ├── codigos.py         # FF-000123 <-> id
│   │   ├── limitador.py       # límite de tasa propio (RN-07)
│   │   ├── recuperacion.py    # RN-09 al arrancar
│   │   ├── alertas.py         # alertas al admin (RN-11)
│   │   └── auth_service.py
│   ├── templates/             # Jinja2
│   └── static/
├── migrations/                # Alembic
├── tests/
│   ├── fake_ventasff.py       # simulador (RNF-08)
│   └── ...
├── docker-compose.yml
├── Dockerfile
├── Caddyfile                  # diferido hasta tener dominio
├── .env.example
└── .gitignore
```

## 3. Modelo de datos

Todos los montos: `NUMERIC(12,2)`. Fechas: `TIMESTAMPTZ` en UTC.

```sql
usuarios(
  id BIGSERIAL PK, usuario TEXT UNIQUE NOT NULL, hash_password TEXT NOT NULL,
  rol TEXT CHECK (rol IN ('admin','cliente')), debe_cambiar_clave BOOL DEFAULT true,
  activo BOOL DEFAULT true, creado_en, ultimo_login
)

saldos(
  usuario_id BIGINT PK REFERENCES usuarios,
  saldo_disponible NUMERIC(12,2) NOT NULL CHECK (saldo_disponible >= 0),
  saldo_reservado  NUMERIC(12,2) NOT NULL CHECK (saldo_reservado  >= 0)
)

paquetes(
  paquete_id INT PK,            -- id de VentasFF
  juego TEXT NOT NULL,          -- 'free_fire'
  nombre TEXT, diamantes INT,
  precio_costo NUMERIC(12,2),
  precio_venta NUMERIC(12,2) NULL,   -- definido por el admin
  activo BOOL DEFAULT false, actualizado_en,
  CHECK (activo = false OR precio_venta IS NOT NULL),
  CHECK (precio_venta IS NULL OR precio_venta > 0), CHECK (precio_costo >= 0)
)

config(clave TEXT PK, valor TEXT)   -- alerta_credito_min (inicial '10.00'), ...

alertas(                                 -- RN-08, RN-11
  id BIGSERIAL PK,
  tipo TEXT CHECK (tipo IN ('credito_bajo','sin_credito','cuenta')),
  mensaje TEXT NOT NULL, creada_en,
  atendida_en TIMESTAMPTZ NULL, atendida_por NULL REFERENCES usuarios
)  -- índice único parcial (tipo) WHERE atendida_en IS NULL: una activa por tipo

pedidos(
  id BIGSERIAL PK,
  codigo TEXT UNIQUE,                  -- 'FF-000123' derivado del id
  usuario_id, paquete_id, player_id TEXT, nickname TEXT NULL,
  precio_costo NUMERIC(12,2), precio_venta NUMERIC(12,2),
  estado TEXT CHECK (estado IN ('CREADO','PROCESANDO','EXITOSO','FALLIDO','PENDIENTE_VERIFICAR')),
  referencia TEXT NULL, error TEXT NULL, error_code TEXT NULL,
  token_idempotencia TEXT NOT NULL,
  creado_en, actualizado_en,
  UNIQUE (usuario_id, token_idempotencia)
)

pedido_eventos(                          -- historial de estados
  id, pedido_id, estado_anterior, estado_nuevo, detalle, creado_por NULL, fecha
)

movimientos(                             -- libro contable, solo INSERT
  id BIGSERIAL PK, usuario_id,
  tipo TEXT CHECK (tipo IN ('abono','reserva','liberacion','cargo','ajuste')),
  monto NUMERIC(12,2), saldo_disponible_resultante NUMERIC(12,2),
  saldo_reservado_resultante NUMERIC(12,2),
  pedido_id NULL, nota TEXT NULL, creado_por NULL, fecha
)

auditoria(id, usuario_id, accion, detalle JSONB, ip, fecha)

sesiones(                                -- RF-06 (CHG-007)
  token_hash TEXT PK,                    -- SHA-256 del token de la cookie; el token no se guarda
  usuario_id BIGINT NOT NULL REFERENCES usuarios ON DELETE CASCADE,
  csrf TEXT NOT NULL, ip INET NULL, creada_en, ultima_actividad
)  -- índice (usuario_id)
```

- `movimientos`: protegida con triggers que rechazan `UPDATE`, `DELETE` y `TRUNCATE` (aplican aunque la app sea dueña de la tabla).
- `movimientos.monto`: positivo en todos los tipos salvo `ajuste`, que lleva signo y no puede ser 0. Efecto: `abono` y `ajuste` suman al disponible; `reserva` pasa de disponible a reservado; `liberacion`, de reservado a disponible; `cargo` resta del reservado. Por eso CA-04 se verifica como `disponible = abonos + ajustes − reservas + liberaciones` y `reservado = reservas − liberaciones − cargos`. `abono` y `ajuste` exigen `nota` no vacía (CHECK).
- La FK `movimientos.pedido_id → pedidos` se crea en la migración de `pedidos` (T-040). `pedidos` tiene además CHECK de formato de `player_id` (RF-27), precios positivos y token no vacío; `codigo` se completa tras insertar (T-041).
- Índices: `pedidos(usuario_id, creado_en DESC)`, `pedidos(estado)`, `pedidos(referencia)`, `pedidos(player_id)`, `pedidos(codigo)`.

## 4. Flujo de recarga (RF-20 a RF-26)

### 4.1 Validar — `POST /recargas/validar`
1. Verifica sesión activa y formato del Player ID (RF-27).
2. Llama a `validar.php?player_id&paquete_id`.
3. Responde `{estado, nickname}`. Si `no_existe`, devuelve 422.

### 4.2 Confirmar — `POST /recargas`
Cuerpo: `{paquete_id, player_id, token_idempotencia, confirmar_sin_verificar?}`.

Antes de la Fase A (y sin bloqueos de BD) el backend vuelve a validar el ID con `validar.php` (RN-03): `no_existe` → 422 sin pedido; `ok` → el nickname se toma de esa respuesta (RF-26), nunca del cliente; `no_disponible` o fallo del validador → solo continúa si `confirmar_sin_verificar = true` (RF-20). Un reenvío con un token ya usado devuelve el pedido existente sin volver a validar.

**Fase A — reserva (transacción 1):**
1. Busca pedido por `(usuario_id, token_idempotencia)`; si existe, devuelve ese pedido.
2. `SELECT … FROM saldos WHERE usuario_id=… FOR UPDATE`.
3. Lee `precio_venta` y `precio_costo` actuales del paquete (activo y con `precio_venta` definido).
4. Si `saldo_disponible < precio_venta` → 422 sin crear pedido.
5. `saldo_disponible -= pv`, `saldo_reservado += pv`; inserta movimiento `reserva`.
6. Inserta pedido en `PROCESANDO` con precios congelados; evento de estado.
7. Commit.

**Fase B — llamada al proveedor (fuera de la transacción de saldo):**
1. Adquiere candado global (`pg_advisory_lock`, conexión dedicada) y pasa por el limitador de tasa propio (ventana deslizante en `limitador.py`: 8 recargas/min, por debajo de las 10 del proveedor).
2. `GET saldo.php`: si `data.credito` < `precio_costo` → resultado FALLIDO ("sin disponibilidad del proveedor"), alerta al admin (RN-08).
3. `POST recargar.php`. Si `BUSY` → espera 3 s, reintenta una vez (RN-06).
4. Libera el candado.

**Fase C — resolución (transacción 2):** bloquea fila de `saldos` y actualiza pedido y saldo:

| Resultado | Pedido | Saldo | Movimiento |
|---|---|---|---|
| `success: true` | EXITOSO, `referencia` | `reservado -= pv` | `cargo` |
| Error con código de API (`PURCHASE_FAILED`, `INSUFFICIENT_CREDIT`, `BUSY` persistente, `MISSING_FIELD`, errores de cuenta) | FALLIDO, `error`, `error_code` | `reservado -= pv`, `disponible += pv` | `liberacion` |
| Timeout / respuesta ilegible / excepción de red tras enviar | PENDIENTE_VERIFICAR | Sin cambio (retenido) | — |

- Errores de cuenta (`INVALID_KEY`, `INACTIVE`, `API_DISABLED`, `MISSING_KEY`) generan además alerta crítica al admin y no se muestran literalmente al cliente (mensaje genérico: "Servicio no disponible").
- Error de conexión **antes** de enviar la petición (DNS, connect refused) puede tratarse como FALLIDO; cualquier fallo después del envío es PENDIENTE_VERIFICAR.
- `nickname` se toma del pedido (de `validar.php`), no de la respuesta de `recargar.php`.

### 4.2.1 Alertas al admin (RN-08, RN-11)
- `sin_credito`: `INSUFFICIENT_CREDIT` o crédito menor que el costo en la Fase B. `cuenta`: errores de cuenta. `credito_bajo`: el crédito informado por `saldo.php` (Fase B) o por `recargar.php` (`data.saldo`) queda por debajo de `config.alerta_credito_min`.
- Se registran tras resolver el pedido, en su propia transacción; si ya hay una activa del mismo tipo no se crea otra (`INSERT … ON CONFLICT DO NOTHING`).
- El admin las ve en el panel y las marca como atendidas (queda en auditoría).

### 4.3 Recuperación (RN-09)
Al iniciar la aplicación: pedidos en `PROCESANDO` → `PENDIENTE_VERIFICAR`, sin mover saldo ni reintentar. Con un solo worker, todo `PROCESANDO` al arrancar es huérfano (umbral de antigüedad 0, configurable). `CREADO` nunca queda guardado: la Fase A lo pasa a `PROCESANDO` en la misma transacción.

### 4.4 Resolución manual (RF-52)
`POST /admin/pedidos/{id}/resolver` con `{resultado: exitoso|fallido, referencia?, nota}`:
- exitoso → misma contabilidad que éxito;
- fallido → misma contabilidad que fallo.
Solo válido si el estado es `PENDIENTE_VERIFICAR`. Registra evento y auditoría.

### 4.5 Cliente VentasFF (`ventasff_client.py`)
- Único módulo que llama a VentasFF. `httpx.AsyncClient` con `Authorization: Bearer`, timeouts 15 s conexión / 30 s general / 90 s en `recargar.php`. El transporte es inyectable (pruebas con respx y con el simulador). La URL base sale de `VENTASFF_URL` (opcional; por defecto la real), para usar el simulador como servidor en desarrollo.
- El JSON se lee con `parse_float=Decimal`; los montos nunca pasan por float.
- Métodos: `saldo()`, `productos()`, `validar(player_id, paquete_id)`, `recargar(paquete_id, player_id)`; devuelven dataclasses con los campos de la sección 9 de la spec.
- Clasificación de resultados (T-021), sobre todo para `recargar`:

| Situación | Excepción / resultado | Consecuencia en Fase C |
|---|---|---|
| `success: true` con `data` válido | resultado | EXITOSO |
| `success: false` con `code` | `ErrorAPI(code, mensaje, http, retry_after)` | FALLIDO |
| Fallo antes de enviar (DNS, conexión rechazada, timeout de conexión) | `ErrorPrevioAlEnvio` | FALLIDO |
| Timeout de lectura/escritura, corte tras enviar, JSON ilegible, `success` ausente o `data` incompleto | `ResultadoIncierto` | PENDIENTE_VERIFICAR |

- `RATE_LIMITED`: se lanza `ErrorAPI` con `retry_after` (segundos) y el cliente no envía otra petición hasta que pase ese plazo (tope 60 s). No reintenta por su cuenta (RN-07).
- Logs: método, ruta, estado HTTP y duración; nunca cabeceras ni la API Key (RNF-05).

### 4.6 Transacciones y bloqueos (implementado en fase 5)
- **No confirman** (corren en la transacción de quien llama): `ledger.*`, `catalogo.fijar_precio_venta/activar/desactivar/sincronizar_catalogo`, `alertas.*`, `auth_service.crear_usuario`.
- **Confirman su propia transacción:** `recarga_service.crear_pedido` (Fase A), `resolver_pedido` (Fase C), `resolver_pendiente` (admin), `recuperacion.recuperar_pedidos_huerfanos`, `tareas.ejecutar_sincronizacion`; `procesar_pedido` = Fase B + Fase C + `registrar_alertas`.
- Orden de bloqueos: fila de `pedidos` y después fila de `saldos`. La Fase A no bloquea pedidos existentes.
- **Rutas (T-054):** `POST /recargas` ejecuta la Fase A en la petición; las fases B y C corren en una tarea `asyncio.create_task` guardada en `app.state.tareas_recarga`, que una desconexión del cliente no cancela. La ruta espera el resultado hasta 20 s (`asyncio.wait`, sin cancelar la tarea) y, si no termina, devuelve el pedido en `Procesando`; el cliente lo consulta en `/me/pedidos/{codigo}`. Al apagar, la app espera hasta 100 s a las tareas en curso; las que no terminen pasan a revisión al arrancar (RN-09). Respuestas: 201 pedido nuevo, 200 token ya usado (CA-02), 409 ID no verificado sin `confirmar_sin_verificar`, 422 rechazos sin pedido (formato, `no_existe`, paquete, token, saldo).
- **Límite general (RN-07):** las rutas usan un único `ClienteVentasFF` (`app.state.ventasff`) con `LimitadorTasa(50/min)` aplicado a toda petición en `_peticion`; comparte la pausa por `RATE_LIMITED`. Las recargas pasan además por su limitador de 8/min. La sincronización programada usa su propio cliente.

## 5. Precios (RF-10 a RF-14)

- `sincronizar_catalogo()`: GET `productos.php`, filtra `juego = free_fire`, upsert en `paquetes` actualizando solo `nombre`, `diamantes` y `precio_costo` (tomado de `precio`).
- Paquetes nuevos: se crean con `activo = false` y `precio_venta = NULL`.
- `precio_venta` nunca se modifica en la sincronización; el panel marca paquetes con `precio_venta <= precio_costo`.
- Paquetes que desaparecen del proveedor → `activo = false`.
- Evolución futura: cálculo por porcentaje (requiere cambio de spec).
- Programada con APScheduler 3.x (`AsyncIOScheduler`) todos los días a las 08:00 UTC, y botón en el admin. El resultado (fecha, contadores, paquetes bajo costo o error) se guarda en `config` con clave `catalogo_ultima_sincronizacion` y se registra en el log.
- Un solo worker de la aplicación ejecuta el scheduler (evitar duplicados con varios workers).

## 6. Endpoints

### Cliente
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/login` | Inicia sesión |
| POST | `/auth/logout` | Cierra sesión |
| POST | `/auth/cambiar-clave` | Cambio de contraseña (obligatorio en primer acceso) |
| GET | `/auth/sesion` | Usuario de la sesión, `debe_cambiar_clave` y token CSRF |
| GET | `/me/resumen` | Saldo disponible, gasto total, nº recargas |
| GET | `/me/fondos` | Saldo y abonos recibidos |
| GET | `/me/pedidos` | Historial con filtros (`estado`, `desde`, `hasta`, `player_id`, `codigo`) y paginación (`pagina`, `por_pagina` = 20, máx. 100) |
| GET | `/me/pedidos/{codigo}` | Detalle de un pedido propio |
| GET | `/paquetes` | Paquetes activos con `precio_venta` |
| POST | `/recargas/validar` | Valida Player ID |
| POST | `/recargas` | Crea recarga |

Las rutas `/me/*`, `/paquetes` y `/recargas*` son solo para clientes (un admin recibe 403: no tiene cuenta de saldo).

### Admin (`/admin/*`, rol admin)
| Método | Ruta | Descripción |
|---|---|---|
| GET/POST | `/admin/usuarios` | Listar / crear cliente (clave temporal) |
| POST | `/admin/usuarios/{id}/bloquear` · `/desbloquear` · `/reset-clave` | Gestión |
| POST | `/admin/saldos/{usuario_id}/abono` · `/ajuste` | Saldos con nota |
| GET | `/admin/pedidos` | Filtros completos (RF-50) |
| GET | `/admin/pedidos/{id}` | Detalle con costo, ganancia e historial (`id` numérico o código `FF-…`) |
| POST | `/admin/pedidos/{id}/resolver` | Resolver `PENDIENTE_VERIFICAR` |
| GET | `/admin/panel` | Saldo VentasFF vs suma de saldos, alertas, ganancia |
| GET/PUT | `/admin/config` | Alertas (crédito bajo) |
| GET | `/admin/alertas` | Alertas activas (RN-11) |
| POST | `/admin/alertas/{id}/atender` | Marca una alerta como atendida |
| GET | `/admin/paquetes` | Todos los paquetes con costo, marcador `bajo_costo` y última sincronización |
| PUT | `/admin/paquetes/{id}` | `precio_venta`, `activo` |
| POST | `/admin/catalogo/sincronizar` | Sincroniza ahora |
| GET | `/admin/auditoria` | Registro de acciones (filtros `accion`, `usuario_id`, `desde`, `hasta`; paginado) |

Esquemas de respuesta del cliente: modelos Pydantic dedicados que **no declaran** `precio_costo` (CA-03). Los montos se serializan como texto con 2 decimales (`"0.91"`) y las respuestas de montos incluyen `moneda: "USD"` (RF-36). Las fechas van en ISO 8601 UTC (RNF-09: el frontend las muestra en la zona del usuario). Errores: `{"detail": "mensaje en español"}`.

### 6.1 Páginas web (Q-05, CHG-008)

Paquete `app/web/`: rutas HTML (sin `include_in_schema`) que llaman a las funciones de las rutas JSON de la sección 6 y renderizan su resultado con Jinja2 (`app/templates/`). Así la web reutiliza validaciones, transacciones y auditoría, y las plantillas del cliente solo reciben esquemas de cliente, que no tienen `precio_costo` (CA-03).

| Ruta | Pantalla | Usa |
|---|---|---|
| `/` | Redirige según rol (`/inicio` o `/gestion`) o a `/entrar` | — |
| `/entrar` (GET/POST) | Login | `/auth/login` |
| `/clave` (GET/POST) | Cambio de contraseña (obligatorio si `debe_cambiar_clave`) | `/auth/cambiar-clave` |
| `/salir` (POST) | Cierra sesión | `/auth/logout` |
| `/inicio` | Inicio del cliente (RF-33) | `/me/resumen` |
| `/recargar`, `/recargar/validar`, `/recargar/confirmar` | Player ID → nickname → paquete → confirmación (RF-20, RF-21, RF-25) | `/paquetes`, `/recargas/validar`, `/recargas` |
| `/historial`, `/historial/{codigo}` | Historial con filtros y detalle (RF-31, RF-32) | `/me/pedidos` |
| `/fondos` | Fondos (RF-34) | `/me/fondos` |
| `/gestion` | Panel: crédito vs saldos, pendientes, ganancia, alertas (RF-53, RN-10, RN-11) | `/admin/panel`, `/admin/alertas/{id}/atender` |
| `/gestion/usuarios`, `/gestion/usuarios/{id}` | Usuarios, abonos y ajustes (RF-03, RF-40, RF-41) | `/admin/usuarios*`, `/admin/saldos/*` |
| `/gestion/pedidos`, `/gestion/pedidos/{id}` | Pedidos con filtros, detalle y resolución (RF-50 a RF-52, RF-54) | `/admin/pedidos*` |
| `/gestion/paquetes` | Catálogo: precio, activación, sincronizar (RF-12, RF-14) | `/admin/paquetes`, `/admin/catalogo/sincronizar` |
| `/gestion/config` | Umbral de crédito bajo (RN-11) | `/admin/config` |
| `/gestion/auditoria` | Registro de acciones (RF-55) | `/admin/auditoria` |

- **Sesión:** las páginas usan las mismas dependencias que la API; sin sesión redirigen a `/entrar`, con `debe_cambiar_clave` a `/clave` y con el rol equivocado al inicio del rol. A una petición HTMX la redirección se le indica con la cabecera `HX-Redirect`.
- **Formularios:** se envían con HTMX (`hx-post`), que agrega `X-CSRF-Token` desde `hx-headers` del `<body>`. La respuesta es un fragmento HTML; los errores 4xx (y el 502 de "sincronizar ahora") también traen un fragmento con el mensaje y HTMX los muestra (`htmx-config` con `responseHandling`). Si el formulario reemplaza otra parte de la página (resolver un pedido, una fila del catálogo), el error se muestra en su zona de mensajes con `HX-Retarget`.
- **Recarga:** `/recargar/validar` muestra nickname, paquete y precio y genera el `token_idempotencia` (UUID) en el fragmento de confirmación. El botón se deshabilita tras el primer clic (`hx-disabled-elt`); un reenvío con el mismo token devuelve el mismo pedido (CA-02). Si la API pide confirmación (`no_disponible`/validador caído), el fragmento exige marcar la casilla de continuar sin verificar. Un pedido en `Procesando` se consulta cada 3 s hasta su estado final.
- **Fechas (RNF-09):** se renderizan como `<time datetime="ISO UTC">` y `app/static/app.js` las muestra en la zona del navegador. Los filtros de fecha usan `<input type="date">` y envían el desfase del navegador (`tz`, minutos); la ruta convierte el día local a UTC (`desde` inclusivo, `hasta` hasta el final de ese día).
- **Montos:** filtro `usd` → `"0.75 USD"` (RF-36).

## 7. Seguridad (RNF-01 a RNF-06)

- Configuración por variables de entorno: `VENTASFF_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE`; opcional `VENTASFF_URL`.
- Sesión (RF-06, CHG-007): token aleatorio (`secrets.token_urlsafe(32)`) en la cookie `sesion`, `HttpOnly; SameSite=Lax; Path=/`, `Secure` según `COOKIE_SECURE`. En la tabla `sesiones` se guarda solo su SHA-256. Cada petición busca la sesión junto con el usuario: si no existe, venció (8 h desde `ultima_actividad`) o el usuario está inactivo → 401 (y la fila se borra). `ultima_actividad` se actualiza como mucho una vez por minuto. Logout borra la fila; bloquear, resetear o cambiar la clave borran todas las del usuario (al cambiarla, el usuario recibe una sesión nueva). El login borra además las sesiones vencidas.
- CSRF: cada sesión tiene un token propio que el login y `GET /auth/sesion` devuelven; las peticiones `POST`/`PUT`/`PATCH`/`DELETE` con sesión deben enviarlo en la cabecera `X-CSRF-Token` (comparación en tiempo constante) o reciben 403. Las páginas web lo ponen en `<body hx-headers=…>`, de modo que HTMX lo envía en cada formulario (sec. 6.1).
- Limitador de login (RF-05) en memoria (un solo worker): ventana deslizante de 15 min por par usuario+IP (5 fallos) y por IP (20 fallos); superado el tope responde 429 durante 15 min con el mismo mensaje genérico. Un login correcto limpia el contador del par.
- Usuario (RF-07): `^[a-z0-9._-]{3,30}$` tras pasar a minúsculas; el login compara en minúsculas. Contraseña nueva (RF-08): 8 a 128 caracteres y distinta de la actual.
- Dependencias de FastAPI (equivalen al middleware): `usuario_en_sesion` (cualquier sesión válida; solo la usan `/auth/logout`, `/auth/sesion` y `/auth/cambiar-clave`), `usuario_actual` (además rechaza con 403 `debe_cambiar_clave`, RF-02) y `require_admin` (además rol admin) para `/admin/*`.
- Auditoría (RF-55): cada acción admin que cambia datos inserta una fila en `auditoria` en la misma transacción, con la IP del cliente.
- Log estructurado con enmascarado de secretos.
- Docker: sin dominio, `app` publica un puerto (ej. 8000). Con dominio, solo Caddy expone 80/443.
- La seguridad del servidor PostgreSQL (firewall, TLS, control de acceso) se gestiona fuera del repositorio. La app usa un usuario dedicado.

## 8. Base de datos y Docker Compose

### Base de datos (RNF-07, RNF-10)
- PostgreSQL corre en el VPS, fuera del repositorio y del Compose. El proyecto solo conoce la cadena de conexión.
- `DATABASE_URL=postgresql+psycopg://USUARIO:CLAVE@HOST:5432/NOMBRE_BD` (solo en `.env`, nunca en el repo).
- `TEST_DATABASE_URL`: mismo formato. Las pruebas crean y eliminan el esquema `test`; no tocan el esquema de desarrollo.
- Entornos: pruebas/desarrollo usan la base de prueba del VPS. Producción usa otra base en el mismo VPS; el cambio es solo el valor de `DATABASE_URL`.
- El usuario de conexión debe poder crear tablas (migraciones con Alembic). Todo cambio de esquema pasa por Alembic.
- Al arrancar, la app verifica la conexión y falla con un error claro si no conecta.

### Docker Compose (servicios)
- `app`: FastAPI (uvicorn), lee `.env`, se conecta a la BD externa. Publica un puerto (ej. 8000).
- No hay servicio `db`.
- Red: `app` se une a la red Docker externa `ffmovil_net` (`external: true`), que crea el dueño y comparte con el Compose de PostgreSQL. En el VPS, `DATABASE_URL` usa como host el nombre del contenedor de PostgreSQL (ej. `@postgres:5432`); PostgreSQL no publica puertos a internet.
- Desarrollo local: acceso a la BD del VPS por túnel SSH (`localhost:5433`); solo cambia el valor de `DATABASE_URL`.
- `caddy` (diferido hasta tener dominio): único con puertos publicados, reverse proxy a `app`, volúmenes para certificados.
- Acceso actual: `http://localhost:8000` o `http://IP_DEL_VPS:8000`.

## 9. Estrategia de pruebas

- **Simulador de VentasFF** (`tests/fake_ventasff.py`): reproduce `ok`, `PURCHASE_FAILED`, `BUSY`, `INSUFFICIENT_CREDIT`, timeout, respuesta ilegible, `nickname: null`.
- **Unitarias:** validación de precios y de Player ID, transiciones de estado.
- **Integración (BD real, esquema `test`):** flujo de recarga completo por cada resultado; concurrencia (CA-01); idempotencia (CA-02); invariante contable (CA-04).
- **Seguridad:** CA-03 (ningún payload de cliente contiene `precio_costo`), acceso a `/admin/*` como cliente → 403.
- **Prueba real controlada** al final: 1 recarga del paquete más barato con un ID propio.

## 10. Fases

1. **Fundación:** repositorio, Docker, BD, migraciones, configuración.
2. **Núcleo contable:** usuarios, saldos, libro de movimientos.
3. **Cliente VentasFF + simulador.**
4. **Catálogo y precios.**
5. **Recarga transaccional** (flujo A/B/C, estados, recuperación).
6. **API cliente y admin.**
7. **Frontend.**
8. **Endurecimiento y pruebas.**
9. **Despliegue en VPS** (Caddy y HTTPS cuando haya dominio).

Detalle en `sdd/tasks.md`.
