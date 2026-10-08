# Registro de cambios de la spec

Cada cambio a `spec.md` se registra aquí antes (o junto con) de modificar `plan.md`, `tasks.md` o el código.

## Formato de entrada

```
### CHG-XXX · AAAA-MM-DD · <título corto>
- **Origen:** hallazgo en implementación | decisión de negocio | error de API | pregunta abierta resuelta (Q-XX)
- **Spec:** secciones/IDs modificados (ej. RF-24 modificado, RN-11 añadido)
- **Plan:** secciones afectadas
- **Tareas:** nuevas (T-1xx), modificadas, canceladas
- **Versión spec:** 0.1.0 → 0.2.0
- **Motivo:** por qué
```

## Versionado de la spec

- **Patch (0.1.x):** correcciones de redacción sin cambio de comportamiento.
- **Minor (0.x.0):** requisitos añadidos o modificados.
- **Major (x.0.0):** cambio de alcance (ej. añadir Mobile Legends).

## Entradas

### CHG-001 · Versión inicial
- **Origen:** decisión de negocio
- **Spec:** creación de `spec.md` v0.1.0
- **Plan:** creación de `plan.md`
- **Tareas:** creación de `tasks.md` (T-001 a T-094)
- **Versión spec:** — → 0.1.0
- **Motivo:** punto de partida del proyecto.

### CHG-002 · 2026-10-07 · Se retira el margen automático
- **Origen:** decisión de negocio
- **Spec:** RF-10, RF-11, RF-12, RF-14 modificados; glosario y fuera de alcance actualizados; Q-01 y Q-02 retiradas
- **Plan:** modelo `paquetes` (sin `precio_manual`, `precio_venta` nullable, CHECK de activación), sección 5, endpoints admin, pruebas
- **Tareas:** T-031, T-032, T-059 modificadas
- **Versión spec:** 0.1.0 → 0.2.0
- **Motivo:** el margen se explica al cliente y no se calcula en el sistema; el admin fija `precio_venta` por paquete. El porcentaje por paquete queda como función futura.

### CHG-003 · 2026-10-07 · PostgreSQL externo en el VPS
- **Origen:** decisión de negocio
- **Spec:** RNF-07 modificado (BD externa, solo `DATABASE_URL`); RNF-10 añadido (esquema `test` para pruebas)
- **Plan:** stack, sección 7 (variables y seguridad), sección 8 (BD externa; Compose sin `db`), pruebas de integración
- **Tareas:** T-002, T-003, T-005 modificadas; T-007 añadida
- **Versión spec:** 0.2.0 → 0.3.0
- **Motivo:** el dueño despliega y asegura PostgreSQL en el VPS; el LLM solo necesita la cadena de conexión. Producción usará otra base en el mismo VPS.

### CHG-004 · 2026-10-07 · Sin dominio por ahora; carpeta `sdd/`
- **Origen:** decisión de negocio
- **Spec:** RNF-03 modificado (HTTPS y `Secure` diferidos); RNF-11 añadido (HTTP sin dominio, `COOKIE_SECURE`); dominio y HTTPS agregados a fuera de alcance
- **Plan:** stack, estructura (monorepo; `Caddyfile` diferido), seguridad (cookie, puertos), sección 8 (Compose solo con `app`), fase 9
- **Tareas:** T-002, T-003, T-050 modificadas; T-090 bloqueada hasta tener dominio
- **Otros:** la carpeta `specs/` pasa a llamarse `sdd/`; API y web viven en el mismo repositorio
- **Versión spec:** 0.3.0 → 0.4.0
- **Motivo:** el dominio se añadirá más adelante; hasta entonces solo hay pruebas, sin clientes reales.

### CHG-005 · 2026-10-08 · Formato real de respuestas de VentasFF
- **Origen:** hallazgo en implementación (documentación del proveedor usada en la primera recarga real, 2026-10-05)
- **Spec:** sección 9 ampliada: envoltura `success`/`data`, campos de `saldo.php`, `productos.php`, `validar.php` y `recargar.php`, estado HTTP por código de error, `Retry-After` en `RATE_LIMITED`, montos leídos como decimales
- **Plan:** sec. 4.2 (Fase B compara `data.credito`), sec. 5 (`precio_costo` desde `precio`), sec. 4.5 nueva (diseño del cliente)
- **Tareas:** sin cambios; T-020 y T-023 siguen este contrato
- **Versión spec:** 0.4.0 → 0.5.0
- **Motivo:** la sección 9 no definía los campos de respuesta; el cliente y el simulador no deben inventarlos. No se incorporan los precios reales (RNF-06), `dato_extra` en la recarga (Mobile Legends, fuera de alcance) ni el reintento como formulario ante `MISSING_FIELD`.

### CHG-006 · 2026-10-08 · Alertas al admin y umbral de crédito bajo
- **Origen:** pregunta abierta resuelta (Q-06) y vacío detectado en T-049 (no había dónde guardar las alertas)
- **Spec:** RN-11 añadido; Q-06 resuelta
- **Plan:** modelo `alertas` y valor inicial de `alerta_credito_min`; sec. 4.2.1 nueva
- **Tareas:** T-049 modificada
- **Versión spec:** 0.5.0 → 0.6.0
- **Motivo:** RN-08 pide una alerta visible en el panel; el umbral de crédito bajo lo fija el dueño en 10 USD.

## Decisiones resueltas

| Q | Decisión | Fecha | CHG |
|---|---|---|---|
| Q-06 | Umbral de crédito bajo en VentasFF: 10 USD, editable por el admin en `config.alerta_credito_min` | 2026-10-08 | CHG-006 |
| Q-01 | Retirada: no hay margen global; precio de venta manual por paquete | 2026-10-07 | CHG-002 |
| Q-02 | Retirada: sin cálculo, no aplica redondeo | 2026-10-07 | CHG-002 |
