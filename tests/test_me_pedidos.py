"""T-053: historial del cliente con filtros y paginación (RF-31, RF-32, CA-05)."""

from datetime import UTC, datetime

from app.services.codigos import codigo_pedido
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


async def preparar_pedidos(sesion):
    """Cliente con cuatro pedidos en días distintos (del más reciente al más antiguo:
    EXITOSO, FALLIDO, PENDIENTE_VERIFICAR, PROCESANDO).

    Devuelve el nombre de usuario y los códigos por estado.
    """
    usuario = await crear_usuario_con_clave(sesion)
    paquete = await crear_paquete(sesion, precio_costo="0.50", precio_venta="0.75")
    cambios = {
        "EXITOSO": {
            "creado_en": datetime(2026, 10, 4, 12, tzinfo=UTC),
            "referencia": "EV-ABC",
            "nickname": "Nick",
        },
        "FALLIDO": {
            "creado_en": datetime(2026, 10, 3, 12, tzinfo=UTC),
            "error": "Motivo X",
            "error_code": "PURCHASE_FAILED",
            "player_id": "12345678",
        },
        "PENDIENTE_VERIFICAR": {"creado_en": datetime(2026, 10, 2, 12, tzinfo=UTC)},
        "PROCESANDO": {"creado_en": datetime(2026, 10, 1, 12, tzinfo=UTC)},
    }
    codigos = {}
    for estado, extra in cambios.items():
        pedido = await crear_pedido(sesion, usuario.id, paquete, estado=estado, **extra)
        pedido.codigo = codigo_pedido(pedido.id)
        codigos[estado] = pedido.codigo
    nombre = usuario.usuario
    await sesion.commit()
    return nombre, codigos


async def listar(cliente, **params):
    """Devuelve (total, códigos) de una consulta correcta a /me/pedidos."""
    respuesta = await cliente.get("/me/pedidos", params=params)
    assert respuesta.status_code == 200
    datos = respuesta.json()
    return datos["total"], [p["codigo"] for p in datos["pedidos"]]


async def test_lista_sin_filtros_ordenada_y_con_campos(api, sesion_bd):
    nombre, codigos = await preparar_pedidos(sesion_bd)
    c = api()
    await iniciar_sesion(c, nombre)
    respuesta = await c.get("/me/pedidos")
    assert respuesta.status_code == 200
    assert "costo" not in respuesta.text
    datos = respuesta.json()
    assert (datos["total"], datos["pagina"], datos["por_pagina"]) == (4, 1, 20)
    exitoso, fallido, pendiente, procesando = datos["pedidos"]
    assert [p["codigo"] for p in datos["pedidos"]] == [
        codigos["EXITOSO"],
        codigos["FALLIDO"],
        codigos["PENDIENTE_VERIFICAR"],
        codigos["PROCESANDO"],
    ]
    sin_fecha = {k: v for k, v in exitoso.items() if k != "fecha"}
    assert sin_fecha == {
        "codigo": codigos["EXITOSO"],
        "paquete": "110 Diamantes",
        "diamantes": 110,
        "player_id": "75807448",
        "nickname": "Nick",
        "monto": "0.75",
        "moneda": "USD",
        "estado": "EXITOSO",
        "estado_etiqueta": "Exitoso",
        "referencia": "EV-ABC",
        "motivo": None,
    }
    assert fallido["estado_etiqueta"] == "Fallido"
    assert fallido["motivo"] == "Motivo X"
    assert pendiente["estado"] == "PENDIENTE_VERIFICAR"
    assert pendiente["estado_etiqueta"] == "En revisión"
    assert procesando["estado"] == "PROCESANDO"
    assert procesando["estado_etiqueta"] == "Procesando"


async def test_filtros_del_historial(api, sesion_bd):
    nombre, codigos = await preparar_pedidos(sesion_bd)
    c = api()
    await iniciar_sesion(c, nombre)

    assert await listar(c, estado="FALLIDO") == (1, [codigos["FALLIDO"]])
    assert await listar(c, estado="PROCESANDO") == (1, [codigos["PROCESANDO"]])
    # desde es inclusivo: 2026-10-02 12:00 UTC expresado con otra zona.
    assert await listar(c, desde="2026-10-02T07:00:00-05:00") == (
        3,
        [codigos["EXITOSO"], codigos["FALLIDO"], codigos["PENDIENTE_VERIFICAR"]],
    )
    # hasta es exclusivo: 2026-10-03 12:00 UTC deja fuera el FALLIDO.
    assert await listar(c, hasta="2026-10-03T12:00:00Z") == (
        2,
        [codigos["PENDIENTE_VERIFICAR"], codigos["PROCESANDO"]],
    )
    assert await listar(c, desde="2026-10-02T07:00:00-05:00", hasta="2026-10-03T12:00:00Z") == (
        1,
        [codigos["PENDIENTE_VERIFICAR"]],
    )
    assert await listar(c, player_id="12345678") == (1, [codigos["FALLIDO"]])
    # Código en minúsculas y con espacios alrededor.
    assert await listar(c, codigo=f" {codigos['EXITOSO'].lower()} ") == (
        1,
        [codigos["EXITOSO"]],
    )
    assert await listar(c, codigo="XYZ") == (0, [])


async def test_paginacion(api, sesion_bd):
    nombre, codigos = await preparar_pedidos(sesion_bd)
    c = api()
    await iniciar_sesion(c, nombre)

    datos = (await c.get("/me/pedidos", params={"por_pagina": 3, "pagina": 2})).json()
    assert (datos["total"], datos["pagina"], datos["por_pagina"]) == (4, 2, 3)
    assert [p["codigo"] for p in datos["pedidos"]] == [codigos["PROCESANDO"]]

    assert (await c.get("/me/pedidos", params={"por_pagina": 101})).status_code == 422
    assert (await c.get("/me/pedidos", params={"pagina": 0})).status_code == 422


async def test_aislamiento_entre_clientes(api, sesion_bd):
    nombre_dueno, codigos = await preparar_pedidos(sesion_bd)
    otro = await crear_usuario_con_clave(sesion_bd)
    nombre_otro = otro.usuario

    dueno = api()
    await iniciar_sesion(dueno, nombre_dueno)
    ajeno = api()
    await iniciar_sesion(ajeno, nombre_otro)

    # El otro cliente no ve los pedidos del dueño en su lista.
    assert await listar(ajeno) == (0, [])

    # Un código ajeno da 404 con el mismo cuerpo que uno inexistente o inválido.
    codigo_ajeno = codigos["EXITOSO"]
    respuesta_ajena = await ajeno.get(f"/me/pedidos/{codigo_ajeno}")
    respuesta_inexistente = await ajeno.get("/me/pedidos/FF-999999999")
    respuesta_invalida = await ajeno.get("/me/pedidos/nada")
    assert respuesta_ajena.status_code == 404
    assert respuesta_inexistente.status_code == 404
    assert respuesta_invalida.status_code == 404
    assert respuesta_ajena.json() == respuesta_inexistente.json() == respuesta_invalida.json()

    # El dueño sí obtiene el detalle de su pedido.
    respuesta = await dueno.get(f"/me/pedidos/{codigo_ajeno}")
    assert respuesta.status_code == 200
    detalle = respuesta.json()
    assert (detalle["codigo"], detalle["estado"], detalle["monto"]) == (
        codigo_ajeno,
        "EXITOSO",
        "0.75",
    )
