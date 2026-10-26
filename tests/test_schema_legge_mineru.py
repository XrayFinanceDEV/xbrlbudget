"""Lo schema di legge di una scansione senza percorso nell'etichetta, dalle tabelle di MinerU
(budget_1322, 2026-10-26): prima finiva sull'estrattore Anthropic, vietato, cioe' su un errore.

Le tabelle sono finte, con la forma vera di MinerU 4: la prima riga di ogni prospetto
intesta le colonne con le date, il prospetto continua su una seconda tabella senza
intestazione, una nota a pie' di pagina sta in mezzo con un'intestazione propria, e una
cella porta il richiamo di nota ("220 (1)").

Run: python -m pytest tests/test_schema_legge_mineru.py -v
"""
from decimal import Decimal as D
from types import SimpleNamespace

from importers import schema_legge_generico as generico
from importers.mineru_adapter import MinerUCell, MinerURow, MinerUTable
from importers.pdf_importer import _dettagli_gia_letti


def _tabella(caption, righe, pagina=0):
    rows = tuple(
        MinerURow(cells=tuple(MinerUCell(text=t, row=i, column=j, page=pagina)
                              for j, t in enumerate(r)), page=pagina, source_block_id=f"b{i}")
        for i, r in enumerate(righe))
    return MinerUTable(html="", caption=caption, page=pagina, rows=rows)


INTESTAZIONE = ["", "31-12-2025", "31-12-2024"]

SP_1 = _tabella("Stato patrimoniale", [
    INTESTAZIONE,
    ["Stato patrimoniale"],
    ["Attivo"],
    ["B) Immobilizzazioni"],
    ["II - Immobilizzazioni materiali"],
    ["1) terreni e fabbricati", "1.000", "1.100"],
    ["Totale immobilizzazioni materiali", "1.000", "1.100"],
    ["Totale immobilizzazioni (B)", "1.000", "1.100"],
    ["C) Attivo circolante"],
    ["IV - Disponibilità liquide"],
    ["1) depositi bancari e postali", "500", "300"],
    ["Totale disponibilità liquide", "500", "300"],
    ["Totale attivo circolante (C)", "500", "300"],
    ["Totale attivo", "1.500", "1.400"],
    ["Passivo"],
    ["A) Patrimonio netto"],
    ["I - Capitale", "1.000", "1.000"],
    ["VI - Altre riserve, distintamente indicate"],
    ["Riserva straordinaria", "80", "60"],
    ["Varie altre riserve", "20 (1)", "20"],
    ["Totale altre riserve", "100", "80"],
], pagina=0)
NOTA = _tabella("(1)", [
    ["Varie altre riserve", "31/12/2025", "31/12/2024"],
    ["Riserva indisponibile", "20", "20"],
], pagina=1)
SP_2 = _tabella("", [
    ["IX - Utile (perdita) dell'esercizio", "100", "20"],
    ["Totale patrimonio netto", "1.200", "1.100"],
    ["D) Debiti"],
    ["7) debiti verso fornitori"],
    ["esigibili entro l'esercizio successivo", "300", "300"],
    ["Totale debiti verso fornitori", "300", "300"],
    ["Totale debiti", "300", "300"],
    ["Totale passivo", "1.500", "1.400"],
], pagina=1)
CE = _tabella("Conto economico", [
    INTESTAZIONE,
    ["Conto economico"],
    ["A) Valore della produzione"],
    ["1) ricavi delle vendite e delle prestazioni", "2.000", "1.500"],
    ["Totale valore della produzione", "2.000", "1.500"],
    ["B) Costi della produzione"],
    ["7) per servizi", "1.900", "1.480"],
    ["Totale costi della produzione", "1.900", "1.480"],
    ["Differenza tra valore e costi della produzione (A - B)", "100", "20"],
    ["Risultato prima delle imposte (A - B + - C + - D)", "100", "20"],
    ["21) Utile (perdita) dell'esercizio", "100", "20"],
], pagina=2)

TESTO = ("Stato patrimoniale Attivo B) Immobilizzazioni C) Attivo circolante Passivo "
         "Conto economico A) Valore della produzione")


def _contesto(*tabelle):
    return SimpleNamespace(tables=tabelle, full_text=TESTO)


def test_le_righe_grezze_vengono_dalle_celle_con_gli_anni_dell_intestazione():
    grezze, n_col, anni = generico._grezze_mineru((SP_1, NOTA, SP_2, CE))
    assert n_col == 2 and anni == {0: 2025, 1: 2024}
    righe = {d: v for _p, d, v in grezze}
    # il richiamo di nota in coda all'importo non sposta le colonne
    assert righe["Varie altre riserve"] == [D(20), D(20)]
    # la tabella senza intestazione continua il prospetto
    assert righe["Totale passivo"] == [D(1500), D(1400)]
    # la nota con un'intestazione propria non e' il prospetto
    assert "Riserva indisponibile" not in righe
    # una riga senza importi resta una riga, a colonne vuote
    assert righe["Passivo"] == [None, None]


def test_lo_schema_di_una_scansione_si_legge_e_si_verifica_al_centesimo():
    letto = generico.estrai_da_mineru(_contesto(SP_1, NOTA, SP_2, CE))
    assert letto["adottabile"], letto.get("rifiuto")
    assert letto["anni"] == [2025, 2024]
    bs, ce = letto["bs"], letto["ce"]
    assert bs["sp03_immob_materiali"] == D("1000")
    assert bs["sp09_disponibilita_liquide"] == D("500")
    assert bs["sp11_capitale"] == D("1000")
    assert bs["sp13_utile_perdita"] == D("100")
    assert bs["sp16d_debiti_fornitori_breve"] == D("300")
    assert ce["ce01_ricavi_vendite"] == D("2000")
    assert letto["prior_bs"]["sp13_utile_perdita"] == D("20")


def test_un_importo_letto_male_si_rifiuta_non_si_adotta():
    """Il lettore riproduce ogni totale stampato: una cella sbagliata (qui la 3.4.5 che
    sfasava le colonne) produce un rifiuto, mai un numero sbagliato."""
    sbagliata = _tabella("Stato patrimoniale", [
        r if r[0] != "1) depositi bancari e postali" else ["1) depositi bancari e postali", "50", "300"]
        for r in [[c.text for c in row.cells] for row in SP_1.rows]])
    letto = generico.estrai_da_mineru(_contesto(sbagliata, NOTA, SP_2, CE))
    assert not letto["adottabile"]


def test_un_documento_che_non_e_uno_schema_di_legge_non_si_legge():
    assert generico.estrai_da_mineru(SimpleNamespace(tables=(SP_1,), full_text="Bilancio di verifica")) is None


def test_la_ricerca_dei_dettagli_non_si_rifa_sullo_schema_letto_da_mineru():
    """budget_1319: col testo pulito di MinerU 4 la ricerca partiva su Qwen e ne respingeva
    ogni proposta, 70-115 s invece di 6-9 e otto avvisi su un foglio gia' dettagliato."""
    assert _dettagli_gia_letti(None, False, True, {"_source_schema_etichette": D(1)}) \
        == "dettagli_letti_dallo_schema_mineru"
    assert _dettagli_gia_letti(None, False, True, {"_source_xbrl_reso": D(1)}) \
        == "dettagli_letti_dallo_schema_mineru"
    assert _dettagli_gia_letti(None, True, True, {}) == "dettagli_letti_dalle_tabelle_mineru"
    assert _dettagli_gia_letti({"fonte": "deterministico:xbrl_reso_parser"}, False, False, {}) \
        == "dettagli_letti_dal_prospetto_xbrl"
    # sul testo di un PDF (nessun MinerU) la ricerca resta com'era
    assert _dettagli_gia_letti(None, False, False, {"_source_schema_etichette": D(1)}) is None
    assert _dettagli_gia_letti(None, False, True, {}) is None


def test_una_cella_vuota_di_mineru_4_e_un_esercizio_senza_importo():
    """budget_283: "D.6) Acconti | | 3.000,00" - i 3.000 sono dell'anno prima. Ricomporre
    saltando la cella vuota li dava all'esercizio, e il totale dei debiti non tornava."""
    from importers.schema_etichette_parser import _ricomponi
    assert _ricomponi(["", "3.000,00"]) == (None, D("3000.00"))
    assert _ricomponi(["14.899,00", ""]) == (D("14899.00"), None)
    # la Differenza stampata smentisce la lettura per posizione: la cella vuota della 3.4.5 e'
    # un importo perso dall'OCR, e lo si ricava come prima (esercizio - differenza)
    assert _ricomponi(["25,00", "", "-5,00", "-16,667"]) == (D("25.00"), D("30.00"))


def test_le_tabelle_della_nota_con_le_scadenze_vengono_dalle_celle_di_mineru():
    """budget_173: crediti e debiti entro/oltre stanno nella nota integrativa. Dalle celle di
    MinerU si leggono con le stesse regole del PDF (budget_201: piu' pulite di find_tables,
    che spezzava "28.371" in "7 28.371")."""
    from importers.xbrl_reso_parser import raccogli_tabelle
    nota = [(17, [
        ["", "Valore di inizio esercizio", "Variazione nell'esercizio", "Valore di fine esercizio",
         "Quota scadente entro l'esercizio", "Quota scadente oltre l'esercizio"],
        ["Crediti verso clienti iscritti nell'attivo circolante", "113.915", "61.106", "175.021",
         "173.021", "2.000"],
        ["Crediti tributari iscritti nell'attivo circolante", "435", "331", "766", "724", "42"],
        ["Totale crediti iscritti nell'attivo circolante", "114.350", "61.437", "175.787",
         "173.745", "2.042"],
    ])]
    t = raccogli_tabelle(nota)["crediti"]
    assert t["errore"] is None and t["finita"]
    assert [c["entro"] for _e, c in t["righe"]] == [D("173021"), D("724")]
    assert t["totale"]["oltre"] == D("2042")


def test_il_prospetto_sintetico_si_legge_dalle_celle_di_mineru():
    """budget_1405 scansionato: lo stesso lettore del testo, sezione dalla didascalia, una
    tabella senza didascalia continua quella prima."""
    from importers import prospetto_sintetico as ps
    voci_attivo = [
        ("B) Immobilizzazioni immateriali", "100,00"), ("B) Immobilizzazioni materiali", "200,00"),
        ("B) Immobilizzazioni finanziarie", "50,00"), ("Totale B) Immobilizzazioni", "350,00"),
        ("C.I) Rimanenze", "100,00"), ("C.II) Crediti", "300,00"),
        ("C.IV) Disponibilità liquide", "50,00"), ("Totale C) Attivo circolante", "450,00"),
        ("D) Ratei e risconti", "10,00"), ("TOTALE ATTIVO", "810,00")]
    voci_passivo = [
        ("A) Patrimonio netto", "300,00"), ("B) Fondi per rischi e oneri", "10,00"),
        ("C) Trattamento di fine rapporto", "50,00"),
        ("D) Debiti entro esercizio successivo", "350,00"),
        ("D) Debiti oltre esercizio successivo", "90,00"), ("Totale D) Debiti", "440,00"),
        ("E) Ratei e risconti", "10,00"), ("TOTALE PASSIVO", "810,00")]
    voci_ce_1 = [("A.1) Ricavi delle vendite e delle prestazioni", "1.000,00"),
                 ("A.5) Altri ricavi e proventi", "20,00"),
                 ("Totale A) Valore della produzione", "1.020,00")]
    voci_ce_2 = [("B.6) Materie prime, sussidiarie, consumo e merci", "(400,00)"),
                 ("B.7) Servizi", "(300,00)"), ("B.9) Personale", "(200,00)"),
                 ("B.10) Ammortamenti e svalutazioni", "(50,00)"),
                 ("Totale B) Costi della produzione", "(950,00)"),
                 ("Differenza A - B", "70,00"),
                 ("C.17) Interessi e altri oneri finanziari", "(20,00)"),
                 ("Totale C) Proventi e oneri finanziari", "(20,00)"),
                 ("RISULTATO PRIMA DELLE IMPOSTE", "50,00"),
                 ("20) Imposte sul reddito", "(15,00)"),
                 ("UTILE DELL’ESERCIZIO", "35,00")]

    def tab(caption, voci, pagina):
        return _tabella(caption, [["Voce", "2025 (€)"]] + [list(v) for v in voci], pagina)

    contesto = SimpleNamespace(tables=(
        tab("STATO PATRIMONIALE - ATTIVO", voci_attivo, 0),
        tab("STATO PATRIMONIALE - PASSIVO", voci_passivo, 0),
        tab("CONTO ECONOMICO", voci_ce_1, 0), tab("", voci_ce_2, 1)), full_text="")
    letto = ps.estrai_da_mineru(contesto)
    assert letto.get("bs") is not None, letto.get("rifiuto")
    assert letto["bs"]["sp13"] == D("35.00")
    assert letto["ce"]["ce06"] == D("300.00")
    assert letto["stampati"]["totale_attivo"] == D("810.00")
