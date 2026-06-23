from pathlib import Path

from core.orchestrator import enumerate_month

ABRIL = Path("A:/informe mensual/ABRIL")


def test_enumerate_month_returns_4_hospitals():
    inv = enumerate_month(ABRIL)
    assert sorted(inv.hospitals_present) == ["HLL", "HLU", "HPV", "HRB"]
    assert not inv.hospitals_missing


def test_enumerate_month_populates_18_categories_per_hospital():
    inv = enumerate_month(ABRIL)
    for hosp in ("HPV", "HRB", "HLU", "HLL"):
        assert len(inv.cells[hosp]) == 18


def test_enumerate_month_returns_zero_for_missing_category(tmp_path):
    (tmp_path / "HPV").mkdir()  # empty hospital folder
    inv = enumerate_month(tmp_path)
    assert "HPV" in inv.hospitals_present
    # all 18 categories should be present (as missing folders)
    assert len(inv.cells["HPV"]) == 18


def test_find_category_folder_resolves_renumbered_corpus(tmp_path):
    from core.domain import SIGLAS
    from core.orchestrator import _find_category_folder

    hosp = tmp_path / "HRB"
    # The current 20-folder disk layout (two inserted categories shift exc..chps).
    layout = [
        "1.-Reunion Prevencion",
        "2.-Induccion IRL",
        "3.-ODI Visitas",
        "4.-Charlas",
        "5.-Charla Integral",
        "6.-Difusion PTS",
        "7.-ART",
        "8.-Inspecciones Generales",
        "9.-Inspeccion Bodega",
        "10.-Inspeccion de Maquinaria",
        "11.-Extintores",
        "12.-Senaleticas",
        "13.-Revision Documentacion Maquinaria",
        "14.-Excavaciones y Vanos",
        "15.-Trabajos en Altura",
        "16.-Inspeccion Trabajos en Caliente",
        "17.-Espacios Confinados",
        "18.-Inspeccion Herramientas Electricas",
        "19.-Andamios",
        "20.-CPHS",
    ]
    for name in layout:
        (hosp / name).mkdir(parents=True)

    # the six shifted/renamed siglas resolve to the right on-disk folder
    assert _find_category_folder(hosp, "exc").name == "14.-Excavaciones y Vanos"
    assert _find_category_folder(hosp, "altura").name == "15.-Trabajos en Altura"
    assert _find_category_folder(hosp, "caliente").name == "16.-Inspeccion Trabajos en Caliente"
    assert (
        _find_category_folder(hosp, "herramientas_elec").name
        == "18.-Inspeccion Herramientas Electricas"
    )
    assert _find_category_folder(hosp, "andamios").name == "19.-Andamios"
    assert _find_category_folder(hosp, "chps").name == "20.-CPHS"
    # pre-senal siglas unaffected
    assert _find_category_folder(hosp, "art").name == "7.-ART"
    assert _find_category_folder(hosp, "maquinaria").name == "10.-Inspeccion de Maquinaria"
    # the two unmodeled folders are never returned for any sigla
    returned = {_find_category_folder(hosp, s).name for s in SIGLAS}
    assert "13.-Revision Documentacion Maquinaria" not in returned
    assert "17.-Espacios Confinados" not in returned


def test_find_category_folder_absent_hospital_returns_nominal(tmp_path):
    from core.orchestrator import _find_category_folder

    missing = tmp_path / "NOPE"
    p = _find_category_folder(missing, "caliente")
    assert not p.exists()
    assert p.name == "15.-Inspeccion Trabajos en Caliente"  # nominal canonical
