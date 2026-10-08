"""movimientos solo insercion

Revision ID: cab77db53d96
Revises: 11795042fb1b
Create Date: 2026-10-08 13:03:46.630970

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cab77db53d96"
down_revision: str | Sequence[str] | None = "11795042fb1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# RF-42: el libro contable es de solo inserción. El trigger aplica aunque la app
# se conecte con el dueño de la tabla (a diferencia de un REVOKE).
def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE FUNCTION movimientos_solo_insercion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'movimientos es de solo inserción (RF-42): % no permitido', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER movimientos_sin_update_delete
        BEFORE UPDATE OR DELETE ON movimientos
        FOR EACH ROW EXECUTE FUNCTION movimientos_solo_insercion()
        """
    )
    op.execute(
        """
        CREATE TRIGGER movimientos_sin_truncate
        BEFORE TRUNCATE ON movimientos
        FOR EACH STATEMENT EXECUTE FUNCTION movimientos_solo_insercion()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER movimientos_sin_truncate ON movimientos")
    op.execute("DROP TRIGGER movimientos_sin_update_delete ON movimientos")
    op.execute("DROP FUNCTION movimientos_solo_insercion()")
