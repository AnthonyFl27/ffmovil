# Especificación: Plataforma de recargas Free Fire (prepago)

- **Versión:** 0.7.0
- **Estado:** Borrador aprobado para iniciar desarrollo
- **Fuente de verdad:** este archivo. El código y el plan se derivan de aquí.

---

## 1. Objetivo

Web de recargas de diamantes de Free Fire para clientes revendedores con cuentas prepago. Cada cliente tiene un saldo interno que se descuenta por recarga. Las recargas se ejecutan a través de la API de VentasFF, usando el crédito general del dueño de la plataforma.

## 2. Alcance

**Dentro (v1):**
- Juego: solo Free Fire (`juego = free_fire`).
- Autenticación con usuario y contraseña temporal.
- Catálogo, recarga, historial y fondos del cliente.
- Panel admin: usuarios, abonos manuales, pedidos, configuración, ganancia propia.

**Fuera (v1):**
- Mobile Legends (requiere Zone ID; sin probar en VentasFF).
- Pasarela de pago (el abono es manual).
- Cálculo de ganancia del cliente final.
- Registro público de usuarios.
- Reintentos automáticos de pedidos en `PENDIENTE_VERIFICAR`.
- Cálculo automático de margen o porcentaje (posible función futura).
- Dominio y HTTPS (se añaden antes de usar clientes reales; ver RNF-11).

## 3. Actores

| Actor | Descripción |
|---|---|
| Cliente | Revendedor. Usa su saldo prepago para recargar. |
| Admin | Dueño de la plataforma. Gestiona usuarios, saldos y pedidos. |
| VentasFF | Proveedor externo (API REST). Solo el backend lo consume. |

## 4. Glosario

- **Precio de costo:** precio reseller de VentasFF (`productos.php`).
- **Precio de venta:** precio al que se vende al cliente. Lo define el admin por paquete.
- **Saldo disponible:** saldo del cliente que puede gastar.
- **Saldo reservado:** monto retenido por pedidos en proceso o pendientes de verificar.
- **ID de pedido:** identificador propio, formato `FF-000123`.
- **Referencia:** código del pedido en VentasFF (ej. `EV-9B5F34F9`).

## 5. Requisitos funcionales

### 5.1 Autenticación y usuarios
- **RF-01** El usuario inicia sesión con usuario y contraseña.
- **RF-02** Las cuentas se crean con contraseña temporal y `debe_cambiar_clave = true`. Hasta cambiarla, el usuario solo puede acceder a la pantalla de cambio de contraseña.
- **RF-03** El admin puede crear, bloquear, desbloquear y resetear la contraseña (nueva temporal) de usuarios. Desde el panel el admin crea solo cuentas de cliente (los admins se crean por CLI) y no puede bloquearse a sí mismo.
- **RF-04** Un usuario bloqueado no puede iniciar sesión ni usar sesiones existentes.
- **RF-05** El login limita intentos fallidos: con 5 fallos en 15 min para el mismo usuario desde la misma IP, o 20 fallos en 15 min desde una IP, se rechazan nuevos intentos durante 15 min con un mensaje genérico.
- **RF-06** La sesión expira tras 8 h sin actividad. Cerrar sesión la invalida. Bloquear al usuario, resetear o cambiar su contraseña cierra todas sus sesiones abiertas.
- **RF-07** El nombre de usuario tiene de 3 a 30 caracteres: letras minúsculas a-z, dígitos, `.`, `_` y `-`. Se guarda en minúsculas y el login no distingue mayúsculas.
- **RF-08** La contraseña nueva tiene de 8 a 128 caracteres y debe ser distinta de la actual.

### 5.2 Catálogo
- **RF-10** El sistema sincroniza `productos.php` una vez al día y bajo demanda del admin, filtrando `juego = free_fire`. Los paquetes nuevos se crean inactivos y sin `precio_venta`.
- **RF-11** El `precio_venta` de cada paquete lo define el admin manualmente. No hay cálculo automático de margen en v1. Un paquete sin `precio_venta` no puede activarse.
- **RF-12** El admin puede definir o cambiar el `precio_venta` por paquete y activar/desactivar paquetes. Al fijar el precio, el sistema avisa si `precio_venta <= precio_costo`.
- **RF-13** El cliente solo ve paquetes activos y su `precio_venta`.
- **RF-14** Si el costo de un paquete cambia en la sincronización, el `precio_venta` no se modifica y el panel marca los paquetes con `precio_venta <= precio_costo`. Los pedidos ya creados conservan el precio con el que se vendieron.

### 5.3 Recarga
- **RF-20** El cliente ingresa el Player ID; el backend llama a `validar.php` (con `paquete_id`) y muestra el nickname.
  - `estado = no_existe` → se bloquea la recarga.
  - `estado = no_disponible` o fallo del validador → se advierte al cliente y se permite continuar bajo su confirmación.
- **RF-21** El cliente selecciona paquete y confirma explícitamente antes de enviar.
- **RF-22** El backend verifica `saldo_disponible >= precio_venta` y reserva el monto antes de llamar a VentasFF.
- **RF-23** El backend verifica con `saldo.php` que el crédito en VentasFF cubre el `precio_costo` antes de procesar.
- **RF-24** El backend ejecuta `recargar.php` y procesa el resultado:
  - Éxito → pedido `EXITOSO`, cobro confirmado, se guarda `referencia`.
  - Error de la API → pedido `FALLIDO`, reserva liberada, se guarda el motivo.
  - Timeout o respuesta ilegible → pedido `PENDIENTE_VERIFICAR`, monto retenido.
- **RF-25** Cada intento de recarga lleva un token de idempotencia único; un reenvío con el mismo token no crea otro pedido.
- **RF-26** El nickname se guarda desde `validar.php`, no desde `recargar.php`.
- **RF-27** El Player ID debe ser numérico de 4 a 20 dígitos.

### 5.4 Historial del cliente
- **RF-30** Cada pedido tiene ID propio visible (`FF-000123`), incluidos los fallidos.
- **RF-31** El cliente ve su historial: fecha, ID de pedido, paquete, Player ID, nickname, monto, estado, referencia (si existe) y motivo del error (si falló).
- **RF-32** Filtros del cliente: estado, rango de fechas, Player ID, ID de pedido.
- **RF-33** Pantalla de inicio del cliente: saldo disponible, gasto total, número de recargas, botones Recargar e Historial. Gasto total y número de recargas cuentan solo pedidos `EXITOSO`.
- **RF-34** Pantalla Fondos: saldo disponible, saldo reservado y los abonos y ajustes con su fecha, monto y nota.
- **RF-35** El cliente nunca recibe `precio_costo`, ni en pantalla ni en respuestas de la API.
- **RF-36** Los montos se muestran al cliente en USD con 2 decimales.

### 5.5 Saldos
- **RF-40** El admin abona saldo a un cliente con una nota obligatoria (método de pago, referencia).
- **RF-41** El admin puede registrar ajustes (positivos o negativos) con nota obligatoria.
- **RF-42** Todo cambio de saldo genera un movimiento en el libro contable (solo inserciones).

### 5.6 Panel admin
- **RF-50** Listado de pedidos con filtros: estado, rango de fechas, usuario, Player ID, ID de pedido, `referencia` de VentasFF, solo `PENDIENTE_VERIFICAR`.
- **RF-51** Detalle de pedido: todos los datos, costo, venta, ganancia, historial de estados y error.
- **RF-52** Resolución manual de `PENDIENTE_VERIFICAR`: "Marcar exitoso" (confirma cobro; permite registrar `referencia`) o "Marcar fallido" (libera reserva).
- **RF-53** Vista de saldo real en VentasFF frente a la suma de saldos de clientes (disponible + reservado).
- **RF-54** Ganancia propia: `precio_venta − precio_costo` por pedido exitoso, con totales por rango de fechas.
- **RF-55** Registro de auditoría de acciones del admin.

## 6. Reglas de negocio

- **RN-01** El saldo del cliente nunca puede quedar negativo.
- **RN-02** Cada recarga descuenta exactamente `precio_venta` vigente al momento de crear el pedido.
- **RN-03** Una recarga es irreversible en VentasFF; la validación del ID es obligatoria antes de recargar.
- **RN-04** Un pedido en `PENDIENTE_VERIFICAR` nunca se reintenta automáticamente.
- **RN-05** Solo una recarga a la vez hacia VentasFF (la API devuelve `BUSY` si hay otra en curso).
- **RN-06** Si VentasFF responde `BUSY`, se espera 3 s y se reintenta una vez; si persiste, el pedido pasa a `FALLIDO` con motivo "proveedor ocupado" (no se llamó con éxito, por lo que no hubo cobro).
- **RN-07** Límites del proveedor: 60 peticiones/min y 10 recargas/min. El sistema aplica límite propio por debajo de esos topes.
- **RN-08** Si la API responde `INSUFFICIENT_CREDIT` (crédito del dueño agotado), el pedido es `FALLIDO` y el admin recibe alerta visible en su panel.
- **RN-09** Los pedidos que quedan en `PROCESANDO` tras un reinicio del servicio pasan a `PENDIENTE_VERIFICAR`.
- **RN-10** La suma de saldos de clientes no debe superar el crédito real en VentasFF; el admin ve la diferencia.
- **RN-11** El sistema genera una alerta visible para el admin cuando: (a) el crédito en VentasFF queda por debajo del umbral `alerta_credito_min` (valor inicial 10 USD, editable por el admin); (b) VentasFF responde `INSUFFICIENT_CREDIT` o el crédito no cubre el costo de una recarga; (c) VentasFF responde un error de cuenta (`MISSING_KEY`, `INVALID_KEY`, `INACTIVE`, `API_DISABLED`). La alerta sigue activa hasta que el admin la marca como atendida; no se crea otra activa del mismo tipo.

## 7. Estados del pedido

| Estado interno | Etiqueta al cliente | Saldo del cliente |
|---|---|---|
| CREADO / PROCESANDO | Procesando | Reservado |
| EXITOSO | Exitoso | Cobrado |
| FALLIDO | Fallido + motivo | Liberado |
| PENDIENTE_VERIFICAR | En revisión | Retenido |

Transiciones permitidas:
`CREADO → PROCESANDO → EXITOSO | FALLIDO | PENDIENTE_VERIFICAR`
`PENDIENTE_VERIFICAR → EXITOSO | FALLIDO` (solo por acción del admin).

## 8. Requisitos no funcionales

- **RNF-01** La API Key de VentasFF solo existe en el backend (variable de entorno).
- **RNF-02** El saldo se controla solo en servidor, con transacciones y bloqueo de fila.
- **RNF-03** Contraseñas con argon2 (o bcrypt), protección CSRF, sesión con cookie `HttpOnly`. HTTPS y atributo `Secure` obligatorios en producción con dominio (diferidos, ver RNF-11).
- **RNF-04** Montos con tipo decimal exacto (nunca float).
- **RNF-05** Los logs no contienen la API Key ni contraseñas.
- **RNF-06** Repositorio público: sin secretos, precios de costo reales, datos ni respaldos. Se incluye `.env.example`.
- **RNF-07** PostgreSQL es externo a la aplicación (servidor propio en el VPS). La app se conecta únicamente mediante `DATABASE_URL`; no depende de que la base corra dentro del mismo Docker Compose.
- **RNF-08** El sistema debe poder probarse sin red mediante un simulador de VentasFF.
- **RNF-09** Zona horaria almacenada en UTC; mostrada en la zona del usuario.
- **RNF-10** Las pruebas automáticas usan un esquema `test` aislado, nunca los datos de desarrollo ni de producción.
- **RNF-11** Mientras no exista dominio, la app corre por HTTP y el atributo `Secure` de la cookie se controla con `COOKIE_SECURE` (`false` en pruebas). No se admiten clientes reales sin HTTPS.

## 9. Contrato externo (VentasFF)

Base: `https://ventasff.com/api/reseller`. Autenticación: `Authorization: Bearer <API_KEY>`. Todas las respuestas son JSON.

Respuesta correcta: `{"success": true, "data": …}`. Error: `{"success": false, "error": "texto", "code": "CODIGO"}`.

| Endpoint | Uso | `data` en éxito |
|---|---|---|
| `GET /saldo.php` | Crédito disponible del dueño. | `{credito, currency, nombre}` |
| `GET /productos.php` | Catálogo con precio de costo. | Lista de `{paquete_id, nombre, juego, diamantes, precio, currency, dato_extra}`; `precio` es el precio de costo; `dato_extra` es `null` si el juego no pide datos adicionales. |
| `GET /validar.php?player_id=&paquete_id=` | Valida el ID. | `{valid, nickname, estado}`; `estado`: `ok`, `no_existe`, `no_disponible` (el validador no respondió). |
| `POST /recargar.php` | Cuerpo JSON `{paquete_id, player_id}`. | `{referencia, monto, saldo, player_id, nickname}`; `nickname` puede ser `null`. |

Los montos llegan como números JSON y se leen como decimales exactos (RNF-04), nunca como float.

| HTTP | `code` |
|---|---|
| 401 | `MISSING_KEY`, `INVALID_KEY` |
| 403 | `INACTIVE`, `API_DISABLED` |
| 409 | `BUSY` (otra recarga en curso) |
| 422 | `MISSING_FIELD`, `INSUFFICIENT_CREDIT` (nada se cobró), `PURCHASE_FAILED` (la entrega falló; el crédito no se descontó; `error` trae el motivo) |
| 429 | `RATE_LIMITED` (incluye cabecera `Retry-After`) |

Limitaciones: sin endpoint de estado de pedido; `recargar.php` no acepta otros campos (ni precio de venta ni nickname). Timeouts: 15 s conexión, 30 s general, 90 s recarga.

## 10. Criterios de aceptación globales

- **CA-01** Dos solicitudes simultáneas del mismo cliente con saldo para una sola no producen dos recargas.
- **CA-02** Un doble clic o reenvío no crea dos pedidos.
- **CA-03** Ningún JSON ni HTML entregado a un cliente contiene `precio_costo`.
- **CA-04** Para todo pedido, `saldo_disponible + saldo_reservado` del usuario coincide con la suma de sus movimientos.
- **CA-05** Un pedido fallido aparece en el historial del cliente con su ID y motivo.
- **CA-06** El admin puede localizar cualquier pedido por ID propio, `referencia` o Player ID.

## 11. Preguntas abiertas

| ID | Pregunta | Estado |
|---|---|---|
| Q-01 | Margen global inicial. | Retirada (CHG-002) |
| Q-02 | Redondeo de `precio_venta`. | Retirada (CHG-002) |
| Q-03 | Moneda mostrada al cliente. | Resuelta (CHG-007): USD (RF-36) |
| Q-04 | Expiración de sesión. | Resuelta (CHG-007): 8 h de inactividad (RF-06) |
| Q-05 | Frontend: Jinja2 + HTMX (propuesta) o SPA aparte. | Abierta |
| Q-06 | Umbral de alerta de crédito bajo en VentasFF. | Resuelta (CHG-006): 10 USD, editable (RN-11) |

## 12. Registro de cambios

Ver `sdd/changelog.md`.
