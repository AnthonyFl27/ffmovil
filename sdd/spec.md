# Especificación: Plataforma de recargas Free Fire (prepago)

- **Versión:** 0.27.0
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
- Publicación en `https://ffmovil.com` con HTTPS (Caddy), detrás de Cloudflare, en dos fases: primero una página «Próximamente» y, al lanzar, la app (RNF-18, RNF-19).
- Página pública de presentación en `/`, páginas legales «Términos y Condiciones» y «Política de Privacidad» (RF-58, RF-59) y página de contacto de revendedores `/resellers` (RF-62).

**Fuera (v1):**
- Mobile Legends (requiere Zone ID; sin probar en VentasFF).
- Pasarela de pago (el abono es manual).
- Cálculo de ganancia del cliente final.
- Registro público de usuarios (RF-62 solo publica cómo contactar a quien crea la cuenta).
- Reintentos automáticos de pedidos en `PENDIENTE_VERIFICAR`.
- Cálculo automático de margen o porcentaje (posible función futura).

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
- **RF-05** El login limita intentos fallidos. Se rechazan nuevos intentos durante 15 min, con un mensaje genérico, cuando hay 5 fallos en 15 min para el mismo usuario desde la misma IP, 10 fallos en 15 min para el mismo usuario desde cualquier IP, o 20 fallos en 15 min desde una IP. Los 15 min cuentan desde el fallo que alcanza el tope y los intentos rechazados no los alargan; durante el bloqueo no se verifica la contraseña, ni siquiera si es correcta. Un login correcto limpia solo el contador del par usuario+IP. Nunca se informa de los intentos que quedan.
- **RF-06** La sesión expira tras 8 h sin actividad. Cerrar sesión la invalida. Bloquear al usuario, resetear o cambiar su contraseña cierra todas sus sesiones abiertas.
- **RF-07** El nombre de usuario tiene de 3 a 30 caracteres: letras minúsculas a-z, dígitos, `.`, `_` y `-`. Se guarda en minúsculas y el login no distingue mayúsculas.
- **RF-08** La contraseña nueva tiene de 8 a 128 caracteres y debe ser distinta de la actual.
- **RF-60** El admin puede archivar a un cliente desde su ficha cuando deja de trabajar con la plataforma. Solo se archiva con el saldo disponible y el saldo reservado en cero (lo que incluye no tener pedidos en curso); si no, se rechaza con 409 y el mensaje indica el saldo pendiente. Archivar bloquea al cliente (RF-04), cierra sus sesiones (RF-06) y lo oculta del listado de usuarios; su cuenta, pedidos, movimientos y auditoría se conservan. El listado ofrece el filtro «Ver archivados», que muestra solo los archivados y desde el cual se abre su ficha. Mientras está archivado no se puede desbloquear ni registrarle abonos o ajustes (409). El admin puede restaurarlo: vuelve al listado y **sigue bloqueado**, y hay que desbloquearlo aparte. No se puede archivar a un administrador. El nombre de usuario de un cliente archivado sigue ocupado (RF-07). Archivar y restaurar quedan en la auditoría (RF-55).
- **RF-61** El listado de usuarios del panel admin tiene un botón «Filtros» que despliega un formulario con estos filtros, combinables entre sí y con «Ver archivados»: **usuario** (coincidencia parcial, sin distinguir mayúsculas), **estado** (activo o bloqueado), **con saldo** (sí: saldo disponible mayor que cero; no: igual a cero), **debe cambiar clave** (sí o no), **último login** y **fecha de creación** (cada uno con rango «desde» y «hasta», por días de la zona del navegador como en RF-50; quien nunca ha iniciado sesión no coincide con un rango de último login). El listado se actualiza en vivo al escribir o cambiar un filtro y el botón «Filtrar» hace lo mismo sin JavaScript; «Quitar filtros» vuelve al listado completo. Sin filtros muestra todos los usuarios. Es solo lectura. `GET /admin/usuarios` acepta `q` (máximo 30 caracteres, el tope de RF-07), `estado` (`activo` o `bloqueado`), `con_saldo`, `debe_cambiar_clave`, `login_desde`, `login_hasta`, `creado_desde` y `creado_hasta`; un valor inválido se rechaza con 422. El listado muestra además la fecha de creación de cada usuario.

### 5.2 Catálogo
- **RF-10** El sistema sincroniza `productos.php` una vez al día y bajo demanda del admin, filtrando `juego = free_fire`. Los paquetes nuevos se crean inactivos y sin `precio_venta`. Los paquetes que dejan de venir se desactivan, salvo que la respuesta no contenga ningún paquete `free_fire`: en ese caso la sincronización no modifica el catálogo (no desactiva ni actualiza ningún paquete), lo indica en su resultado y genera la alerta de RN-11 (e).
- **RF-11** El `precio_venta` de cada paquete lo define el admin manualmente. No hay cálculo automático de margen en v1. Un paquete sin `precio_venta` no puede activarse.
- **RF-12** El admin puede definir o cambiar el `precio_venta` por paquete y activar/desactivar paquetes. Al fijar el precio, el sistema avisa si `precio_venta <= precio_costo`.
- **RF-13** El cliente solo ve paquetes activos y su `precio_venta`.
- **RF-14** Si el costo de un paquete cambia en la sincronización, el `precio_venta` no se modifica y el panel marca los paquetes con `precio_venta <= precio_costo`. Los pedidos ya creados conservan el precio con el que se vendieron.

### 5.3 Recarga
- **RF-20** El cliente ingresa primero solo el Player ID; el backend llama a `validar.php` con el paquete activo de menor precio y muestra una tarjeta con el nickname y el Player ID. Los paquetes se muestran solo después de esa validación, y el cliente puede volver a cambiar el Player ID.
  - `estado = no_existe` → se bloquea la recarga y se pide otro Player ID.
  - `estado = no_disponible` o fallo del validador → la tarjeta advierte que no se pudo verificar el nombre y se permite continuar bajo su confirmación.
- **RF-21** Con el jugador verificado, el cliente elige un paquete, ve un resumen (jugador, Player ID, paquete, precio y saldo disponible) y confirma explícitamente antes de enviar. Al confirmar, el backend vuelve a validar el ID con el paquete elegido (RN-03).
- **RF-22** El backend verifica `saldo_disponible >= precio_venta` y reserva el monto antes de llamar a VentasFF.
- **RF-23** El backend verifica con `saldo.php` que el crédito en VentasFF cubre el `precio_costo` antes de procesar.
- **RF-24** El backend ejecuta `recargar.php` y procesa el resultado:
  - Éxito → pedido `EXITOSO`, cobro confirmado, se guarda `referencia`.
  - Error de la API → pedido `FALLIDO`, reserva liberada, se guarda el motivo.
  - Timeout o respuesta ilegible → pedido `PENDIENTE_VERIFICAR`, monto retenido.
- **RF-25** Cada intento de recarga lleva un token de idempotencia único; un reenvío con el mismo token no crea otro pedido.
- **RF-26** El nickname se guarda desde `validar.php`, no desde `recargar.php`.
- **RF-27** El Player ID debe ser numérico, de 5 a 15 dígitos (se ignoran los espacios alrededor). Al verificarlo, el cliente recibe un mensaje según el caso, mostrado en una etiqueta roja bajo el campo: vacío → «Escribe tu Player ID.»; con algo que no son dígitos → «ID no válido, verifícalo. Solo se permiten números.»; de 1 a 4 dígitos → «Al ID le faltan dígitos. Verifícalo.»; de más de 15 dígitos → «El ID tiene demasiados dígitos. Verifícalo.»
- **RF-56** Cada cliente puede validar un Player ID (RF-20) como máximo 10 veces por minuto, en la API y en la web. Superado el tope recibe 429 con el mensaje «Demasiadas verificaciones. Espera un momento e inténtalo de nuevo.» y no se llama a VentasFF. El tope es por usuario: un cliente no consume el cupo de VentasFF (RN-07) de los demás.
- **RF-57** Cada cliente puede crear como máximo 5 pedidos de recarga por minuto, en la API (`POST /recargas`) y en la web (confirmación). Superado el tope recibe 429 con el mensaje «Demasiadas recargas. Espera un momento e inténtalo de nuevo.», sin reservar saldo, sin crear pedido y sin llamar a VentasFF. Cada solicitud de confirmación cuenta, incluido un reenvío con el mismo token (RF-25); las rechazadas por el tope no cuentan. El tope es por usuario: un cliente no puede ocupar el cupo de recargas de VentasFF (RN-07) de los demás.

### 5.4 Historial del cliente
- **RF-30** Cada pedido tiene ID propio visible (`FF-000123`), incluidos los fallidos.
- **RF-31** El cliente ve su historial: fecha, ID de pedido, paquete, Player ID, nickname, monto, estado, referencia (si existe) y motivo del error (si falló).
- **RF-32** Filtros del cliente: estado, rango de fechas, Player ID, ID de pedido.
- **RF-33** Pantalla de inicio del cliente: saldo disponible, gasto total, número de recargas, botones Recargar e Historial y la lista de sus **últimas 5 recargas** de cualquier estado (fecha, paquete, nickname del jugador, monto y estado, cada una enlazada a su detalle; sin enlace "Ver todo", pues el botón Historial cumple esa función). Si no tiene recargas, muestra un estado vacío con un acceso a Recargar. Gasto total y número de recargas cuentan solo pedidos `EXITOSO`.
- **RF-34** Pantalla Fondos: saldo disponible, saldo reservado y los abonos y ajustes con su fecha, monto y nota.
- **RF-35** El cliente nunca recibe `precio_costo`, ni en pantalla ni en respuestas de la API.
- **RF-36** Los montos se muestran al cliente en USD con 2 decimales.

### 5.5 Saldos
- **RF-40** El admin abona saldo a un cliente con una nota obligatoria (método de pago, referencia).
- **RF-41** El admin puede registrar ajustes (positivos o negativos) con nota obligatoria.
- **RF-42** Todo cambio de saldo genera un movimiento en el libro contable (solo inserciones).
- **RF-43** La ficha de cada cliente en el panel admin muestra su **historial de abonos y ajustes**, del más reciente al más antiguo y paginado. Cada registro muestra: fecha, tipo (abono o ajuste), monto con signo y nota. Permite filtrar por tipo y por rango de fechas. Las reservas, liberaciones y cargos de las recargas no aparecen: se ven en el detalle de cada pedido. Es solo lectura y no modifica el libro (RF-42). La pantalla Fondos del cliente no cambia (RF-34).

### 5.6 Panel admin
- **RF-50** Listado de pedidos con filtros: estado, rango de fechas, usuario, Player ID, ID de pedido, `referencia` de VentasFF, solo `PENDIENTE_VERIFICAR`.
- **RF-51** Detalle de pedido: todos los datos, costo, venta, ganancia, historial de estados y error.
- **RF-52** Resolución manual de `PENDIENTE_VERIFICAR`: "Marcar exitoso" (confirma cobro; permite registrar `referencia`) o "Marcar fallido" (libera reserva).
- **RF-53** Vista de saldo real en VentasFF frente a la suma de saldos de clientes (disponible + reservado), con el **saldo por cubrir** (suma de saldos menos crédito, o 0.00 si el crédito la cubre). Un saldo por cubrir mayor que cero es informativo, no un error (RN-10).
- **RF-54** Ganancia propia: `precio_venta − precio_costo` por pedido exitoso, con totales por rango de fechas.
- **RF-55** Registro de auditoría de acciones del admin.

### 5.7 Página pública y legales

- **RF-58** `GET /` sin sesión válida muestra una página pública de presentación, con tema azul oscuro y blanco, que contiene: (a) un encabezado con el logo, el nombre «FFMovil» y el botón «Iniciar sesión» hacia `/login`, visible sin desplazarse a 360 × 740 px; (b) un bloque principal con el texto «Ya puedes vender diamantes a tus propios clientes usando nuestros precios y nuestra plataforma.» y un personaje con un diamante que flota en su mano (el botón «Iniciar sesión» del encabezado sigue visible al desplazar); (c) los tres pasos para recargar (recibir la cuenta que crea nuestro equipo, tener saldo abonado, recargar con el Player ID) y, debajo, si hay revendedores definidos (RF-62), una sección «¿Aún no tienes usuario?» con el texto «Contáctate con uno de nuestros revendedores: te ayudan a crear tu usuario y a empezar a vender diamantes.» y el botón «Ver revendedores» hacia `/resellers`; (d) secciones con imágenes de personajes que aparecen con una animación al desplazar la página; (e) un pie con el nombre «FFMovil» y una descripción breve, los enlaces «Términos y Condiciones» y «Política de Privacidad» (RF-59), el correo de contacto y, debajo de él, el enlace «Revendedores» hacia `/resellers` (RF-62), «© <año actual> FFMovil • Todos los derechos reservados», el aviso «La marca Free Fire es propiedad exclusiva de Garena. Este sitio opera de manera independiente.» y el sello «Protected by Cloudflare». No muestra precios, importes, paquetes, saldos ni datos de cuenta; no lee paquetes, saldos ni pedidos y no llama a VentasFF. El pie no incluye selector de idioma ni de moneda, sección de ayuda ni números de contacto de revendedores (solo están en `/resellers`). El correo de contacto se define fuera del repositorio (RNF-06); si no está definido, la línea del correo no se muestra, y la columna «Contacto» solo se muestra si hay correo o revendedores definidos. Con sesión válida, `/` sigue llevando al inicio del rol o a cambiar la clave (RF-02).
- **RF-59** `GET /terminos` y `GET /privacidad` muestran las páginas «Términos y Condiciones» y «Política de Privacidad», sin requerir sesión y sin redirigir a quien la tiene, con el mismo encabezado y pie que `/` y un enlace de vuelta a `/`. El texto lo redacta y aprueba el dueño. Puede incluir condiciones comerciales que se cumplen fuera de la plataforma: requisitos para ser revendedor, horario y plazos de atención, abonos y política de reembolsos, y ley aplicable. No sustituye asesoría legal. Lo que el texto afirme sobre el funcionamiento de la plataforma (cuentas, saldo, recargas, estados del pedido, datos guardados y cookies) debe coincidir con esta spec. Los textos dicen que las cuentas las crea FFMovil o los revendedores autorizados de su equipo, que la cuenta se puede solicitar por el correo de contacto o desde `/resellers`, y que esos revendedores pueden crear usuarios y ver los datos necesarios para hacerlo; distinguen a los «revendedores del equipo de FFMovil» de los «clientes revendedores». El correo de contacto del texto sale de la configuración (RNF-06).
- **RF-62** `GET /resellers` muestra, sin requerir sesión y sin redirigir a quien la tiene, la lista de revendedores del equipo de FFMovil, con el mismo encabezado y pie que `/` y un enlace de vuelta a `/`. Por cada revendedor muestra solo su nombre y los botones «WhatsApp» (`https://wa.me/<número>?text=…`, con el mensaje «Hola, quiero abrir mi usuario en FFMovil.» ya escrito) y «Telegram» (`https://t.me/<usuario>`), cada uno con su logo y solo los canales que tenga definidos; los enlaces se abren en una pestaña nueva con `rel="noopener noreferrer"`. Los revendedores se definen fuera del repositorio (RNF-06) en la variable `RESELLERS`, un JSON en una línea con una lista de `{"nombre", "whatsapp", "telegram"}`: `nombre` es obligatorio, hace falta al menos un canal, `whatsapp` lleva solo dígitos con código de país y `telegram` va sin `@`; un valor inválido impide arrancar la app con un error claro. Sin revendedores definidos, la portada no muestra su sección (RF-58), el pie no muestra el enlace y `/resellers` responde 404. No muestra precios, importes, paquetes, saldos ni datos de cuenta, no lee la BD y no llama a VentasFF. Los revendedores del equipo usan el usuario de administración con sus mismas condiciones; esta página no crea cuentas ni registra a nadie.

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
- **RN-10** El admin puede abonar a un cliente un monto mayor que el crédito disponible en VentasFF (pago adelantado). El abono nunca consulta ni modifica el crédito de VentasFF y no tiene tope. Si la suma de saldos de clientes supera el crédito real, el panel muestra el **saldo por cubrir** como dato informativo, sin alerta aparte. Cuando falte crédito en VentasFF para una recarga, aplican RF-23 y RN-08: el pedido pasa a `FALLIDO`, se libera la reserva del cliente y el admin recibe la alerta.
- **RN-11** El sistema genera una alerta visible para el admin cuando: (a) el crédito en VentasFF queda por debajo del umbral `alerta_credito_min` (valor inicial 10 USD, editable por el admin); (b) VentasFF responde `INSUFFICIENT_CREDIT` o el crédito no cubre el costo de una recarga; (c) VentasFF responde un error de cuenta (`MISSING_KEY`, `INVALID_KEY`, `INACTIVE`, `API_DISABLED`); (e) la sincronización del catálogo recibe una respuesta sin ningún paquete `free_fire` (RF-10). La alerta sigue activa hasta que el admin la marca como atendida; no se crea otra activa del mismo tipo.

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
- **RNF-03** Contraseñas con argon2 (o bcrypt), protección CSRF, sesión con cookie `HttpOnly`. HTTPS y atributo `Secure` obligatorios en producción (RNF-11, RNF-18).
- **RNF-04** Montos con tipo decimal exacto (nunca float).
- **RNF-05** Los logs no contienen la API Key ni contraseñas.
- **RNF-06** Repositorio público: sin secretos, precios de costo reales, datos ni respaldos. Se incluye `.env.example`.
- **RNF-07** PostgreSQL es externo a la aplicación (servidor propio en el VPS). La app se conecta únicamente mediante `DATABASE_URL`; no depende de que la base corra dentro del mismo Docker Compose.
- **RNF-08** El sistema debe poder probarse sin red mediante un simulador de VentasFF.
- **RNF-09** Zona horaria almacenada en UTC; mostrada en la zona del usuario.
- **RNF-10** Las pruebas automáticas usan un esquema `test` aislado, nunca los datos de desarrollo ni de producción.
- **RNF-11** En producción la app se sirve solo por HTTPS en `ffmovil.com` con `COOKIE_SECURE=true`. El acceso por HTTP sin dominio (`COOKIE_SECURE=false`) queda limitado al desarrollo local y a las pruebas. No se admiten clientes reales sin HTTPS.
- **RNF-12** Uso en móvil (*mobile-first*): todas las pantallas de cliente y de admin se usan sin desplazamiento horizontal de la página y con todo el contenido legible desde 360 px de ancho, y siguen siendo correctas en escritorio.
  - La navegación se pliega en pantallas angostas (menú desplegable) y todas sus opciones son alcanzables.
  - Los listados con muchas columnas (historial, pedidos, usuarios, auditoría, catálogo) se muestran en móvil como tarjetas, con el estado del pedido visible sin desplazamiento horizontal. El detalle completo es accesible desde cada fila.
  - Los controles interactivos (botones, enlaces de acción, casillas, opciones de paquete) miden al menos 44 × 44 px de área táctil.
  - Los filtros de los listados van plegados bajo un botón «Filtros», en móvil y en escritorio, y se despliegan al tocarlo; solo arrancan desplegados si ya hay algún filtro aplicado.
  - Los campos de entrada usan letra de al menos 16 px y el Player ID abre el teclado numérico.
- **RNF-13** Límites de entrada: el cuerpo de una petición no puede superar 64 KB (413 Payload Too Large; no se procesa) y en el login un `usuario` de más de 30 caracteres o una `clave` de más de 128 se rechazan como credenciales incorrectas, sin verificar la contraseña. Los topes coinciden con RF-07 y RF-08, así que no afectan a ningún uso legítimo.
- **RNF-14** Todas las respuestas llevan cabeceras de seguridad: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` y `Content-Security-Policy: default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'` (sin scripts ni estilos en línea). Las respuestas que no son archivos estáticos llevan además `Cache-Control: no-store`, para que «Atrás» no muestre páginas con sesión tras salir.
- **RNF-15** La app no publica documentación interactiva ni el esquema de la API (`/docs`, `/redoc` y `/openapi.json` no existen).
- **RNF-16** La IP del cliente (limitador de login RF-05, sesiones y auditoría RF-55) es la de la conexión. Si se define la variable opcional `CLIENT_IP_HEADER` (por ejemplo `CF-Connecting-IP` tras el túnel de Cloudflare), se toma de esa cabecera, pero solo cuando la conexión viene de loopback o de una red privada (proxy local o red de Docker); una cabecera ausente o que no sea una IP válida se ignora. Sin esta variable, tras un proxy todos los clientes comparten IP y el tope por IP de RF-05 bloquearía a todos a la vez.
- **RNF-17** Tope general de peticiones: con sesión válida, 120 por minuto por usuario; sin sesión válida (login, páginas públicas, sesión vencida o ausente), 60 por minuto por IP (la de RNF-16). Superado el tope se responde 429 con el mensaje «Demasiadas peticiones. Espera un momento e inténtalo de nuevo.»; las peticiones rechazadas no cuentan. Quedan fuera `/static` y `/health`. Los topes de RF-05, RF-56 y RF-57 se aplican además de este. Tras un proxy, el tope por IP solo distingue clientes si se define `CLIENT_IP_HEADER` (RNF-16).
- **RNF-18** `ffmovil.com` es la dirección canónica y `www.ffmovil.com` redirige a ella con una redirección permanente; el HTTP simple redirige a HTTPS. El tráfico pasa por Cloudflare (proxy, SSL/TLS en Full strict) y Caddy, con certificado válido y renovación automática. Hasta el lanzamiento, `https://ffmovil.com` muestra solo una página estática «Próximamente» y la app no está desplegada ni es accesible desde internet. En el VPS el firewall solo admite SSH, 80 y 443, y la app nunca publica su puerto: solo Caddy la alcanza por la red Docker.
- **RNF-19** Con la app detrás de Cloudflare y Caddy, Caddy solo acepta `CF-Connecting-IP` de conexiones que vienen de Cloudflare y entrega la IP real a la app en una cabecera propia que reemplaza cualquier valor enviado por el cliente; la app la toma con `CLIENT_IP_HEADER` (RNF-16). Así el límite de login (RF-05) y la auditoría (RF-55) ven la IP del cliente, y una cabecera falsa de quien no pasa por Cloudflare no se acepta.
- **RNF-20** Páginas públicas ligeras y accesibles (RF-58, RF-59): cada imagen pesa a lo sumo 150 KB y todas juntas a lo sumo 800 KB; las imágenes bajo el primer pliegue se cargan de forma diferida y todas llevan `width`, `height` y texto alternativo; las animaciones al desplazar solo usan `transform` y `opacity`, se activan con JavaScript propio servido desde `/static` (sin librerías ni scripts en línea, RNF-14) y se desactivan con `prefers-reduced-motion`; sin JavaScript todo el contenido sigue visible; sin fuentes, imágenes ni scripts de otros dominios.
- **RNF-21** Toda respuesta de `ffmovil.com` y de `www.ffmovil.com` por HTTPS lleva `Strict-Transport-Security: max-age=31536000` (1 año), añadida por Caddy tanto con la página «Próximamente» como con la app desplegada. No lleva `includeSubDomains` ni `preload`: solo protege a esos dos nombres y no inscribe el dominio en la lista de los navegadores. La app no la añade (en desarrollo corre por HTTP, donde los navegadores la ignoran).

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
- **CA-07** En un viewport de 360 × 740 px, ninguna pantalla de cliente ni de admin hace que el ancho del documento supere el del viewport, y todo control interactivo mide al menos 44 px de lado. Se verifica con una prueba automatizada de navegador.
- **CA-08** Si `productos.php` responde sin ningún paquete `free_fire`, los paquetes activos siguen activos, el resultado de la sincronización lo indica y queda una alerta activa `catalogo_vacio`; una segunda sincronización vacía no crea otra alerta.
- **CA-09** Con la página «Próximamente» publicada, `https://ffmovil.com` responde 200 con certificado válido, `http://ffmovil.com` y `https://www.ffmovil.com` redirigen a `https://ffmovil.com`, el puerto 8000 no responde desde internet y la página lleva las cabeceras de seguridad de RNF-14 y la de RNF-21. Con la app desplegada (fase 2), 5 intentos fallidos desde una IP no bloquean al mismo usuario desde otra IP y la auditoría muestra la IP del cliente. Se verifica en el despliegue; los archivos de configuración tienen además pruebas automáticas.
- **CA-10** `GET /` sin sesión responde 200 y contiene el botón «Iniciar sesión» hacia `/login`, los enlaces a `/terminos` y `/privacidad`, el aviso de marcas y el sello de Cloudflare, y no contiene precios ni importes; con sesión (cliente, admin o con cambio de clave pendiente) redirige como antes. `/terminos` y `/privacidad` responden 200 con y sin sesión. Ninguna de las tres llama a VentasFF ni lee paquetes, saldos o pedidos. Cada imagen pesa ≤ 150 KB y el total ≤ 800 KB (RNF-20). A 360 × 740 px cumplen CA-07, el botón «Iniciar sesión» es visible sin desplazarse y la prueba de navegador no registra violaciones de CSP (RNF-14).
- **CA-11** Un cliente con saldo disponible o reservado distinto de cero no se puede archivar (409). Con ambos en cero, al archivarlo desaparece del listado, no puede iniciar sesión y conserva sus pedidos y movimientos; aparece con el filtro «Ver archivados»; no se puede desbloquear ni abonar mientras está archivado; al restaurarlo vuelve al listado y sigue bloqueado.
- **CA-12** Con `RESELLERS` definido, `/resellers` responde 200 con y sin sesión, sin redirigir, y muestra por cada revendedor su nombre y solo los botones de los canales definidos, con los enlaces `wa.me` (con el mensaje) y `t.me`; la portada muestra la sección «¿Aún no tienes usuario?» con el botón hacia `/resellers` y el pie, bajo el correo, el enlace «Revendedores». Sin `RESELLERS`, `/resellers` responde 404 y la portada y el pie no muestran la sección ni el enlace; un valor inválido impide arrancar. No llama a VentasFF ni lee la BD. A 360 × 740 px cumple CA-07 y la prueba de navegador no registra violaciones de CSP (RNF-14).

## 11. Preguntas abiertas

| ID | Pregunta | Estado |
|---|---|---|
| Q-01 | Margen global inicial. | Retirada (CHG-002) |
| Q-02 | Redondeo de `precio_venta`. | Retirada (CHG-002) |
| Q-03 | Moneda mostrada al cliente. | Resuelta (CHG-007): USD (RF-36) |
| Q-04 | Expiración de sesión. | Resuelta (CHG-007): 8 h de inactividad (RF-06) |
| Q-05 | Frontend: Jinja2 + HTMX (propuesta) o SPA aparte. | Resuelta (CHG-008): Jinja2 + HTMX servidos por FastAPI |
| Q-06 | Umbral de alerta de crédito bajo en VentasFF. | Resuelta (CHG-006): 10 USD, editable (RN-11) |
| Q-07 | Derechos de uso del logo de Free Fire y de las imágenes de personajes y objetos de Garena en una página pública y en un repositorio público. | Resuelta (CHG-022): las imágenes se publican en el repositorio (`app/static/inicio/`); el aviso de marcas de RF-58 se mantiene |

## 12. Registro de cambios

Ver `sdd/changelog.md`.
