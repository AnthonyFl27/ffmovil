"""T-034: los esquemas de cliente nunca declaran campos de costo (RF-35, CA-03)."""

import importlib
import json
import pkgutil
import typing
from decimal import Decimal

from pydantic import BaseModel, Field

import app.schemas
from app.models import Paquete
from app.schemas.cliente import PaqueteCliente


def _modelos_cliente() -> list[type[BaseModel]]:
    """Modelos Pydantic definidos en los módulos de `app.schemas` que no son de admin."""
    modelos: list[type[BaseModel]] = []
    for info in pkgutil.iter_modules(app.schemas.__path__):
        if info.name.startswith("admin"):
            continue
        modulo = importlib.import_module(f"{app.schemas.__name__}.{info.name}")
        for obj in vars(modulo).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == modulo.__name__
            ):
                modelos.append(obj)
    return modelos


def _modelos_anidados(anotacion, visto: set[type]) -> list[type[BaseModel]]:
    """Modelos Pydantic alcanzables desde una anotación (`X`, `list[X]`, `X | None`...)."""
    encontrados: list[type[BaseModel]] = []
    if isinstance(anotacion, type) and issubclass(anotacion, BaseModel):
        if anotacion not in visto:
            visto.add(anotacion)
            encontrados.append(anotacion)
            for campo in anotacion.model_fields.values():
                encontrados.extend(_modelos_anidados(campo.annotation, visto))
        return encontrados
    for arg in typing.get_args(anotacion):
        encontrados.extend(_modelos_anidados(arg, visto))
    return encontrados


def campos_prohibidos(modelo: type[BaseModel]) -> list[str]:
    """Campos con "costo" en el nombre o en algún alias, en el modelo y sus anidados.

    Devuelve entradas "Modelo.campo" para cada campo que no debe llegar al cliente.
    """
    prohibidos: list[str] = []
    visto: set[type] = set()
    for modelo_alcanzado in _modelos_anidados(modelo, visto):
        for nombre_campo, campo in modelo_alcanzado.model_fields.items():
            alias = [
                valor
                for valor in (campo.alias, campo.serialization_alias, campo.validation_alias)
                if isinstance(valor, str)
            ]
            if any("costo" in texto.lower() for texto in [nombre_campo, *alias]):
                prohibidos.append(f"{modelo_alcanzado.__name__}.{nombre_campo}")
    return prohibidos


def test_escaneo_encuentra_esquemas_de_cliente():
    modelos = _modelos_cliente()
    assert modelos, "el escaneo no encontró esquemas de cliente"
    assert PaqueteCliente in modelos


def test_ningun_esquema_de_cliente_declara_costo():
    for modelo in _modelos_cliente():
        prohibidos = campos_prohibidos(modelo)
        assert prohibidos == [], (
            f"{modelo.__name__} declara campos de costo prohibidos para el cliente: "
            f"{', '.join(prohibidos)}"
        )


def test_el_comprobador_detecta_costo_anidado():
    class Interno(BaseModel):
        precio_costo: Decimal

    class Externo(BaseModel):
        detalle: Interno | None

    class ConAlias(BaseModel):
        precio: Decimal = Field(alias="precio_costo")

    class Lista(BaseModel):
        items: list[Interno]

    assert campos_prohibidos(Externo) == ["Interno.precio_costo"]
    assert campos_prohibidos(Lista) == ["Interno.precio_costo"]
    assert campos_prohibidos(ConAlias) == ["ConAlias.precio"]


def test_paquete_cliente_no_serializa_costo():
    paquete = Paquete(
        paquete_id=1,
        juego="free_fire",
        nombre="110 Diamantes",
        diamantes=110,
        precio_costo=Decimal("0.50"),
        precio_venta=Decimal("0.75"),
        activo=True,
    )
    cliente = PaqueteCliente.model_validate(paquete)

    dump = cliente.model_dump_json()
    assert "costo" not in dump
    assert "0.50" not in dump
    assert json.loads(dump)["precio_venta"] == "0.75"
    assert cliente.precio_venta == Decimal("0.75")
