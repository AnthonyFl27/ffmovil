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

### CHG-007 · 2026-10-08 · Sesiones, credenciales y precisiones de la API del cliente
- **Origen:** preguntas abiertas resueltas (Q-03, Q-04) y vacíos detectados antes de la fase 6
- **Spec:** RF-03, RF-05, RF-33, RF-34 modificados; RF-06, RF-07, RF-08, RF-36 añadidos; Q-03 y Q-04 resueltas
- **Plan:** modelo `sesiones`; sec. 6 (`/auth/sesion`, `/admin/alertas`, paginación, formato de montos); sec. 7 (sesión en BD, CSRF por cabecera, limitador de login, reglas de usuario y contraseña, dependencias)
- **Tareas:** T-050, T-051, T-052, T-055, T-058 modificadas
- **Versión spec:** 0.6.0 → 0.7.0
- **Motivo:** la fase 6 necesitaba la expiración de sesión, los topes del limitador de login, las reglas de usuario y contraseña, qué cuenta en el resumen y qué muestra Fondos.

### CHG-008 · 2026-10-08 · Frontend con Jinja2 + HTMX
- **Origen:** pregunta abierta resuelta (Q-05)
- **Spec:** Q-05 resuelta; sin cambios en requisitos
- **Plan:** stack (Jinja2 + HTMX + Pico.css servidos desde `app/static`); sec. 6.1 nueva (páginas web); sec. 7 (CSRF de los formularios por cabecera con `hx-headers`)
- **Tareas:** sin cambios (T-071 a T-077 siguen este diseño)
- **Versión spec:** 0.7.0 → 0.7.1
- **Motivo:** el dueño elige páginas renderizadas por FastAPI que reutilizan las rutas y esquemas ya construidos: sin paso de build ni otro contenedor.

### CHG-009 · 2026-10-08 · Adaptación a móvil
- **Origen:** decisión de negocio (la plataforma se usará sobre todo desde celular, el admin desde celular y escritorio) y hallazgo de la auditoría en navegador móvil
- **Spec:** RNF-12 y CA-07 añadidos
- **Plan:** sec. 6.2 nueva (CSS mobile-first, menú plegable, tarjetas, filtros plegables, áreas táctiles, prueba con Playwright); sec. 9 (prueba móvil)
- **Tareas:** nuevas T-100 a T-105 (tareas emergentes)
- **Versión spec:** 0.7.1 → 0.8.0
- **Motivo:** la web desbordaba el viewport en todas las pantallas a 360 y 390 px, ocultaba el estado en el historial y tenía controles táctiles de 20 a 34 px. Decisiones del dueño: admin adaptado por completo, listados como tarjetas, mínimo 360 px, Playwright solo como dependencia de desarrollo.

### CHG-010 · 2026-10-08 · Recarga en tres pasos
- **Origen:** decisión de negocio (revisión del flujo en celular por el dueño)
- **Spec:** RF-20 y RF-21 modificados
- **Plan:** sec. 6.1 (rutas y fragmentos de la pantalla Recargar)
- **Tareas:** nueva T-106 (tareas emergentes)
- **Versión spec:** 0.8.0 → 0.9.0
- **Motivo:** una pantalla más limpia: primero solo el Player ID; tras verificarlo, una tarjeta con el jugador y los paquetes; al tocar un paquete, el resumen y la confirmación. `validar.php` exige `paquete_id`, por eso el primer paso usa el paquete activo más barato; al confirmar el servidor vuelve a validar con el paquete elegido (RN-03). VentasFF no entrega avatar: la tarjeta muestra la inicial del nickname. Decisiones del dueño: el resumen aparece al tocar el paquete, sin botón intermedio.

### CHG-011 · 2026-10-09 · Abonos por encima del crédito de VentasFF
- **Origen:** decisión de negocio (el dueño adelanta saldo a clientes confiables)
- **Spec:** RN-10 modificada (el abono puede superar el crédito en VentasFF, sin tope); RF-53 modificado (saldo por cubrir informativo)
- **Plan:** sec. 6.1 (panel; la configuración del umbral vive en Auditoría)
- **Tareas:** nueva T-107 (tareas emergentes)
- **Versión spec:** 0.9.0 → 0.10.0
- **Motivo:** un cliente puede pagar por adelantado 1000 USD aunque el crédito en VentasFF sea menor; consume a medida que el dueño recarga crédito. RN-10 antes lo prohibía y el panel lo mostraba como error. Decisiones del dueño: sin tope de adelanto, sin alerta aparte por saldo por cubrir. Cuando falta crédito para una recarga siguen RF-23 y RN-08 (pedido `FALLIDO`, reserva liberada, alerta). Queda fuera por ahora el mensaje al cliente cuando VentasFF no tiene crédito.

### CHG-012 · 2026-10-09 · Últimas recargas en el inicio del cliente
- **Origen:** decisión de negocio (mejora de la pantalla de inicio propuesta en la revisión visual)
- **Spec:** RF-33 modificado
- **Plan:** sec. 6.1 (ruta `/inicio`)
- **Tareas:** nueva T-108 (tareas emergentes)
- **Versión spec:** 0.10.0 → 0.11.0
- **Motivo:** el inicio quedaba con media pantalla vacía y el cliente (revendedor con muchas recargas a distintos jugadores) quiere ver lo último que hizo sin entrar al Historial. Decisiones del dueño: 5 recargas, de todos los estados (para que una recarga fallida o en revisión se vea de inmediato) y con el nickname del jugador.

### CHG-013 · 2026-10-09 · Inicio del cliente sin enlace "Ver todo"
- **Origen:** decisión de negocio (revisión visual del dueño)
- **Spec:** RF-33 modificado (se retira el enlace "Ver todo"; el botón Historial basta)
- **Plan:** sin cambios
- **Tareas:** T-108 ajustada (criterio sin "Ver todo")
- **Versión spec:** 0.11.0 → 0.12.0
- **Motivo:** las últimas recargas del inicio son solo una referencia rápida; el botón Historial ya lleva al listado completo.

### CHG-014 · 2026-10-09 · Historial de movimientos de saldo en la ficha del cliente
- **Origen:** decisión de negocio (el dueño quiere ver, al entrar a un usuario, todo el historial de sus movimientos)
- **Spec:** RF-43 añadido (RF-34, Fondos del cliente, sin cambios)
- **Plan:** sec. 6 (endpoint `GET /admin/usuarios/{id}/movimientos`) y 6.1 (ficha `/gestion/usuarios/{id}`)
- **Tareas:** nueva T-109 (tareas emergentes)
- **Versión spec:** 0.12.0 → 0.13.0
- **Motivo:** el admin solo veía el saldo actual de un cliente. Decisiones del dueño: se muestran todos los tipos de movimiento (así el historial cuadra con CA-04) y el cliente conserva su pantalla Fondos con abonos y ajustes.

### CHG-015 · 2026-10-09 · El historial del admin solo muestra abonos y ajustes
- **Origen:** decisión de negocio (revisión del dueño: el historial con reservas y cargos de recargas confundía y no coincidía con lo esperado)
- **Spec:** RF-43 modificado (solo abonos y ajustes; columnas fecha, tipo, monto y nota; sin pedido, autor ni saldos resultantes)
- **Plan:** sec. 6 (endpoint `/admin/usuarios/{id}/movimientos`)
- **Tareas:** T-109 ajustada (criterio y pruebas)
- **Versión spec:** 0.13.0 → 0.14.0
- **Motivo:** corrige la decisión de CHG-014 (todos los tipos): el dueño quiere la misma vista que el cliente tiene en Fondos, con abonos y ajustes. Las reservas, liberaciones y cargos se consultan en el detalle de cada pedido.

## Decisiones resueltas

| Q | Decisión | Fecha | CHG |
|---|---|---|---|
| Q-05 | Frontend: Jinja2 + HTMX servidos por FastAPI; Pico.css como estilo | 2026-10-08 | CHG-008 |
| Q-03 | Moneda mostrada al cliente: USD con 2 decimales (RF-36) | 2026-10-08 | CHG-007 |
| Q-04 | Sesión: expira tras 8 h sin actividad, guardada en BD (RF-06) | 2026-10-08 | CHG-007 |
| Q-06 | Umbral de crédito bajo en VentasFF: 10 USD, editable por el admin en `config.alerta_credito_min` | 2026-10-08 | CHG-006 |
| Q-01 | Retirada: no hay margen global; precio de venta manual por paquete | 2026-10-07 | CHG-002 |
| Q-02 | Retirada: sin cálculo, no aplica redondeo | 2026-10-07 | CHG-002 |
