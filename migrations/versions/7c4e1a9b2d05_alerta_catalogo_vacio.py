"""alerta_catalogo_vacio

Revision ID: 7c4e1a9b2d05
Revises: ea509abd049b
Create Date: 2026-10-10 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c4e1a9b2d05"
down_revision: str | Sequence[str] | None = "ea509abd049b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Añade el tipo de alerta "catalogo_vacio" (sincronización con productos vacíos).
    op.drop_constraint(op.f("ck_alertas_tipo"), "alertas", type_="check")
    op.create_check_constraint(
        op.f("ck_alertas_tipo"),
        "alertas",
        "tipo IN ('credito_bajo', 'sin_credito', 'cuenta', 'catalogo_vacio')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Las alertas de este tipo no existen en la versión anterior: se eliminan antes
    # de restaurar el CHECK con los tres tipos originales.
    op.execute("DELETE FROM alertas WHERE tipo = 'catalogo_vacio'")
    op.drop_constraint(op.f("ck_alertas_tipo"), "alertas", type_="check")
    op.create_check_constraint(
        op.f("ck_alertas_tipo"),
        "alertas",
        "tipo IN ('credito_bajo', 'sin_credito', 'cuenta')",
    )
