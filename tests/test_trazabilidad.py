"""T-083: trazabilidad de la spec (sin BD). Cada requisito vigente tiene tarea y prueba."""

from pathlib import Path

from tests import trazabilidad


def test_todo_requisito_tiene_tarea_y_prueba():
    assert trazabilidad.problemas() == []


def test_detecta_huecos(tmp_path: Path):
    (tmp_path / "sdd").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "sdd" / "spec.md").write_text(
        "- **RF-01** Uno.\n- **RF-02** Dos.\n- **RF-03** Tres (retirado, CHG-099).\n"
        "- **RN-01** Regla.\n",
        encoding="utf-8",
    )
    (tmp_path / "sdd" / "tasks.md").write_text(
        "- [x] T-001 Hace (RF-01, RN-01) → ok\n- [x] T-002 Sin refs → ok\n- [x] T-003 Cita (RF-03)\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_a.py").write_text('"""RF-01."""\n', encoding="utf-8")
    assert trazabilidad.problemas(tmp_path) == [
        "RF-02: sin tarea en sdd/tasks.md",
        "RF-02: sin prueba que lo nombre en tests/",
        "RN-01: sin prueba que lo nombre en tests/",
        "T-002: la tarea no cita ningún requisito",
        "T-003: cita RF-03, que no existe en la spec (o está retirado)",
    ]


def test_expande_rangos():
    assert trazabilidad.ids_en("(RF-50 a RF-52, CA-02 a CA-04)") == {
        "RF-50", "RF-51", "RF-52", "CA-02", "CA-03", "CA-04",
    }  # fmt: skip
