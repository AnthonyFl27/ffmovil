from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Numeric
from sqlalchemy.orm import DeclarativeBase

# Nombres de restricciones estables para que Alembic genere migraciones reproducibles.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def valores_sql(valores: tuple[str, ...]) -> str:
    """Lista para `CHECK (columna IN (...))`."""
    return ", ".join(f"'{v}'" for v in valores)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)
    # Fechas en UTC con zona (RNF-09); montos NUMERIC(12,2), nunca float (RNF-04).
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        Decimal: Numeric(12, 2),
    }
