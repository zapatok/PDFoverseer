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


def test_folder_to_sigla_current_disk_numbering():
    # 20-folder corpus: exc..andamios shifted, chps spelled CPHS
    assert folder_to_sigla("14.-Excavaciones y Vanos") == "exc"
    assert folder_to_sigla("15.-Trabajos en Altura") == "altura"
    assert folder_to_sigla("16.-Inspeccion Trabajos en Caliente") == "caliente"
    assert folder_to_sigla("18.-Inspeccion Herramientas Electricas") == "herramientas_elec"
    assert folder_to_sigla("19.-Andamios") == "andamios"
    assert folder_to_sigla("20.-CPHS") == "chps"


def test_folder_to_sigla_legacy_numbering_still_works():
    assert folder_to_sigla("13.-Excavaciones y Vanos") == "exc"
    assert folder_to_sigla("18.-CHPS") == "chps"


def test_folder_to_sigla_compound_name_with_suffix():
    assert folder_to_sigla("4.-Charlas 0") == "charla"
    assert folder_to_sigla("5.-Charla Integral 0") == "chintegral"


def test_folder_to_sigla_unmodeled_corpus_folders_return_none():
    assert folder_to_sigla("13.-Revision Documentacion Maquinaria") is None
    assert folder_to_sigla("17.-Espacios Confinados") is None


def test_folder_match_texts_pairwise_distinct():
    # Load-bearing no-collision guarantee for the startswith(+" ") predicate.
    from core.domain import CATEGORY_FOLDERS, _SIGLA_FOLDER_ALIASES, _folder_text

    texts = [_folder_text(v) for v in CATEGORY_FOLDERS.values()]
    for aliases in _SIGLA_FOLDER_ALIASES.values():
        texts.extend(aliases)
    for i, a in enumerate(texts):
        for j, b in enumerate(texts):
            if i == j:
                continue
            assert a != b, f"duplicate match text: {a!r}"
            assert not a.startswith(b + " "), f"{a!r} starts with {b!r} + ' '"
