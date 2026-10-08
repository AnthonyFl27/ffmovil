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
uv run ruff check . && uv run ruff format --check .
uv run alembic upgrade head        # migra la BD de DATABASE_URL
uv run alembic revision -m "..."   # nueva migración (luego editarla a mano)
uv run uvicorn app.main:app --reload
```

### Piezas ya construidas (fases 1 a 6, spec v0.7.0)

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
- **Esquemas:** los de cliente van en `app/schemas/` (cualquier módulo que no empiece por `admin`) y una prueba falla si declaran algo con "costo"; los de admin, en `app/schemas/admin*.py`. Montos con el tipo `Monto` (texto con 2 decimales) y `moneda: "USD"` (RF-36).

### Pruebas: cómo escribirlas

- Simulador: `tests/fake_ventasff.py` → `SimuladorVentasFF(escenario_recarga=…, escenario_validar=…, credito=…, busy_restantes=…)`; cliente con `ClienteVentasFF(sim.api_key, "http://simulador/api/reseller", transport=sim.transporte())`. `sim.recargas` dice si el proveedor cobró.
- API: fixture `api` (fábrica de `httpx.AsyncClient` contra la app; `api(ip)` fija la IP; un tarro de cookies por cliente) y fixture `simulador` (el VentasFF de la app en la prueba). `tests/utilidades_api.py`: `crear_usuario_con_clave` (confirma; clientes con saldo en cero) e `iniciar_sesion` (deja la cabecera CSRF en el cliente). Los pedidos creados con `crear_pedido` no tienen `codigo`: asignar `codigo_pedido(pedido.id)` si la prueba lo usa. Usar precios ficticios (0.50/0.75), no 0.81.
- El esquema `test` se crea **una vez por sesión** de pytest y lo comparten todas las pruebas: usar ids/nombres únicos (`tests/utilidades.py`: `crear_usuario`, `crear_paquete`, `crear_pedido`; fixtures `cuenta`, `admin_id`), aserciones solo sobre lo propio y `rollback` cuando no haga falta persistir. Releer con `execution_options(populate_existing=True)`; tras un `rollback` no acceder a atributos de objetos ORM (expiran → `MissingGreenlet`).
- Motor y event loop son de alcance sesión. El enlace al VPS es lento (~0.5 s por consulta): minimizar ida y vuelta. Suite completa ≈ 12 min (529 pruebas al cerrar la fase 6).
- Dos procesos de pytest con BD a la vez se pisan (cada sesión recrea `test`): no correr pruebas de BD en paralelo.

### Forma de trabajo acordada con el usuario

- Al terminar cada tarea: marcar `[x]`, commit y **push** a `origin/main` (repositorio público: revisar que no haya secretos antes). Avisar al usuario al terminar cada fase.
- El LLM principal orquesta y delega tareas básicas y acotadas a subagentes Haiku (simuladores, utilidades puras, servicios con contrato exacto, tablas de pruebas). La lógica contable, transaccional y de clasificación la hace el principal. A cada subagente: lista cerrada de archivos, sin git, sin leer `.env`, sin suite completa; revisar e integrar antes del commit.

### Pendientes y decisiones abiertas (al cerrar la fase 6)

- Siguiente: **Fase 7** (T-070…). Antes: resolver Q-05 (Jinja2 + HTMX propuesto o SPA). Los formularios deben enviar el token CSRF (campo oculto o cabecera) y mostrar fechas en la zona del usuario (RNF-09).
- Consultados al usuario y sin respuesta: (1) las pruebas antiguas usan 0.81, que coincide con un costo real (RNF-06), ¿pasar a valores ficticios?; (2) si `productos.php` llega vacío, la sincronización desactiva todo el catálogo, ¿proteger con un cambio de spec?
- Un fallo inesperado (excepción) en la tarea de fases B/C deja el pedido en `PROCESANDO` hasta el siguiente arranque (RN-09); se registra en el log.
- Producción: usuario de BD dedicado con clave fuerte; rotar la API Key de VentasFF que se compartió en un chat; `--workers 1` (limitadores de login y de VentasFF en memoria).

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
