"""T-134: sección «Updates» del admin (RF-63, CA-13).

RF-63, RF-55, RNF-03, RNF-06, CA-13: servicio que valida `app/updates.json`, API y página web.
"""

import json
import re

import pytest

from app.main import app
from app.services.updates import RUTA_UPDATES, cargar_updates
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion

UNA = {"fecha": "2026-10-15", "titulo": "Algo nuevo", "puntos": ["Primer punto."]}


def _archivo(tmp_path, datos):
    ruta = tmp_path / "updates.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


# --- Servicio (RF-63) ------------------------------------------------------------------


def test_el_archivo_del_repositorio_es_valido():
    """CA-13: el `updates.json` real carga, trae novedades y no contiene datos sensibles."""
    updates = cargar_updates()
    assert updates
    assert [u.fecha for u in updates] == sorted((u.fecha for u in updates), reverse=True)
    texto = RUTA_UPDATES.read_text(encoding="utf-8").lower()
    assert "costo" not in texto and "api key" not in texto and "rv_c_" not in texto


def test_ordena_de_la_mas_reciente_a_la_mas_antigua_y_respeta_el_orden_del_dia(tmp_path):
    ruta = _archivo(
        tmp_path,
        [
            {**UNA, "fecha": "2026-10-01", "titulo": "Vieja"},
            {**UNA, "fecha": "2026-10-15", "titulo": "Primera del día"},
            {**UNA, "fecha": "2026-10-15", "titulo": "Segunda del día"},
            {**UNA, "fecha": "2026-10-10", "titulo": "Media"},
        ],
    )
    assert [u.titulo for u in cargar_updates(ruta)] == [
        "Primera del día",
        "Segunda del día",
        "Media",
        "Vieja",
    ]


def test_recorta_espacios_y_admite_lista_vacia(tmp_path):
    ruta = _archivo(tmp_path, [{**UNA, "titulo": "  Con aire  ", "puntos": ["  Punto  "]}])
    (update,) = cargar_updates(ruta)
    assert (update.titulo, update.puntos) == ("Con aire", ["Punto"])
    assert cargar_updates(_archivo(tmp_path, [])) == []


@pytest.mark.parametrize(
    "dato",
    [
        {**UNA, "fecha": "15/10/2026"},
        {**UNA, "fecha": "2026-13-40"},
        {**UNA, "fecha": 20261015},
        {**UNA, "titulo": "   "},
        {**UNA, "puntos": []},
        {**UNA, "puntos": ["  "]},
        {**UNA, "puntos": "no es una lista"},
        {**UNA, "extra": "campo desconocido"},
        {"fecha": "2026-10-15", "titulo": "Sin puntos"},
        "no es un objeto",
    ],
)
def test_un_archivo_invalido_se_rechaza_con_mensaje_claro(tmp_path, dato):
    with pytest.raises(ValueError, match="updates.json inválido"):
        cargar_updates(_archivo(tmp_path, [dato]))


def test_archivo_faltante_o_que_no_es_json_se_rechaza(tmp_path):
    with pytest.raises(ValueError, match="No se pudo leer"):
        cargar_updates(tmp_path / "no_existe.json")
    malo = tmp_path / "updates.json"
    malo.write_text("{no es json", encoding="utf-8")
    with pytest.raises(ValueError, match="no es JSON válido"):
        cargar_updates(malo)
    with pytest.raises(ValueError, match="inválido"):
        cargar_updates(_archivo(tmp_path, {"fecha": "2026-10-15"}))


# --- API y web (RF-63, RNF-03) -----------------------------------------------------------


@pytest.fixture
def novedades(tmp_path):
    """Dos novedades en el estado de la app (una con HTML para comprobar el escapado)."""
    anteriores = app.state.updates
    app.state.updates = cargar_updates(
        _archivo(
            tmp_path,
            [
                {**UNA, "fecha": "2026-10-01", "titulo": "Antigua", "puntos": ["Uno", "Dos"]},
                {
                    "fecha": "2026-10-15",
                    "titulo": "<script>alert(1)</script>",
                    "puntos": ["<b>negrita</b> & más"],
                },
            ],
        )
    )
    yield app.state.updates
    app.state.updates = anteriores


async def test_admin_ve_las_updates_por_api(api, sesion_bd, novedades):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    http = api()
    await iniciar_sesion(http, admin.usuario)
    r = await http.get("/admin/updates")
    assert r.status_code == 200
    titulos = [u["titulo"] for u in r.json()["updates"]]
    assert titulos == ["<script>alert(1)</script>", "Antigua"]
    assert r.json()["updates"][1]["puntos"] == ["Uno", "Dos"]


async def test_cliente_y_anonimo_no_ven_las_updates(api, sesion_bd, novedades):
    cliente = await crear_usuario_con_clave(sesion_bd)
    http = api()
    assert (await http.get("/admin/updates")).status_code == 401
    assert (await http.get("/gestion/updates", follow_redirects=False)).status_code == 303
    await iniciar_sesion(http, cliente.usuario)
    assert (await http.get("/admin/updates")).status_code == 403
    r = await http.get("/gestion/updates", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/inicio")


async def test_pagina_muestra_las_updates_escapadas_y_en_orden(api, sesion_bd, novedades):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    http = api()
    await iniciar_sesion(http, admin.usuario)
    r = await http.get("/gestion/updates")
    assert r.status_code == 200
    html = r.text
    assert html.index("Antigua") > html.index("&lt;script&gt;alert(1)&lt;/script&gt;")
    assert "<script>alert(1)" not in html and "<b>negrita</b>" not in html
    assert "&lt;b&gt;negrita&lt;/b&gt; &amp; más" in html
    assert '<time datetime="2026-10-15">15/10/2026</time>' in html
    assert html.count('<article class="update">') == 2
    # «Auditoría» queda resaltada en el menú (en línea y plegable).
    resaltadas = re.findall(r'<a href="([^"]+)" aria-current="page"', html)
    assert resaltadas == ["/gestion/auditoria", "/gestion/auditoria"]


async def test_sin_updates_muestra_un_aviso(api, sesion_bd):
    anteriores = app.state.updates
    app.state.updates = []
    try:
        admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
        http = api()
        await iniciar_sesion(http, admin.usuario)
        html = (await http.get("/gestion/updates")).text
    finally:
        app.state.updates = anteriores
    assert "Aún no hay updates." in html and '<article class="update">' not in html


async def test_auditoria_tiene_el_boton_updates(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    http = api()
    await iniciar_sesion(http, admin.usuario)
    html = (await http.get("/gestion/auditoria")).text
    assert 'href="/gestion/updates"' in html
