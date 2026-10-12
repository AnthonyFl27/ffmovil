"""T-129: filtros del listado de usuarios, API y web (RF-61, RF-60, RF-07, RNF-12)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import update

from app.models import Usuario
from app.services import ledger
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import htmx_get


def fecha(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


async def preparar(api, sesion_bd):
    """Admin con sesión y tres clientes con nombres y datos conocidos (prefijo único).

    - `a_b`: activo, con saldo, debe cambiar clave, entró el 10-mar, creado el 5-ene.
    - `axb`: bloqueado, sin saldo, nunca entró, creado el 10-feb.
    - `zed`: activo, sin saldo, entró el 1-abr a las 00:00, creado el 1-mar a las 00:00.
    """
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    etiqueta = uuid.uuid4().hex[:8]
    # sufijo: (activo, debe cambiar clave, último login, creado)
    datos = {
        "a_b": (True, True, fecha(2026, 3, 10, 12), fecha(2026, 1, 5, 12)),
        "axb": (False, False, None, fecha(2026, 2, 10, 12)),
        "zed": (True, False, fecha(2026, 4, 1), fecha(2026, 3, 1)),
    }
    ids = {}
    for sufijo, (activo, debe, login, creado) in datos.items():
        cliente = await crear_usuario_con_clave(sesion_bd)
        await sesion_bd.execute(
            update(Usuario)
            .where(Usuario.id == cliente.id)
            .values(
                usuario=f"{etiqueta}{sufijo}",
                activo=activo,
                debe_cambiar_clave=debe,
                ultimo_login=login,
                creado_en=creado,
            )
        )
        ids[sufijo] = cliente.id
    await ledger.abonar(sesion_bd, ids["a_b"], Decimal("5.00"), nota="Abono", creado_por=admin.id)
    await sesion_bd.commit()
    http = api()
    await iniciar_sesion(http, admin.usuario)
    return http, admin, etiqueta, ids


async def nombres(http, etiqueta, **params):
    """Sufijos de los clientes de la prueba que devuelve el listado con esos filtros."""
    respuesta = await http.get("/admin/usuarios", params={"q": etiqueta} | params)
    assert respuesta.status_code == 200, respuesta.text
    return {u["usuario"].removeprefix(etiqueta.lower()) for u in respuesta.json()}


async def test_busqueda_parcial_sin_distinguir_mayusculas(api, sesion_bd):
    http, _, etiqueta, _ = await preparar(api, sesion_bd)
    assert await nombres(http, etiqueta) == {"a_b", "axb", "zed"}
    assert await nombres(http, etiqueta, q=etiqueta.upper()) == {"a_b", "axb", "zed"}
    assert await nombres(http, etiqueta, q=f"{etiqueta}ZE") == {"zed"}
    # Sin texto no filtra.
    sin_q = await http.get("/admin/usuarios")
    assert sin_q.status_code == 200 and len(sin_q.json()) >= 3


async def test_guion_bajo_y_porcentaje_son_literales(api, sesion_bd):
    http, _, etiqueta, _ = await preparar(api, sesion_bd)
    # `_` no es comodín: `a_b` no encuentra `axb`; `%` no encuentra nada.
    assert await nombres(http, etiqueta, q=f"{etiqueta}a_b") == {"a_b"}
    assert await nombres(http, etiqueta, q=f"{etiqueta}%") == set()
    assert await nombres(http, etiqueta, q=f"{etiqueta}a%b") == set()


async def test_estado_saldo_y_cambio_de_clave(api, sesion_bd):
    http, admin, etiqueta, _ = await preparar(api, sesion_bd)
    assert await nombres(http, etiqueta, estado="activo") == {"a_b", "zed"}
    assert await nombres(http, etiqueta, estado="bloqueado") == {"axb"}
    assert await nombres(http, etiqueta, con_saldo="true") == {"a_b"}
    assert await nombres(http, etiqueta, con_saldo="false") == {"axb", "zed"}
    assert await nombres(http, etiqueta, debe_cambiar_clave="true") == {"a_b"}
    assert await nombres(http, etiqueta, debe_cambiar_clave="false") == {"axb", "zed"}
    # Un admin no tiene cuenta de saldo: cuenta como «sin saldo».
    propio = await http.get("/admin/usuarios", params={"q": admin.usuario, "con_saldo": "false"})
    assert [u["usuario"] for u in propio.json()] == [admin.usuario]


async def test_rangos_de_login_y_de_creacion(api, sesion_bd):
    http, _, etiqueta, _ = await preparar(api, sesion_bd)
    # `hasta` es exclusivo: `zed` entró exactamente el 1-abr a las 00:00 y queda fuera.
    marzo = {"login_desde": "2026-03-01T00:00:00Z", "login_hasta": "2026-04-01T00:00:00Z"}
    assert await nombres(http, etiqueta, **marzo) == {"a_b"}
    # Quien nunca entró no coincide con ningún rango de login.
    assert await nombres(http, etiqueta, login_desde="2000-01-01T00:00:00Z") == {"a_b", "zed"}
    febrero = {"creado_desde": "2026-02-01T00:00:00Z", "creado_hasta": "2026-03-01T00:00:00Z"}
    assert await nombres(http, etiqueta, **febrero) == {"axb"}
    assert await nombres(http, etiqueta, creado_desde="2026-02-10T12:00:00Z") == {"axb", "zed"}


async def test_filtros_combinados_y_con_archivados(api, sesion_bd):
    http, _, etiqueta, ids = await preparar(api, sesion_bd)
    assert await nombres(http, etiqueta, estado="activo", con_saldo="false") == {"zed"}
    assert await nombres(http, etiqueta, estado="activo", con_saldo="false", q=f"{etiqueta}a") == (
        set()
    )

    await sesion_bd.execute(update(Usuario).where(Usuario.id == ids["zed"]).values(archivado=True))
    await sesion_bd.commit()
    assert await nombres(http, etiqueta, estado="activo", con_saldo="false") == set()
    assert await nombres(http, etiqueta, archivados="true", con_saldo="false") == {"zed"}
    assert await nombres(http, etiqueta, archivados="true", con_saldo="true") == set()


async def test_valores_invalidos_son_422(api, sesion_bd):
    http, *_ = await preparar(api, sesion_bd)
    assert (await http.get("/admin/usuarios", params={"q": "x" * 30})).status_code == 200
    for params in (
        {"q": "x" * 31},
        {"estado": "archivado"},
        {"con_saldo": "quizas"},
        {"debe_cambiar_clave": "tal vez"},
        {"login_desde": "ayer"},
        {"creado_hasta": "2026-13-45"},
    ):
        respuesta = await http.get("/admin/usuarios", params=params)
        assert respuesta.status_code == 422, params


async def test_web_filtra_y_devuelve_solo_la_tabla(api, sesion_bd):
    http, _, etiqueta, _ = await preparar(api, sesion_bd)

    parcial = await htmx_get(
        http, "/gestion/usuarios", destino="tabla-usuarios", q=f"{etiqueta}a", estado="activo"
    )
    assert parcial.status_code == 200
    assert "<html" not in parcial.text and f"{etiqueta}a_b" in parcial.text
    assert f"{etiqueta}axb" not in parcial.text and f"{etiqueta}zed" not in parcial.text

    # Fechas por día local (con `tz`); `hasta` incluye todo ese día.
    dia = await htmx_get(
        http,
        "/gestion/usuarios",
        destino="tabla-usuarios",
        q=etiqueta,
        creado_desde="2026-02-10",
        creado_hasta="2026-02-10",
        tz="0",
    )
    assert f"{etiqueta}axb" in dia.text and f"{etiqueta}a_b" not in dia.text
    assert f"{etiqueta}zed" not in dia.text

    vacio = await htmx_get(http, "/gestion/usuarios", destino="tabla-usuarios", q=f"{etiqueta}qq")
    assert "No hay usuarios con estos filtros." in vacio.text

    largo = await htmx_get(http, "/gestion/usuarios", destino="tabla-usuarios", q="x" * 31)
    assert largo.status_code == 422
    mala = await htmx_get(http, "/gestion/usuarios", destino="tabla-usuarios", creado_desde="ayer")
    assert mala.status_code == 422


async def test_web_formulario_plegado_en_vivo_y_con_creado(api, sesion_bd):
    http, _, etiqueta, _ = await preparar(api, sesion_bd)

    pagina = await http.get("/gestion/usuarios")
    html = pagina.text
    # Plegado sin filtros; búsqueda en vivo con un solo disparador y «Filtrar» de respaldo.
    assert (
        '<details class="filtros">' in html
        and '<summary role="button" class="outline secondary">Filtros</summary>' in html
    )
    assert 'hx-trigger="submit, input delay:300ms"' in html
    assert 'hx-target="#tabla-usuarios"' in html and 'hx-push-url="true"' in html
    for campo in (
        'name="q"',
        'name="estado"',
        'name="con_saldo"',
        'name="debe_cambiar_clave"',
        'name="login_desde"',
        'name="login_hasta"',
        'name="creado_desde"',
        'name="creado_hasta"',
        'name="tz"',
    ):
        assert campo in html, campo
    assert "Filtrar</button>" in html and "Quitar filtros</a>" in html
    assert 'href="/gestion/usuarios"' in html and 'name="archivados"' not in html
    assert "<th>Creado</th>" in html

    # Con un filtro aplicado va abierto y conserva los valores.
    filtrada = await http.get("/gestion/usuarios", params={"q": etiqueta, "estado": "bloqueado"})
    assert '<details class="filtros" open>' in filtrada.text
    assert f'value="{etiqueta}"' in filtrada.text and 'value="bloqueado" selected' in filtrada.text

    # «Ver archivados» se conserva al filtrar y al quitar los filtros.
    archivados = await http.get("/gestion/usuarios", params={"archivados": "1"})
    assert '<input type="hidden" name="archivados" value="1">' in archivados.text
    assert 'href="/gestion/usuarios?archivados=1">Quitar filtros' in archivados.text
