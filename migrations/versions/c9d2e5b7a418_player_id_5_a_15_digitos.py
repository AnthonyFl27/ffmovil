"""player_id_5_a_15_digitos

Revision ID: c9d2e5b7a418
Revises: b3f8a1d6c492
Create Date: 2026-10-14 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d2e5b7a418"
down_revision: str | Sequence[str] | None = "b3f8a1d6c492"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOMBRE = "ck_pedidos_player_id_formato"


def upgrade() -> None:
    """Upgrade schema."""
    # RF-27 (CHG-028, T-130): el Player ID pasa de 4-20 a 5-15 dígitos.
    op.drop_constraint(op.f(NOMBRE), "pedidos", type_="check")
    op.create_check_constraint(op.f(NOMBRE), "pedidos", "player_id ~ '^[0-9]{5,15}$'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f(NOMBRE), "pedidos", type_="check")
    op.create_check_constraint(op.f(NOMBRE), "pedidos", "player_id ~ '^[0-9]{4,20}$'")
