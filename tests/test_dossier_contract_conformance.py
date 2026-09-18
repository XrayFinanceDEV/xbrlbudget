"""M2-02G fase 2 — conformità del catalogo al contratto di pagina v4.

Il contratto (`contracts/dossier_page_contract.json`, 33 pagine estratte
dall'anteprima voluta dal proprietario) vincola **forma e struttura**, mai i
numeri e mai il testo dei titoli: vedi la sezione `binding` del JSON e
`docs/testing/M2-02G-contratto.md`.

Due cose stanno in questo file.

1. `test_pagina_esecutiva_conforme_al_contratto` confronta, **solo per le
   pagine executive (1-18)**, l'inventario del catalogo
   (`dossier_catalog.build_inventory` sulla fixture sintetica di
   `test_dossier_catalog.py`) con il contratto: ordine e id delle pagine,
   sequenza dei tipi di blocco, `kind`/numero di serie/unità di ogni grafico,
   colonne (mai più di 5) e caption di ogni tabella, numero di KPI di ogni
   rail, numero di pannelli di ogni `panel_grid`. Il messaggio di fallimento
   elenca **una riga per differenza**: è quell'elenco che la traccia C legge
   per adeguare le singole pagine. Il test nasce rosso, e le pagine non ancora
   adeguate sono marcate con uno `xfail` **dichiarato** in `NON_CONFORMANT`
   (mai uno `skip`): una pagina che diventa conforme senza che la voce venga
   rimossa fallisce come XPASS.

2. I test successivi verificano la **fondazione** che la traccia A costruisce,
   cioé i meccanismi che rendono possibile quelle correzioni: ogni grafico
   dell'inventario trasporta un `kind` esplicito, il ripiego della lista `bars`
   resta per chi non dichiara nulla, le forme di pagina (`single`,
   `rail+main`, `full+panels`) decidono geometrie e rail e le trasmettono a
   `chart_marker_width_mm`, un `panel_grid` si appiattisce nei `content_id`
   giusti.

Che cosa **non** si verifica qui, e perché:

- titoli, headline e lede: `dynamic: true` nel contratto, nel prodotto restano
  neutri (la personalizzazione vive nei commenti del piano editoriale);
- i numeri: vengono dal modello v2;
- i blocchi `optional: true`: poggiavano su contenuto assente dal modello
  (costanti di deploy, testo redazionale del campione, calendario rimborsi);
- i blocchi `note`: in v4 ogni pagina ha il suo riquadro di commento, e nel
  prodotto quel riquadro **esiste già per costruzione** come footer slot
  (marcatore di tipo `slot`, preteso su ogni pagina fisica da
  `editorial_plan._validate_records`); non è un item del catalogo, quindi non
  entra nella sequenza — la sua presenza è verificata a parte;
- i nomi delle serie: vincolanti nel contratto ma non forma di pagina, sono il
  perimetro della traccia B;
- il numero di righe delle tabelle: la fixture sintetica non ha gli stessi
  periodi di AMBIENTA, quindi le righe non si confrontano (le colonne sì, che
  sono una scelta di layout).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.renderers.typst import dossier_catalog
from app.renderers.typst.dossier_catalog import (
    build_inventory, chart_declarations, chart_marker_width_mm, expected_content_inventory, shared,
)
from tests.test_final_report_v2 import fixture_report

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "dossier_page_contract.json").read_text(encoding="utf-8"))
BASE = ROOT / "backend/app/renderers/typst/templates/dossier-base"

# Unica divergenza di id fra le due anagrafi, registrata in
# `docs/testing/M2-02G-contratto.md` (§ «Verifica di accettazione»).
CATALOG_OF_CONTRACT = {"copertina": "cover"}

# Il contratto porta l'unità come etichetta stampata nella v4, il catalogo come
# codice del modello. `None` = il grafico non dichiara unità (stacked al 100%:
# quote, non importi) e quindi quel confronto non si applica.
UNIT_OF_CONTRACT = {"€ migliaia": "eur", "%": "percent", "giorni": "days", "volte": "ratio"}

TYPE_OF_KIND = {"chart": "chart", "table": "table", "text": "text", "index": "toc",
                "panel": "panel_grid", "cover": "cover"}


def executive_contract_pages() -> list[dict]:
    return [page for page in CONTRACT["pages"] if page["priority"] == "executive"]


def _fixture_inventory() -> list[dict]:
    """La fixture sintetica di `tests/test_dossier_catalog.py`, nel workflow
    che produce più pagine executive: l'infrannuale è l'unico con le pagine
    3-6 del gruppo dati."""
    return build_inventory(fixture_report("infrannuale", [2027, 2028, 2029]))


# ── Normalizzazione: dall'inventario ai blocchi del contratto ────────────────


def _block(item: dict) -> dict:
    kind = item["kind"]
    if kind == "chart":
        chart = item["chart"]
        return {"type": "chart", "kind": chart["kind"], "n_series": len(chart["series"]),
                "unit": chart["unit"], "id": item["id"]}
    if kind == "table":
        return {"type": "table", "n_columns": len(item["columns"]),
                "caption": (item.get("title") or "").strip() or None, "id": item["id"]}
    return {"type": TYPE_OF_KIND.get(kind, kind), "id": item["id"]}


def _blocks(page: dict) -> list[dict]:
    """Sequenza dei blocchi di una pagina del catalogo. I KPI non sono un
    blocco: sono il rail, e il rail è una forma di pagina (`form`), non un item.
    Un pannello è un blocco a sé **e** apre nei suoi grafici, che restano gli
    item con i `content_id` — qui conta la forma richiesta dal contratto."""
    blocks: list[dict] = []
    for item in page["items"]:
        if item["kind"] == "panel":
            blocks.append({"type": "panel_grid", "panels": len(item["items"]),
                           "children": [_block(child) for child in item["items"]],
                           "id": item["id"]})
        else:
            blocks.append(_block(item))
    return blocks


def _expected_blocks(contract_page: dict) -> list[dict]:
    """I blocchi del contratto che una pagina del catalogo deve reproduire in
    sequenza. Due categorie restano fuori di proposito: `note` (il riquadro di
    commento è il footer slot, non un item) e `kpi_rail` (il rail è una forma
    di pagina, e si confronta a parte in `_diff_rail`: lasciarlo nella sequenza
    farebbe slittare di una posizione ogni blocco successivo, e ogni pagina
    ricadrebbe in una valanga di «blocco assente» che non è il difetto)."""
    return [block for block in contract_page["blocks"]
            if not block.get("optional") and block["type"] not in ("note", "kpi_rail")]


# ── Confronto: una riga per differenza ──────────────────────────────────────


def _diff_rail(contract_page: dict, page: dict) -> list[str]:
    where = f"pag. {contract_page['order']} {contract_page['id']}"
    lines: list[str] = []
    for block in contract_page["blocks"]:
        if block["type"] != "kpi_rail":
            continue
        have = len(page.get("rail") or [])
        if block["n_kpis"] != have:
            lines.append(f"{where}: rail con {block['n_kpis']} KPI atteso, trovati {have}")
        form = page.get("form")
        want_form = "cover" if block.get("variant") == "cover" else "rail+main"
        if form != want_form:
            lines.append(f"{where}: forma di pagina {want_form!r} attesa (rail a sinistra del "
                         f"contenuto), trovata {form!r}")
    return lines


def _diff_chart(contract_block: dict, catalog_block: dict, where: str) -> list[str]:
    lines = []
    if contract_block["kind"] != catalog_block["kind"]:
        lines.append(f"{where}: grafico {contract_block['kind']} atteso, "
                     f"trovato {catalog_block['kind']}")
    if contract_block.get("n_series") != catalog_block["n_series"]:
        lines.append(f"{where}: {contract_block.get('n_series')} serie attese, "
                     f"trovate {catalog_block['n_series']}")
    if contract_block.get("unit") is not None:
        want = UNIT_OF_CONTRACT[contract_block["unit"]]
        if want != catalog_block["unit"]:
            lines.append(f"{where}: unità {contract_block['unit']!r} ({want}) attesa, "
                         f"trovata {catalog_block['unit']!r}")
    return lines


def _diff_blocks(contract_page: dict, page: dict) -> list[str]:
    order, identifier = contract_page["order"], contract_page["id"]
    expected, actual = _expected_blocks(contract_page), _blocks(page)
    if identifier == "copertina":
        # La copertina è una composizione a sé (`base.typ::cover`, perimetro
        # M2-02F): i suoi meta_row/text/toc non sono item del catalogo, e qui
        # si dichiara che quel confronto non è a carico del catalogo. La forma
        # della pagina e il suo rail a 4 KPI si verificano comunque, sopra.
        types = [block["type"] for block in actual]
        if types != ["cover"]:
            return [f"pag. {order} {identifier}: blocco 'cover' atteso, trovati {types}"]
        return [f"pag. {order} {identifier}: i blocchi meta_row/text/toc della copertina sono "
                f"resi da `base.typ::cover`, non da item del catalogo (verifica a carico di "
                f"M2-02F)"]
    lines: list[str] = []
    want_types = [block["type"] for block in expected]
    have_types = [block["type"] for block in actual]
    if want_types != have_types:
        lines.append(f"pag. {order} {identifier}: sequenza {want_types} attesa, trovata {have_types}")
    for index, want in enumerate(expected):
        where = f"pag. {order} {identifier}: blocco {index + 1}"
        if index >= len(actual):
            lines.append(f"{where} di tipo {want['type']!r} atteso, blocco assente")
            continue
        have = actual[index]
        if have["type"] != want["type"]:
            continue  # il disallineamento lo dice già la riga sulla sequenza
        if want["type"] == "chart":
            lines.extend(_diff_chart(want, have, where))
        elif want["type"] == "table":
            if want["n_columns"] != have["n_columns"]:
                lines.append(f"{where}: tabella di {want['n_columns']} colonne attesa, "
                             f"trovate {have['n_columns']}")
            if want.get("caption") and not have.get("caption"):
                lines.append(f"{where}: tabella con caption {want['caption']!r} attesa, "
                             f"titolo di blocco assente")
        elif want["type"] == "panel_grid":
            if want["panels"] != have["panels"]:
                lines.append(f"{where}: panel_grid da {want['panels']} pannelli atteso, "
                             f"trovati {have['panels']}")
            for child_index, child in enumerate(want.get("charts", [])):
                if child_index >= len(have.get("children", [])):
                    lines.append(f"{where}, pannello {child_index + 1}: grafico {child['kind']} "
                                 f"atteso, pannello assente")
                    continue
                lines.extend(_diff_chart(child, have["children"][child_index],
                                         f"{where}, pannello {child_index + 1}"))
    return lines


def page_diffs(contract_page: dict, inventory: list[dict]) -> list[str]:
    identifier = CATALOG_OF_CONTRACT.get(contract_page["id"], contract_page["id"])
    page = next((item for item in inventory if item["id"] == identifier), None)
    if page is None:
        return [f"pag. {contract_page['order']} {contract_page['id']}: pagina assente dal catalogo"]
    return _diff_rail(contract_page, page) + _diff_blocks(contract_page, page)


# ── Le pagine non ancora adeguate: un xfail dichiarato per ciascuna ─────────
# Ogni voce dice che cosa la traccia C deve chiudere su quella pagina. Elenco
# redatto a consegna della traccia A, misurando `page_diffs` sotto.

NON_CONFORMANT: dict[str, str] = {
    "cover": "perimetro M2-02F: la copertina è la composizione unica di `base.typ::cover` "
             "(meta_row, tre text e toc del contratto non sono item), e non dichiara la forma "
             "`cover` per il proprio rail.",
    "sintesi": "forma `rail+main` non dichiarata; il grafico esce a linee perché "
               "`sintesi-andamento` non dichiara `kind='bar'` (contratto: barre, 3 serie × "
               "4 periodi).",
    "fonti": "forma `rail+main` non dichiarata (rail a 4 KPI, prima tabella nella colonna "
             "principale).",
    "rettifiche": "forma `rail+main` non dichiarata: i 4 KPI stanno al grafico, non al rail.",
    "chiusura": "forma `rail+main` non dichiarata: i 4 KPI stanno al grafico, non al rail.",
    "indicatori-infrannuali": "forma `rail+main` non dichiarata; il confronto esce a barre "
                              "perché `indicatori-infrannuali-confronto` non dichiara "
                              "`kind='dumbbell'`.",
    "ipotesi": "forma `rail+main` non dichiarata; il rail della fixture ha 3 KPI contro i 4 "
               "del contratto («investimenti cumulati» non è nel modello: traccia B).",
    "ce": "forma `rail+main` non dichiarata; serie a 2 periodi contro i 4 del contratto, con "
         "l'EBIT margin alla chiusura che il modello non espone (traccia B).",
    "sp": "forma `rail+main` non dichiarata; `sp-patrimonio-debito` non dichiara `kind='bar'` "
         "e la colonna della chiusura manca (traccia B).",
    "flussi": "forma `rail+main` non dichiarata; `flussi-composizione` deve dichiarare "
              "`kind='bar'` (esce a barre dal ripiego `bars`, ma il kind va dichiarato).",
    "indicatori": "forma `rail+main` non dichiarata.",
    "liquidita": "forma `rail+main` non dichiarata; il contratto chiede DUE grafici (barre "
                 "strutturali + linee current/quick ratio) e il secondo non esiste: "
                 "`quick_ratio` non è esposto come serie (traccia B).",
    "redditivita": "forma `full+panels` non dichiarata; il contratto chiede un `panel_grid` di "
                   "due grafici a linee, qui c'è un solo grafico a 4 serie.",
    "solidita": "forma `rail+main` non dichiarata; il secondo grafico (PFN / EBITDA in «volte») "
                "non esiste come blocco.",
    "composizione": "forma `full+panels` non dichiarata; due `stacked` in un pannello + un "
                    "`dumbbell` delle incidenze, oggi un grafico a linee e una tavola di quote "
                    "che il contratto non ha.",
    "break-even": "forma `rail+main` non dichiarata; il primo grafico non dichiara "
                  "`kind='bar'` e il secondo (margine di sicurezza %) non esiste come blocco.",
    "diagnostica": "forma `rail+main` non dichiarata; il contratto chiede rail a 4 KPI, una "
                   "tavola «Priorità di verifica» (che oggi è un blocco text) e una seconda "
                   "tavola.",
    "circolante": "pagina assente dalla fixture sintetica: `indicatori._circolante` produce una "
                  "pagina senza_items_ quando gli indici di rotazione sono tutti a zero, e la "
                  "fixture è uno di quei casi (su AMBIENTA la pagina c'è).",
}

EXECUTIVE_PAGE_IDS = [CATALOG_OF_CONTRACT.get(page["id"], page["id"]) for page in executive_contract_pages()]
EXECUTIVE_CONTRACT = dict(zip(EXECUTIVE_PAGE_IDS, executive_contract_pages()))


@pytest.mark.parametrize("catalog_id", EXECUTIVE_PAGE_IDS)
def test_pagina_esecutiva_conforme_al_contratto(catalog_id: str) -> None:
    diffs = page_diffs(EXECUTIVE_CONTRACT[catalog_id], _fixture_inventory())
    if not diffs:
        assert catalog_id not in NON_CONFORMANT, (
            f"pagina {catalog_id} ora conforme: rimuovere la voce da NON_CONFORMANT")
        return
    assert catalog_id in NON_CONFORMANT, "differenze non dichiarate:\n" + "\n".join(diffs)
    pytest.xfail(f"{NON_CONFORMANT[catalog_id]} | oggi: " + " | ".join(diffs))


# ── Vincoli trasversali, verificati senza xfail ─────────────────────────────


def test_cinque_colonne_massimo_su_tutte_le_tabelle() -> None:
    """`binding`: mai più di 5 colonne, su qualunque pagina."""
    for page in _fixture_inventory():
        for item in page["items"]:
            if item["kind"] == "table":
                assert len(item["columns"]) <= 5, f"{page['id']}/{item['id']}: {len(item['columns'])} colonne"


# Pagine executive che la fixture sintetica non produce: non è un difetto di
# layout, è contenuto assente su una fonte degenere (su AMBIENTA la pagina
# c'è). Dichiarata qui perché il confronto d'ordine resti leggibile: se ne
# scompare un'altra, questo test fallisce e nomina quale.
MISSING_FROM_FIXTURE = {"circolante"}


def test_ordine_e_id_delle_pagine_esecutive() -> None:
    inventory = _fixture_inventory()
    present = [page["id"] for page in inventory if page["id"] in EXECUTIVE_PAGE_IDS]
    assert set(present) == set(EXECUTIVE_PAGE_IDS) - MISSING_FROM_FIXTURE, (
        f"atteso {sorted(set(EXECUTIVE_PAGE_IDS) - MISSING_FROM_FIXTURE)}, trovato {present}")
    assert present == [page for page in EXECUTIVE_PAGE_IDS if page in present]


def test_ogni_pagina_esecutiva_dichiara_il_riquadro_di_commento() -> None:
    """Il contratto porta una nota su tutte e 33 le pagine; nel prodotto il
    riquadro non è un item ma il footer slot, preteso su ogni pagina fisica da
    `editorial_plan._validate_records`. Qui si verifica la premessa."""
    for page in executive_contract_pages():
        assert any(block["type"] == "note" for block in page["blocks"]), page["id"]


def test_style_contract_letto_dalla_tipografia() -> None:
    """Lo style contract è la fonte dei corpi applicati in `base.typ`: se una
    chiave si muove, la tipografia va riallineata (traccia A, punto 6)."""
    style = json.loads((ROOT / "contracts" / "dossier_style_contract.json").read_text(encoding="utf-8"))
    assert style["type"]["corpo"]["size"]["pt"] == 9.0
    assert style["type"]["titolo_pagina"]["size"]["pt"] == 16.0
    assert style["type"]["occhiello"]["size"]["pt"] == 7.5
    assert style["type"]["tabella"]["size"]["pt"] == 8.0
    assert style["type"]["intestazione_tabella"]["size"]["pt"] == 7.2
    assert style["type"]["legenda"]["size"]["pt"] == 7.6
    assert style["type"]["titolo_nota"]["size"]["pt"] == 8.0
    assert style["type"]["testo_nota"]["size"]["pt"] == 9.0
    assert style["type"]["kpi_valore"]["size"]["pt"] == 15.0
    assert style["colors"]["series_palette"] == ["#003049", "#669BBC", "#B7791F", "#9CC0D8"]

    # Fin qui il JSON. Le righe sotto riguardano il template: un ruolo tipografico
    # che lo style contract nomina e che `base.typ`/`comuni.typ`/`charts.typ` non
    # esprimono piú non è "il contratto non vincola", è una regressione — ed è
    # esattamente il modo in cui una forma di pagina torna `single` senza che
    # nessuno se ne accorga.
    templates = ROOT / "backend/app/renderers/typst/templates/dossier-base"
    base = (templates / "base.typ").read_text(encoding="utf-8")
    comuni = (templates / "pagine/comuni.typ").read_text(encoding="utf-8")
    grafici = (templates / "charts.typ").read_text(encoding="utf-8")
    assert "size: 9pt" in base, "il corpo del documento non è piú 9 pt"
    assert "safe-prose(16pt, weight: 600" in comuni, "il titolo di pagina non è piú 16 pt/600"
    assert "plex(7.5pt, weight: 500, fill: blue" in comuni, "l'occhiello non è piú 7,5 pt/500"
    assert "size: 8pt" in comuni, "la tabella non è piú 8 pt"
    assert "plex(7.2pt, weight: 500, fill: muted" in comuni, "l'intestazione di tabella non è piú 7,2 pt/500 muted"
    assert "7.6pt, fill: muted" in grafici, "la legenda dei grafici non è piú 7,6 pt muted"
    assert "#let rail-width = 47mm" in base, "il rail non è piú largo 47 mm come lo style contract"
    assert style["spacing"]["rail_colonna"]["width"] == "47mm"
    assert "15pt" in base and "7.8pt, fill: muted, kpi.label" in base, "il KPI del rail non è piú 15 pt su 7,8 pt"
    # Le colonne della forma devono richiudere il foglio: sono la stessa somma
    # che Typst mette nel grid e che `editorial_plan` rivuole nel marcatore.
    assert 47 + 5 + float(shared.CHART_WIDTH_RAIL_MM) == 178
    assert 2 * float(shared.CHART_WIDTH_PANEL_MM) + 6 == 178


# ── La fondazione: kind, forme di pagina, pannelli ──────────────────────────


def _page(identifier: str, items: list[dict], **extra) -> dict:
    page = {"id": identifier, "title": identifier, "family": None, "subtitle": None, "kpis": []}
    page.update(extra)
    page["items"] = items
    return dossier_catalog._apply_page_form(page)


def _years(count: int) -> list:
    from types import SimpleNamespace
    return [SimpleNamespace(year=2027 + index) for index in range(count)]


def _chart_item(identifier: str, label: str, values: list[int], unit: str = "eur",
                kpis: list[dict] | None = None, kind: str | None = None) -> dict:
    chart = shared.chart_from_series(identifier, identifier, unit, _years(len(values)),
                                      [(label, values)], kind=kind)
    return shared.chart_block(identifier, identifier, chart, kpis or [])


def test_kind_di_grafico_sempre_dichiarato_nell_inventario() -> None:
    for page in _fixture_inventory():
        for item in page["items"]:
            for block in ([item] if item["kind"] != "panel" else item["items"]):
                if block["kind"] == "chart":
                    assert block["chart"]["kind"] in shared.CHART_KINDS, block["id"]


def test_ripiego_sulla_lista_bars_per_un_item_che_non_dichiara_nulla() -> None:
    bars = json.loads((BASE / "chart-layout.json").read_text(encoding="utf-8"))["bars"]
    assert all(shared.chart_kind({"id": identifier}) == "bar" for identifier in bars)
    assert shared.chart_kind({"id": "un grafico mai visto"}) == "line"
    # Una dichiarazione vince sempre sul ripiego, anche se l'id sta in `bars`.
    assert shared.chart_kind({"id": "cashflows"}, "dumbbell") == "dumbbell"


def test_kind_e_forma_sconosciuti_si_rifiutano_non_si_ripiegano() -> None:
    with pytest.raises(ValueError, match="unknown chart kind"):
        shared.chart_kind({"id": "x"}, "donut")
    with pytest.raises(ValueError, match="unknown page form"):
        _page("x", [], form="a-quattro-colonne")


def test_forma_di_default_single_non_cambia_geometrie_né_value_table() -> None:
    """Una pagina che non dichiara `form` deve comportarsi esattamente come
    prima della traccia A: è ciò che tiene in piedi le pagine non ancora
    adeguate mentre la traccia C le raggiunge."""
    item = _chart_item("prova-single", "A", [1], kpis=[shared.kpi("a", 1)])
    page = _page("prova-single", [item])
    assert page["form"] == "single"
    assert chart_marker_width_mm(item) == shared.CHART_WIDTH_KPI_MM
    assert "value_table" not in item and "rail" not in item


def test_rail_di_pagina_prende_i_kpi_e_stringe_il_grafico_a_126mm() -> None:
    item = _chart_item("prova-rail", "A", [1], kpis=[shared.kpi("a", 1)])
    page = _page("prova-rail", [item], form="rail+main")
    assert page["form"] == "rail+main"
    assert [k["label"] for k in page["rail"]] == ["a"]
    assert item["kpis"] == [], "il grafico non deve ripetere nel proprio blocco i KPI del rail"
    assert chart_marker_width_mm(item) == shared.CHART_WIDTH_RAIL_MM == "126"
    assert item["value_table"] is False


def test_rail_di_pagina_lascia_a_larghezza_intera_cio_che_sotto_non_sta() -> None:
    """Il rail della v4 sta dentro la `.row`: accanto al primo blocco (o alla
    corsa iniziale di grafici), non accanto all'intera pagina."""
    first = _chart_item("rail-1", "A", [1])
    second = _chart_item("rail-2", "B", [2])
    table = shared.table("rail-tab", "Tabella", ["Voce", "2027"],
                         [shared.row("rail-tab:1", ["x", 1])])
    page = _page("rail-due", [first, second, table], form="rail+main")
    assert (first["rail"], second["rail"], table["rail"]) == (True, True, False)
    assert chart_marker_width_mm(first) == chart_marker_width_mm(second) == "126"


def test_pannelli_affiancati_a_meta_larghezza() -> None:
    left = _chart_item("p-1", "Sinistra", [1], "percent")
    right = _chart_item("p-2", "Destra", [2], "percent")
    panel = shared.panel_grid("prova-panel", "Pannelli", [left, right])
    _page("prova-panel", [panel], form="full+panels")
    assert panel["panels"] == 2 and panel["kind"] == "panel"
    assert [chart_marker_width_mm(child) for child in (left, right)] == ["86", "86"]
    assert all(child["value_table"] is False for child in (left, right))
    # Un pannello con un figlio solo non è un pannello: i blocchi restano propri.
    assert shared.panel_grid("zoppo", "Zoppo", [left]) is None


# ── La fondazione si compila: rail, stacked, dumbbell, pannelli ─────────────
# Una forma che non è mai stata resa da Typst non è una forma realizzata.
# Queste pagine sintetiche passano dal probe di layout, cioé dallo stesso
# compilatore, dallo stesso sandbox e dalla stessa rete di controlli che il
# piano editoriale usa per rivalidare un dossier reale: se una componente non
# stesse nei 94 mm o sconfinasse dalla colonna, il probe risponde
# `RendererCompileError`, e se la larghezza misurata non fosse quella che
# Python ha dichiarato non passerebbe `_validate_records`.

def _synthetic_catalog(report) -> list[dict]:
    """Quattro pagine finte, una per forma: il modo piú diretto di dimostrare
    che rail, stacked, dumbbell e pannelli esistono anche dall'altra parte del
    filo — quella che impagina — e non solo nell'inventario."""
    years = report.forecast.years
    revenue = [("Ricavi", [str(y.income_statement[0].value) for y in years])]
    cash = [("Operativo", [str(y.balance_sheet[0].value) for y in years])]

    def chart(identifier, title, pairs, unit, kind, categories=None):
        view = shared.chart_from_series(identifier, title, unit, years, pairs, kind=kind)
        if categories is not None:
            view["categories"] = categories
        return view

    rail_chart = shared.chart_block("fondo-rail", "Barre nel rail",
        chart("fondo-rail", "Barre nel rail", cash, "eur", "bar"),
        [shared.kpi("cassa", years[-1].balance_sheet[0].value, "eur"),
         shared.kpi("ricavi", years[-1].income_statement[0].value, "eur")])
    rail_table = shared.table("fondo-rail-tab", "Tavola sotto il rail",
        ["Voce", "2029"],
        [shared.row("fondo-rail-tab:2029", ["Ricavi", years[-1].income_statement[0].value], [None, "eur"])])
    rail_page = {"id": "fondo-rail", "title": "Rail di pagina", "family": "Sintesi",
                 "subtitle": "Un grafico nella `.row`, una tavola a larghezza intera.",
                 "kpis": [], "items": [rail_chart, rail_table], "form": "rail+main"}

    uses = shared.chart_block("fondo-uses", "Impieghi", chart("fondo-uses", "Impieghi",
        [("Immobilizzazioni", ["30"] * len(years)), ("Circolante", ["60"] * len(years)),
         ("Cassa", ["10"] * len(years))], "percent", "stacked"), [])
    sources = shared.chart_block("fondo-sources", "Fonti", chart("fondo-sources", "Fonti",
        [("Patrimonio netto", ["40"] * len(years)), ("Debiti", ["50"] * len(years)),
         ("Altro", ["10"] * len(years))], "percent", "stacked"), [])
    panel_page = {"id": "fondo-panel", "title": "Pannelli", "family": "Sintesi", "subtitle": None,
                  "kpis": [], "items": [shared.panel_grid("fondo-panel", "Pannelli", [uses, sources])],
                  "form": "full+panels"}

    dumbbell_view = chart("fondo-dumbbell", "Incidenze",
        [("Periodo iniziale", ["30", "25", "19.79", "2.08"]),
         ("Periodo finale", ["30", "21.34", "20.35", "1.32"])], "percent", "dumbbell",
        categories=["Materie prime", "Servizi", "Personale", "Oneri finanziari"])
    dumbbell_page = {"id": "fondo-dumbbell", "title": "Dumbbell", "family": "Sintesi", "subtitle": None,
                     "kpis": [], "items": [shared.chart_block("fondo-dumbbell", "Incidenze",
                     dumbbell_view, [shared.kpi("incidenza materie", "30", "percent")])],
                     "form": "rail+main"}

    cover = {"id": "cover", "title": None, "family": None, "subtitle": None, "kpis": [],
             "items": [{"id": "cover", "kind": "cover", "title": report.document.title}]}
    return [cover, rail_page, panel_page, dumbbell_page]


@pytest.fixture
def probe(tmp_path):
    import os
    from app.renderers.typst import Compiler
    from app.renderers.typst.editorial_plan import DossierLayoutProbe, DossierTemplateBundle
    binary = Path(os.environ.get("TYPST_TEST_BINARY", ROOT / "tools/typst/bin/typst"))
    if not binary.is_file():
        pytest.skip("Install pinned compiler for real editorial layout tests")
    return DossierLayoutProbe(Compiler.from_manifest(ROOT / "tools/typst/manifest.json", binary),
                              DossierTemplateBundle(BASE), temp_root=tmp_path)


def test_le_quattro_forme_si_compilano_su_una_pagina_ciascuna(probe, monkeypatch) -> None:
    """Ogni forma occuperebbe una pagina sola se stesse nei 244 mm.

    Il probe passa anche dalla rete di `editorial_plan`: un grafico misurato piú
    largo o piú alto di quanto Python ha dichiarato (`_validate_records`) non
    arriva fin qui, e una pagina che sconfinasse su due fisiche si vede dal
    numero di pagina dei suoi contenuti.
    """
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    monkeypatch.setattr(dossier_catalog.apertura, "build", lambda r: _synthetic_catalog(r))
    pages = {record.content_id: record.page for record in probe.measure_layout(report).records
             if record.kind == "content"}
    assert pages["chart:fondo-rail"] == 2, "la pagina rail è sconfinata su due fisiche"
    assert pages["chart:fondo-uses"] == pages["chart:fondo-sources"] == 3, "i pannelli non stanno in una pagina"
    assert pages["chart:fondo-dumbbell"] == 4, "la pagina dumbbell è sconfinata su due fisiche"


def test_la_larghezza_dichiarata_e_quella_della_forma(synthetic_catalog) -> None:
    """`86` e `126` non sono due numeri inventati dal template: sono le colonne
    che la forma di pagina ha deciso, e `chart_marker_width_mm` è la funzione
    che il piano editoriale usa per controllarle una per una."""
    pages = synthetic_catalog
    rail = pages[1]["items"][0]
    assert rail["width_mm"] == shared.CHART_WIDTH_RAIL_MM == "126"
    assert rail["value_table"] is False, "la tabellina dei valori resta anche nel rail"
    assert pages[1]["rail"], "la pagina rail+main non ha KPI nel rail"
    assert dossier_catalog.chart_marker_width_mm(rail) == "126"
    panel = pages[2]["items"][0]
    assert panel["kind"] == "panel" and len(panel["items"]) == 2
    assert {child["width_mm"] for child in panel["items"]} == {shared.CHART_WIDTH_PANEL_MM}
    assert all(child["value_table"] is False for child in panel["items"])
    # Il contenitore non è un blocco per il piano: `chart_marker_width_mm` si
    # chiama sui figli, che sono gli unici con un marcatore proprio.
    assert all(dossier_catalog.chart_marker_width_mm(child) == "86" for child in panel["items"])
    assert dossier_catalog.chart_marker_width_mm(pages[3]["items"][0]) == "126"


@pytest.fixture
def synthetic_catalog():
    # La normalizzazione della forma la fa `build_inventory`, non il catalogo
    # delle pagine finte: senza, le colonne non sarebbero assegnate.
    from app.renderers.typst.dossier_catalog import _apply_page_form
    return [_apply_page_form(page) for page in _synthetic_catalog(
        fixture_report("infrannuale", [2027, 2028, 2029]))]


def test_pannello_si_appiattisce_nei_contenuti_e_nelle_dichiarazioni() -> None:
    """Il piano editoriale e il probe di layout devono continuare a vedere i
    singoli `chart:<id>`, mai il contenitore dei pannelli."""
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    left = _chart_item("finto-1", "A", [1], "percent", kpis=[])
    right = _chart_item("finto-2", "B", [2], "percent", kpis=[])
    panel = shared.panel_grid("finto", "Pannelli", [left, right])

    def build(_report):
        return [{"id": "cover", "title": None, "family": None, "subtitle": None, "kpis": [],
                 "items": [{"id": "cover", "kind": "cover", "title": "x"}]},
                {"id": "finto", "title": "Finto", "family": "Sintesi", "subtitle": None,
                 "kpis": [], "items": [panel], "form": "full+panels"}]

    original = dossier_catalog.apertura.build
    dossier_catalog.apertura.build = build
    try:
        expected = list(expected_content_inventory(report))
        assert expected[:3] == ["cover", "chart:finto-1", "chart:finto-2"], expected[:3]
        assert "panel:finto" not in expected
        declarations = chart_declarations(report)
        assert {"chart:finto-1", "chart:finto-2"} <= set(declarations)
        assert [chart_marker_width_mm(declarations[key])
                for key in ("chart:finto-1", "chart:finto-2")] == ["86", "86"]
    finally:
        dossier_catalog.apertura.build = original
