# AGENTS.md — Contexto y reglas para el LLM

## Proyecto

Web de recargas de diamantes de Free Fire con cuentas prepago. Backend FastAPI en Docker; PostgreSQL externo (servidor propio en el VPS) accedido solo por `DATABASE_URL`. API y web en el mismo repositorio. Sin dominio por ahora: la app corre por HTTP y Caddy queda diferido. Consume la API de VentasFF (`https://ventasff.com/api/reseller`). Repositorio público: nunca incluir secretos, precios de costo reales, datos ni respaldos.

## Documentos (orden de autoridad)

1. `sdd/spec.md` — **qué** y **por qué**. Fuente de verdad.
2. `sdd/plan.md` — **cómo** (arquitectura, datos, flujos).
3. `sdd/tasks.md` — **pasos** de implementación.
4. `sdd/changelog.md` — historial de cambios de la spec.

Si hay conflicto: spec > plan > tasks > código.

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

## Convenciones

- Código y comentarios técnicos en inglés o español, de forma consistente dentro del proyecto (definir y anotar aquí).
- Mensajes al usuario final en español.
- Commits: `T-XXX <resumen> [RF-/RN-/RNF-...]`.
- Formato y lint: `ruff`.

## Qué no hacer

- No ampliar el alcance (p. ej. Mobile Legends) sin un cambio de spec aprobado.
- No agregar Caddy, dominio ni HTTPS hasta que se apruebe el cambio de spec correspondiente.
- No inventar campos o endpoints de VentasFF fuera de la sección 9 de la spec.
- No modificar migraciones ya aplicadas; crear una nueva.
- No subir `.env`, volcados de BD ni datos reales.
