from core.domain import CATEGORY_FOLDERS, HOSPITALS, SIGLAS, folder_to_sigla, sigla_to_folder


def test_hospitals_are_the_four_codes():
    assert HOSPITALS == ("HPV", "HRB", "HLU", "HLL")


def test_siglas_are_the_18_canonical():
    expected = (
        "reunion",
        "irl",
        "odi",
        "charla",
        "chintegral",
        "dif_pts",
        "art",
        "insgral",
        "bodega",
        "maquinaria",
        "ext",
        "senal",
        "exc",
        "altura",
        "caliente",
        "herramientas_elec",
        "andamios",
        "chps",
    )
    assert SIGLAS == expected
    assert len(SIGLAS) == 18


def test_category_folders_map_to_numbered_names():
    assert CATEGORY_FOLDERS["reunion"] == "1.-Reunion Prevencion"
    assert CATEGORY_FOLDERS["art"] == "7.-ART"
    assert CATEGORY_FOLDERS["chps"] == "18.-CHPS"
    assert len(CATEGORY_FOLDERS) == 18


def test_sigla_to_folder_and_back():
    for sigla in SIGLAS:
        folder = sigla_to_folder(sigla)
        assert folder_to_sigla(folder) == sigla
        # also accepts " 0" suffix used for empty categories
        assert folder_to_sigla(folder + " 0") == sigla
        assert folder_to_sigla(folder + " 934") == sigla


def test_folder_to_sigla_unknown_returns_none():
    assert folder_to_sigla("99.-Unknown Category") is None
