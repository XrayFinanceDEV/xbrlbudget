"""M2-02B (worker S2) — tabelle F/G, ipotesi e metodologia senza motivazione
per riga (rilievi 2, 3, 4, 6 di `.superpowers/sdd/2026-09-17-dossier-v4/m2-02b-s2.md`).

Questi test verificano solo l'inventario editoriale (`editorial_inventory.py`):
la resa fisica delle pagine resta responsabilità dei template `.typ`, non
toccati qui.
"""
from app.renderers.typst.editorial_inventory import build_inventory
from tests.test_final_report_v2 import fixture_report


def _items(inventory):
    return [item for section in inventory for item in section["items"]]


def _tables(inventory):
    return {item["id"]: item for item in _items(inventory) if item["kind"] == "table"}


def _texts(inventory):
    return {item["id"]: item for item in _items(inventory) if item["kind"] == "text"}


def _notes(inventory):
    # Le note di indisponibilità raggruppate sono un kind a parte («note»),
    # senza titolo di sezione: distinte dai blocchi narrativi/di convenzione,
    # che restano «text» (M2-02B integrazione, rilievo 3).
    return {item["id"]: item for item in _items(inventory) if item["kind"] == "note"}


# ── Rilievo 3 — Tabelle F e G ────────────────────────────────────────────────

def test_tabelle_f_g_hanno_indicatore_come_prima_colonna_senza_unita_separata():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    inventory = build_inventory(report)
    tables = _tables(inventory)

    for table_id in ("indicator-practice-table", "indicator-analytical-table"):
        table = tables[table_id]
        assert table["columns"][0] == "Indicatore"
        assert "Unità" not in table["columns"]
        # value_start=1: il template usa lo stesso ramo a etichetta singola di
        # ogni altra tabella periodica (mai più «value-start == 2», la causa
        # storica dell'intestazione «Unità» al posto di «Indicatore»).
        assert table["value_start"] == 1


def test_tabelle_f_g_portano_unita_fra_parentesi_nell_etichetta():
    report = fixture_report("infrannuale", [2027])
    inventory = build_inventory(report)
    tables = _tables(inventory)
    labels = {row["cells"][0] for table in tables.values() if table["id"].startswith("indicator-")
              for row in table["rows"]}
    # Ogni indicatore col relativo `unit` dichiarato porta l'unità fra
    # parentesi nell'etichetta (M2-02B rilievo 3: «tra parentesi
    # nell'etichetta», l'alternativa esplicitamente ammessa alla cella, che
    # richiederebbe un formattatore di unità nel template).
    assert any(label.endswith("(%)") for label in labels)
    assert any(label.endswith("(volte)") for label in labels)


def test_tabelle_f_g_non_hanno_motivazione_per_riga_ma_nota_raggruppata_dopo():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    inventory = build_inventory(report)
    tables = _tables(inventory)
    notes = _notes(inventory)

    for table_id, note_id in (
        ("indicator-practice-table", "indicator-practice-table:unavailable"),
        ("indicator-analytical-table", "indicator-analytical-table:unavailable"),
    ):
        table = tables[table_id]
        # L'ultima colonna resta riservata (il template la esclude dal
        # conteggio dei periodi), ma nessuna riga porta più un testo lì:
        # niente motivazione ripetuta sotto ogni indicatore.
        assert table["columns"][-1] == "Indisponibilità"
        assert all(row["cells"][-1] is None for row in table["rows"])
        # Il fixture ha indicatori non disponibili: la nota raggruppata esiste,
        # è un item «note» senza titolo (M2-02B integrazione, rilievo 3, non più
        # «Indisponibilità — Tabella F» come sezione), e cita la ragione una
        # volta sola per intervallo di periodi contigui, non una riga per
        # indicatore né una frase per periodo.
        if any(row["cells"][-2] is None for row in table["rows"] if len(row["cells"]) > 1):
            assert note_id in notes
            note = notes[note_id]
            assert "title" not in note
            # Il vecchio formato «periodo — motivazione» (una frase per riga
            # per periodo, es. «2027 (12 mesi) — calcolo sorgente non
            # disponibile: ...») non compare più: la nota raggruppa per voce
            # e intervallo di periodi contigui, il periodo sta fra parentesi
            # in coda alla frase, non subito dopo l'etichetta del periodo.
            assert "mesi) — " not in note["text"]


def test_content_ids_includono_le_note_raggruppate_una_sola_volta():
    report = fixture_report("infrannuale", [2027])
    from app.renderers.typst.editorial_inventory import expected_content_inventory
    inventory = build_inventory(report)
    notes = _notes(inventory)
    expected = expected_content_inventory(report)
    for note_id in notes:
        if note_id.endswith(":unavailable"):
            assert list(expected).count(note_id) == 1


# ── Rilievo 4 — Metodologia e convenzioni ────────────────────────────────────

def test_tabella_metodologia_e_compatta_indicatore_metodologia():
    report = fixture_report("bilancio", [2027])
    inventory = build_inventory(report)
    table = _tables(inventory)["indicator-methodology"]
    assert table["columns"] == ["Indicatore", "Metodologia"]
    for row in table["rows"]:
        assert len(row["cells"]) == 2


def test_famiglia_e_soglie_non_si_stampano_piu():
    report = fixture_report("bilancio", [2027])
    inventory = build_inventory(report)
    flattened_cells = "\n".join(str(cell) for item in _items(inventory) if item["kind"] == "table"
                                for row in item["rows"] for cell in row["cells"] if cell is not None)
    flattened_titles = "\n".join(item.get("title", "") for item in _items(inventory))
    assert "Famiglia:" not in flattened_cells
    assert "Soglie:" not in flattened_cells
    assert "Famiglia" not in _tables(inventory)["indicator-methodology"]["columns"]
    assert "Soglie" not in _tables(inventory)["indicator-methodology"]["columns"]
    assert flattened_titles  # sanity: qualche titolo esiste comunque


def test_convenzione_scritta_una_volta_come_testo_prima_della_tabella():
    report = fixture_report("bilancio", [2027])
    inventory = build_inventory(report)
    items = _items(inventory)
    conventions = [item for item in items if item["id"].startswith("indicator-methodology:convention:")]
    methodology_index = next(i for i, item in enumerate(items) if item["id"] == "indicator-methodology")
    assert conventions  # esiste almeno una nota di convenzione
    for convention in conventions:
        assert items.index(convention) < methodology_index
    # Le convenzioni distinte dichiarate dal modello (pratica vs analitica)
    # restano entrambe: nessuna si scarta silenziosamente.
    distinct_texts = {item["text"] for item in conventions}
    assert len(distinct_texts) == len(conventions)


# ── Rilievo 6 — Tabelle delle ipotesi ────────────────────────────────────────

def test_tabelle_ipotesi_non_hanno_colonna_indisponibilita():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    inventory = build_inventory(report)
    for table_id, table in _tables(inventory).items():
        if table_id.startswith("assumptions:") and not table_id.endswith(":details"):
            assert "Indisponibilità" not in table["columns"]
            for row in table["rows"]:
                assert len(row["cells"]) == len(table["columns"])


def test_tabelle_ipotesi_con_valori_mancanti_hanno_nota_raggruppata_dopo():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    inventory = build_inventory(report)
    items = _items(inventory)
    notes = _notes(inventory)

    costi_index = next(i for i, item in enumerate(items) if item["id"] == "assumptions:costi")
    note_id = "assumptions:costi:unavailable"
    assert note_id in notes
    assert items.index(notes[note_id]) == costi_index + 1  # subito dopo la tabella
    assert "title" not in notes[note_id]  # nessun titolo di sezione (M2-02B integrazione, rilievo 3)
    # Compattata per voce e per intervallo di anni contigui, non una frase per
    # anno: «Non dichiarati: <voce> (<primo>–<ultimo>).», non «valore non
    # dichiarato per 2027: ... valore non dichiarato per 2028: ...».
    assert notes[note_id]["text"] == "Non dichiarati: Override CE (2027–2029)."


def test_tabelle_ipotesi_senza_valori_mancanti_non_hanno_nota():
    report = fixture_report("bilancio", [2027])
    inventory = build_inventory(report)
    items = _items(inventory)
    notes = _notes(inventory)
    fatturato_index = next(i for i, item in enumerate(items) if item["id"] == "assumptions:fatturato")
    # Nel fixture "bilancio" a un anno la crescita ricavi è dichiarata: nessuna
    # nota da aggiungere, la tabella non è seguita da un blocco di note.
    assert "assumptions:fatturato:unavailable" not in notes
    assert items[fatturato_index + 1]["kind"] != "note" or not items[fatturato_index + 1]["id"].startswith("assumptions:fatturato:unavailable")


# ── Rilievo 2 — Blocchi narrativi senza testo vero ───────────────────────────

def test_blocco_narrativo_segnaposto_non_entra_nell_inventario():
    report = fixture_report("infrannuale", [2027])
    # Il fixture porta segnaposto di una sola parola per tutti i narrativi.
    assert all(len((n.text or "").split()) < 2 for n in report.narrative)
    inventory = build_inventory(report)
    texts = _texts(inventory)
    narrative_ids = {"executive_summary", "adjustments_and_closing", "budget_assumptions",
                      "economic_outlook", "financial_outlook", "risks_and_actions"}
    assert not (narrative_ids & set(texts))


def test_blocco_narrativo_con_testo_vero_entra_nell_inventario():
    report = fixture_report("infrannuale", [2027])
    report.narrative[0].text = "Un commento vero con più di una parola."
    inventory = build_inventory(report)
    texts = _texts(inventory)
    assert report.narrative[0].id in texts
    assert texts[report.narrative[0].id]["text"] == "Un commento vero con più di una parola."
