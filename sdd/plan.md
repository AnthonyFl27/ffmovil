# Plan técnico

- **Spec de referencia:** `sdd/spec.md` v0.5.0
- **Regla:** este plan implementa la spec. Si el plan contradice la spec, gana la spec.

---

## 1. Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x async con psycopg 3, Alembic |
| Dependencias | uv (`pyproject.toml` + `uv.lock`) |
| Base de datos | PostgreSQL 18, externo (servidor propio en el VPS), acceso solo por `DATABASE_URL` |
| Frontend (propuesta Q-05) | Jinja2 + HTMX servidos por FastAPI |
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
│   ├── services/
│   │   ├── ventasff_client.py # único módulo que llama a VentasFF
│   │   ├── recarga_service.py # flujo transaccional
│   │   ├── ledger.py          # movimientos y saldos
│   │   ├── catalogo.py        # sincronización y precios
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

config(clave TEXT PK, valor TEXT)   -- alerta_credito_min, ...

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
| GET | `/me/resumen` | Saldo disponible, gasto total, nº recargas |
| GET | `/me/fondos` | Saldo y abonos recibidos |
| GET | `/me/pedidos` | Historial con filtros (`estado`, `desde`, `hasta`, `player_id`, `codigo`) y paginación |
| GET | `/me/pedidos/{codigo}` | Detalle de un pedido propio |
| GET | `/paquetes` | Paquetes activos con `precio_venta` |
| POST | `/recargas/validar` | Valida Player ID |
| POST | `/recargas` | Crea recarga |

### Admin (`/admin/*`, rol admin)
| Método | Ruta | Descripción |
|---|---|---|
| GET/POST | `/admin/usuarios` | Listar / crear (clave temporal) |
| POST | `/admin/usuarios/{id}/bloquear` · `/desbloquear` · `/reset-clave` | Gestión |
| POST | `/admin/saldos/{usuario_id}/abono` · `/ajuste` | Saldos con nota |
| GET | `/admin/pedidos` | Filtros completos (RF-50) |
| GET | `/admin/pedidos/{id}` | Detalle con costo y ganancia |
| POST | `/admin/pedidos/{id}/resolver` | Resolver `PENDIENTE_VERIFICAR` |
| GET | `/admin/panel` | Saldo VentasFF vs suma de saldos, alertas, ganancia |
| GET/PUT | `/admin/config` | Alertas (crédito bajo) |
| PUT | `/admin/paquetes/{id}` | `precio_venta`, `activo` |
| POST | `/admin/catalogo/sincronizar` | Sincroniza ahora |
| GET | `/admin/auditoria` | Registro de acciones |

Esquemas de respuesta del cliente: modelos Pydantic dedicados que **no declaran** `precio_costo` (CA-03).

## 7. Seguridad (RNF-01 a RNF-06)

- Configuración por variables de entorno: `VENTASFF_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE`; opcional `VENTASFF_URL`.
- Sesión con cookie firmada `HttpOnly; SameSite=Lax`; `Secure` según `COOKIE_SECURE` (`true` en producción con HTTPS); token CSRF en formularios.
- Limitador de login (por usuario e IP).
- Middleware que bloquea a usuarios con `debe_cambiar_clave` salvo en `/auth/cambiar-clave`.
- Dependencia `require_admin` para `/admin/*`.
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
