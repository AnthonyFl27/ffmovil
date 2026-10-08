from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from tests.conftest import ESQUEMA_TEST, RAIZ


async def test_conexion_usa_esquema_test(motor_bd):
    async with motor_bd.connect() as conexion:
        esquema = (await conexion.execute(text("SELECT current_schema()"))).scalar()
    assert esquema == ESQUEMA_TEST


async def test_migraciones_aplicadas_en_esquema_test(motor_bd):
    config = Config()
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    async with motor_bd.connect() as conexion:
        version = (
            await conexion.execute(
                text(f'SELECT version_num FROM "{ESQUEMA_TEST}".alembic_version')
            )
        ).scalar()
    assert version == head
