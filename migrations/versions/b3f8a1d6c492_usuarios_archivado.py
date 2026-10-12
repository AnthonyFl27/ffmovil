"""usuarios_archivado

Revision ID: b3f8a1d6c492
Revises: 7c4e1a9b2d05
Create Date: 2026-10-12 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f8a1d6c492"
down_revision: str | Sequence[str] | None = "7c4e1a9b2d05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Retiro lógico de clientes (RF-60, CHG-026).
    op.add_column(
        "usuarios",
        sa.Column("archivado", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("usuarios", "archivado")
