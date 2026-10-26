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
