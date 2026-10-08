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
- **BD desde el equipo local:** túnel SSH `ssh -N -L 5433:localhost:5432 ffmovil`; el `.env` local apunta a `localhost:5433`. Sin túnel fallan Alembic, la app y las pruebas de BD. El túnel se abre al iniciar la sesión y se cierra al terminar.
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

### Piezas ya construidas

- `app/config.py`: configuración por entorno (`SecretStr`); falla con mensaje claro sin exponer valores. `TEST_DATABASE_URL` es opcional para la app.
- `app/db.py`: `crear_motor(url, esquema=None)`, `verificar_conexion()` (la app no arranca si la BD no responde).
- `app/main.py`: `lifespan` con verificación de BD; `GET /health` (200 / 503 sin detalles).
- `app/models/base.py`: `Base` con convención de nombres de restricciones.
- `migrations/env.py`: toma la URL de la configuración (nunca de `alembic.ini`); acepta `config.attributes["url"]` y `["esquema"]` para migrar en el esquema `test`.
- `tests/conftest.py`: fixtures `url_bd_test` (sesión: crea `test`, migra, elimina al final), `motor_bd` y `sesion_bd` (search_path = `test`).

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
