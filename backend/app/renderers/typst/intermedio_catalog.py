"""Catalogo delle pagine del report intermedio (infrannuale + crisi d'impresa).

Stesso formato di pagina del dossier finale (`dossier_catalog`): id, titolo,
famiglia, sottotitolo, forma (`rail+main` · `full+panels`), KPI del rail e
blocchi (`chart` · `table` · `text`), resi da `pagine/comuni.typ` senza
modifiche. Cambiano il modello letto (`IntermediateReportModel`) e il
commento di pagina, che qui e' uno dei sei commenti AI dell'infrannuale.

I moduli di `dossier_catalog` si importano e non si toccano: il loro hash lega
i piani editoriali gia' misurati del report finale, e una modifica li
dichiarerebbe tutti non attuali.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas.intermedio_report import IntermediateReportModel
from calculations.crisi_impresa import SOGLIA_OLTRE

from .dossier_catalog import _apply_page_form  # noqa: PLC2701 (la normalizzazione delle forme e' una sola)
from .dossier_catalog import shared as s

_UNITA = {"euro": "eur", "pct": "percent", "ratio": "ratio"}
# Soglia del pallino verde della tabella a schermo (`scoreDotColor`).
SOGLIA_BUONO = Decimal("0.67")

_CE_RIGHE = (
    ("ricavi", "Ricavi"),
    ("costi_operativi", "Costi operativi"),
    ("ebitda", "EBITDA"),
    ("ammortamenti", "Ammortamenti"),
    ("ebit", "EBIT"),
    ("oneri_finanziari", "Oneri finanziari"),
    ("risultato_ante_imposte", "Risultato ante imposte"),
    ("imposte", "Imposte"),
    ("risultato_netto", "Risultato netto"),
)


def _d(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _var_pct(dopo: Any, prima: Any) -> Decimal | None:
    """Variazione percentuale di due cifre gia' in pagina: ricapitola, non deriva."""
    if dopo is None or prima is None or Decimal(prima) == 0:
        return None
    return (Decimal(dopo) / Decimal(prima) - 1) * 100


def _esito(punteggio: Any) -> str:
    p = Decimal(str(punteggio))
    if p < SOGLIA_OLTRE:
        return "oltre soglia"
    return "attenzione" if p < SOGLIA_BUONO else "in soglia"


def _chart(chart_id: str, title: str, unit: str, categories: list[str],
           series: list[tuple[str, list[Any]]], kind: str = "bar") -> dict[str, Any] | None:
    built = [{"label": label, "values": [s.exact(_d(v)) for v in values]}
             for label, values in series if any(v is not None for v in values)]
    if not built:
        return None
    return {"id": chart_id, "title": title, "unit": unit, "categories": categories,
            "series": built, "indicator_ids": [], "thresholds": [], "kind": kind}


def _page(model: IntermediateReportModel, pid: str, title: str, family: str, subtitle: str,
          kpis: list[dict | None], items: list[dict | None], comment_key: str | None,
          form: str = "rail+main") -> dict[str, Any]:
    shown = [k for k in kpis if k is not None]
    blocks = [i for i in items if i is not None]
    # Il rail prende i KPI della pagina (`_apply_page_form`), non quelli del grafico.
    for block in blocks:
        if block["kind"] == "chart":
            block["kpis"] = []
    return {"id": pid, "title": title, "family": family, "form": form, "subtitle": subtitle,
            "kpis": shown, "items": blocks,
            "comment": model.commenti.get(comment_key, "") if comment_key else ""}


def _colonne_crisi(model: IntermediateReportModel) -> list[tuple[str, Any]]:
    c = model.crisi
    cols = [(f"Storico {c.reference_year}", c.storico), (f"Infrannuale {c.period_months}M", c.infrannuale)]
    if c.proiezione is not None:
        cols.append((f"Proiezione {c.partial_year}", c.proiezione))
    return cols


# ── Copertina ─────────────────────────────────────────────────────────────────


def _copertina(model: IntermediateReportModel) -> dict[str, Any]:
    parziale = model.colonna_ce("infrannuale")
    finale = model.colonna_ce("proiezione") or model.colonna_ce("annualizzato")
    colonna = model.crisi.proiezione or model.crisi.infrannuale
    kpis = [k for k in (
        s.kpi(f"ricavi · {model.period_months} mesi {model.partial_year}", parziale.ricavi, "eur"),
        s.kpi(f"ricavi · proiezione {model.partial_year}", finale.ricavi if finale else None, "eur"),
        s.kpi(f"EBITDA · proiezione {model.partial_year}", finale.ebitda if finale else None, "eur"),
        s.kpi(f"classe di rischio · {'proiezione' if model.crisi.proiezione else 'infrannuale'}",
              f"{colonna.rating.codice} · {colonna.rating.etichetta}"),
    ) if k is not None]
    return {"id": "cover", "title": None, "family": None, "subtitle": None, "kpis": kpis,
            "items": [{"id": "cover", "kind": "cover", "title": documento_titolo(model)}]}


# ── Sintesi ───────────────────────────────────────────────────────────────────


def _sintesi(model: IntermediateReportModel) -> dict[str, Any]:
    parziale = model.colonna_ce("infrannuale")
    proiez = model.colonna_ce("proiezione")
    crisi = model.crisi
    colonne_ce = [c for c in model.ce if c.chiave != "infrannuale"]
    chart = _chart("intermedio-sintesi", "Ricavi e redditività", "eur", [c.etichetta for c in colonne_ce],
                   [("Valore della produzione", [c.ce.valore_produzione for c in colonne_ce]),
                    ("EBITDA", [c.ce.ebitda for c in colonne_ce]),
                    ("Risultato netto", [c.ce.risultato_netto for c in colonne_ce])])
    rating_to = crisi.proiezione.rating.codice if crisi.proiezione else None
    kpis = [
        s.kpi(f"ricavi · {model.period_months} mesi {model.partial_year}", parziale.ricavi, "eur"),
        s.kpi(f"ricavi · proiezione {model.partial_year}", proiez.ricavi if proiez else None, "eur"),
        s.kpi(f"EBITDA · proiezione {model.partial_year}", proiez.ebitda if proiez else None, "eur"),
        s.kpi("classe di rischio · infrannuale → proiezione", crisi.infrannuale.rating.codice, to=rating_to),
    ]
    cols = [c for c in model.sp]
    ce_by = {c.chiave: c.ce for c in model.ce}
    crisi_by = {"storico": crisi.storico, "infrannuale": crisi.infrannuale, "proiezione": crisi.proiezione}
    columns = ["Voce"] + [c.etichetta for c in cols]
    units_eur = [None] + ["eur"] * len(cols)

    def riga(key: str, label: str, values: list[Any], units: list[str | None] | None = None):
        return s.row(f"intermedio-sintesi-tabella:{key}", [label, *values], units or units_eur)

    rows = [
        riga("ricavi", "Ricavi", [ce_by[c.chiave].ricavi for c in cols]),
        riga("ebitda", "EBITDA", [ce_by[c.chiave].ebitda for c in cols]),
        riga("risultato", "Risultato netto", [ce_by[c.chiave].risultato_netto for c in cols]),
        riga("attivo", "Totale attivo", [c.sp.totale_attivo for c in cols]),
        riga("pn", "Patrimonio netto", [c.sp.patrimonio_netto for c in cols]),
        riga("pfn", "PFN", [_d(crisi_by[c.chiave].indicatori["pfn"]) if crisi_by.get(c.chiave) else None
                             for c in cols]),
        riga("rating", "Classe di rischio",
             [f"{crisi_by[c.chiave].rating.codice} · {crisi_by[c.chiave].rating.etichetta}"
              if crisi_by.get(c.chiave) else None for c in cols], [None] * len(columns)),
    ]
    note = ("I ricavi e i risultati dell'infrannuale sono di " f"{model.period_months} mesi; "
            "lo stato patrimoniale è puntuale alla data del periodo.")
    return _page(model, "sintesi", "Sintesi esecutiva", "Sintesi",
                 "Il periodo osservato, la sua proiezione a fine anno e l'anno di riferimento "
                 "sono tenuti distinti in tutto il documento.",
                 kpis,
                 [s.chart_block("intermedio-sintesi", "Ricavi e redditività", chart, []),
                  s.table("intermedio-sintesi-tabella", "Il periodo in sintesi", columns, rows),
                  s.note("intermedio-sintesi-nota", note)],
                 "overall")


# ── Conto economico a confronto ──────────────────────────────────────────────


def _ce_confronto(model: IntermediateReportModel) -> dict[str, Any]:
    storico = model.colonna_ce("storico")
    parziale = model.colonna_ce("infrannuale")
    annual = model.colonna_ce("annualizzato")
    cols = [c for c in model.ce if c.chiave in ("storico", "infrannuale", "annualizzato")]
    chart = _chart("intermedio-ce-confronto", "Il periodo contro l'anno di riferimento", "eur",
                   [c.etichetta for c in cols],
                   [("Ricavi", [c.ce.ricavi for c in cols]), ("EBITDA", [c.ce.ebitda for c in cols]),
                    ("Risultato netto", [c.ce.risultato_netto for c in cols])])
    kpis = [
        s.kpi(f"ricavi · {model.period_months} mesi", parziale.ricavi, "eur"),
        s.kpi(f"ricavi annualizzati · {model.partial_year}", annual.ricavi if annual else None, "eur"),
        s.kpi(f"annualizzato su storico {model.reference_year}",
              _var_pct(annual.ricavi, storico.ricavi) if annual else None, "percent"),
        s.kpi("EBITDA margin · annualizzato", _d(model.crisi.infrannuale.indicatori["ebitda_margin"]), "percent"),
    ]
    columns = ["Voce"] + [c.etichetta for c in cols]
    if annual:
        columns.append("Annualizz. / storico")
    rows = []
    for key, label in _CE_RIGHE:
        values = [getattr(c.ce, key) for c in cols]
        units: list[str | None] = [None] + ["eur"] * len(cols)
        if annual:
            values.append(_var_pct(getattr(annual, key), getattr(storico, key)))
            units.append("percent")
        rows.append(s.row(f"intermedio-ce-confronto-tabella:{key}", [label, *values], units))
    return _page(model, "ce-confronto", "Conto economico a confronto", "Conto economico",
                 f"I {model.period_months} mesi osservati, riportati a dodici mesi "
                 f"(× 12 / {model.period_months}), contro l'anno {model.reference_year}.",
                 kpis,
                 [s.chart_block("intermedio-ce-confronto", "Il periodo contro l'anno di riferimento", chart, []),
                  s.table("intermedio-ce-confronto-tabella", "Conto economico riclassificato", columns, rows)],
                 "ce_confronto")


_SP_RIGHE = (
    ("immobilizzazioni", "Immobilizzazioni"),
    ("attivo_circolante", "Attivo circolante"),
    ("totale_attivo", "Totale attivo"),
    ("patrimonio_netto", "Patrimonio netto"),
    ("debiti_finanziari", "Debiti finanziari"),
    ("debiti_operativi", "Debiti operativi"),
    ("cassa", "Disponibilità liquide"),
    ("ccn", "Capitale circolante netto"),
)


def _tabella(tid: str, title: str, righe: tuple[tuple[str, str], ...], cols: list[Any], attr: str,
             rapporto: tuple[str, str, str] | None) -> dict[str, Any]:
    """Tabella sintetica di pagina: una colonna per periodo, piu' il rapporto
    percentuale fra due colonne (`rapporto` = chiave numeratore, chiave
    denominatore, intestazione), come la Stampa."""
    by = {c.chiave: getattr(c, attr) for c in cols}
    columns = ["Voce", *[c.etichetta for c in cols]] + ([rapporto[2]] if rapporto else [])
    rows = []
    for key, label in righe:
        values: list[Any] = [getattr(getattr(c, attr), key) for c in cols]
        units: list[str | None] = [None] + ["eur"] * len(cols)
        if rapporto:
            num, den = by.get(rapporto[0]), by.get(rapporto[1])
            variazione = _var_pct(getattr(num, key), getattr(den, key)) if num and den else None
            values.append("" if variazione is None else variazione)
            units.append(None if variazione is None else "percent")
        rows.append(s.row(f"{tid}:{key}", [label, *values], units))
    return s.table(tid, title, columns, rows)


def _sp_confronto(model: IntermediateReportModel) -> dict[str, Any]:
    cols = [c for c in model.sp if c.chiave in ("storico", "infrannuale")]
    parziale = model.colonna_sp("infrannuale")
    chart = _chart("intermedio-sp-confronto", "Struttura patrimoniale alla data del periodo", "eur",
                   [c.etichetta for c in cols],
                   [("Totale attivo", [c.sp.totale_attivo for c in cols]),
                    ("Patrimonio netto", [c.sp.patrimonio_netto for c in cols]),
                    ("Debiti finanziari", [c.sp.debiti_finanziari for c in cols])])
    kpis = [
        s.kpi(f"totale attivo · {model.period_months} mesi", parziale.totale_attivo, "eur"),
        s.kpi(f"patrimonio netto · {model.period_months} mesi", parziale.patrimonio_netto, "eur"),
        s.kpi("PFN · infrannuale", _d(model.crisi.infrannuale.indicatori["pfn"]), "eur"),
        s.kpi("capitale circolante netto · infrannuale", parziale.ccn, "eur"),
    ]
    return _page(model, "sp-confronto", "Stato patrimoniale a confronto", "Stato patrimoniale",
                 f"Lo stato patrimoniale è puntuale: i valori a {model.period_months} mesi non si "
                 f"annualizzano e si confrontano così come sono con la chiusura {model.reference_year}.",
                 kpis,
                 [s.chart_block("intermedio-sp-confronto", "Struttura patrimoniale alla data del periodo", chart, []),
                  _tabella("intermedio-sp-confronto-tabella", "Stato patrimoniale sintetico", _SP_RIGHE, cols,
                           "sp", ("infrannuale", "storico", "Infrann. / storico"))],
                 "sp_confronto")


def _ce_proiezione(model: IntermediateReportModel) -> dict[str, Any] | None:
    proiez = model.colonna_ce("proiezione")
    if proiez is None:
        return None
    storico = model.colonna_ce("storico")
    cols = [c for c in model.ce if c.chiave in ("storico", "infrannuale", "proiezione")]
    grafico = [c for c in model.ce if c.chiave in ("storico", "annualizzato", "proiezione")]
    chart = _chart("intermedio-ce-proiezione", "Dall'annualizzato alla proiezione", "eur",
                   [c.etichetta for c in grafico],
                   [("Ricavi", [c.ce.ricavi for c in grafico]), ("EBITDA", [c.ce.ebitda for c in grafico]),
                    ("Risultato netto", [c.ce.risultato_netto for c in grafico])])
    kpis = [
        s.kpi(f"ricavi · proiezione {model.partial_year}", proiez.ricavi, "eur"),
        s.kpi(f"proiezione su storico {model.reference_year}", _var_pct(proiez.ricavi, storico.ricavi), "percent"),
        s.kpi(f"EBITDA · proiezione {model.partial_year}", proiez.ebitda, "eur"),
        s.kpi(f"risultato netto · proiezione {model.partial_year}", proiez.risultato_netto, "eur"),
    ]
    return _page(model, "ce-proiezione", "La proiezione a fine anno: conto economico", "Proiezione",
                 "La proiezione a dodici mesi del motore infrannuale, con le ipotesi della pratica: "
                 "non è l'annualizzazione aritmetica del periodo.",
                 kpis,
                 [s.chart_block("intermedio-ce-proiezione", "Dall'annualizzato alla proiezione", chart, []),
                  _tabella("intermedio-ce-proiezione-tabella", "Conto economico riclassificato", _CE_RIGHE, cols,
                           "ce", ("proiezione", "storico", "Proiez. / storico"))],
                 "ce_proiezione")


def _sp_proiezione(model: IntermediateReportModel) -> dict[str, Any] | None:
    proiez = model.colonna_sp("proiezione")
    if proiez is None:
        return None
    cols = list(model.sp)
    chart = _chart("intermedio-sp-proiezione", "La struttura patrimoniale a fine anno", "eur",
                   [c.etichetta for c in cols],
                   [("Totale attivo", [c.sp.totale_attivo for c in cols]),
                    ("Patrimonio netto", [c.sp.patrimonio_netto for c in cols]),
                    ("Debiti finanziari", [c.sp.debiti_finanziari for c in cols])])
    kpis = [
        s.kpi(f"totale attivo · proiezione {model.partial_year}", proiez.totale_attivo, "eur"),
        s.kpi(f"patrimonio netto · proiezione {model.partial_year}", proiez.patrimonio_netto, "eur"),
        s.kpi(f"disponibilità liquide · proiezione {model.partial_year}", proiez.cassa, "eur"),
        s.kpi("PFN · proiezione", _d(model.crisi.proiezione.indicatori["pfn"]) if model.crisi.proiezione else None,
              "eur"),
    ]
    return _page(model, "sp-proiezione", "La proiezione a fine anno: stato patrimoniale", "Proiezione",
                 f"Lo stato patrimoniale al 31/12/{model.partial_year} che il motore ricava dal conto economico "
                 "proiettato: rotazioni del circolante, imposte, rimborso del debito, cassa di chiusura.",
                 kpis,
                 [s.chart_block("intermedio-sp-proiezione", "La struttura patrimoniale a fine anno", chart, []),
                  _tabella("intermedio-sp-proiezione-tabella", "Stato patrimoniale sintetico", _SP_RIGHE, cols,
                           "sp", ("proiezione", "storico", "Proiez. / storico"))],
                 "sp_proiezione")


# ── Crisi d'impresa: il quadro ───────────────────────────────────────────────


def _crisi_quadro(model: IntermediateReportModel) -> dict[str, Any]:
    cols = _colonne_crisi(model)
    categories = [label for label, _ in cols]

    def serie(key: str) -> list[Any]:
        return [_d(c.indicatori[key]) for _, c in cols]

    equilibrio = _chart("intermedio-crisi-equilibrio", "Equilibrio finanziario e strutturale", "eur", categories,
                        [("Margine di tesoreria", serie("mt")), ("Margine di struttura", serie("ms")),
                         ("PFN", serie("pfn"))])
    debito = _chart("intermedio-crisi-debito", "Sostenibilità del debito", "ratio", categories,
                    [("PFN / EBITDA", serie("pfn_ebitda")), ("DSCR", serie("dscr"))])
    kpis = [s.kpi(f"classe di rischio · {label.lower()}", f"{c.rating.codice} · {c.rating.etichetta}")
            for label, c in cols]
    kpis.append(s.kpi("segnali extracontabili attivi", f"{model.crisi.segnali_attivi} su 7"))
    rows = [s.row(f"intermedio-crisi-classi:{c.chiave}",
                  [label, c.rating.codice, c.rating.etichetta, f"{c.rating.oltre} su 14", str(c.rating.segnali)])
            for label, c in cols]
    tabella = s.table("intermedio-crisi-classi", "Classe di rischio per periodo",
                      ["Periodo", "Classe", "Esito", "Oltre soglia", "Segnali"], rows)
    return _page(model, "crisi-quadro", "Indicatori della crisi d'impresa", "Crisi d'impresa",
                 "Quattordici indicatori con punteggio da 0 a 1 e i sette segnali extracontabili "
                 "compongono la classe di rischio, da A3 (nessun rischio) a D (crisi).",
                 kpis,
                 [s.chart_block("intermedio-crisi-equilibrio", "Equilibrio finanziario e strutturale", equilibrio, []),
                  s.chart_block("intermedio-crisi-debito", "Sostenibilità del debito", debito, []),
                  tabella],
                 None)


# ── Crisi d'impresa: i quindici indicatori ───────────────────────────────────


def _crisi_indicatori(model: IntermediateReportModel) -> dict[str, Any]:
    """La tabella a tutta larghezza, con i KPI in striscia sopra (forma `single`):
    accanto al rail la colonna e' di 126 mm, e su ricavi quasi nulli (AIC SRL,
    9 mesi: 16.000,7%) i valori non ci entrano e la tabella passa alla forma
    impilata, che trabocca. Un grafico in piu' non ci sta."""
    crisi = model.crisi
    cols = _colonne_crisi(model)
    finale_label, finale = cols[-1]
    kpis = [s.kpi(f"oltre soglia · {label.lower()}", f"{c.rating.oltre} su 14") for label, c in cols]
    columns = ["Indicatore"] + [label for label, _ in cols] + ["Esito"]
    rows = []
    for d in crisi.definizioni:
        unit = _UNITA[d.formato]
        values = [_d(c.indicatori[d.chiave]) for _, c in cols]
        rows.append(s.row(f"intermedio-crisi-tabella:{d.chiave}",
                          [d.etichetta, *values, _esito(finale.punteggi[d.chiave])],
                          [None, *([unit] * len(cols)), None]))
    return _page(model, "crisi-indicatori", "Gli indicatori, uno per uno", "Crisi d'impresa",
                 f"Valori per periodo; l'esito è quello della colonna {finale_label.lower()}, "
                 "«oltre soglia» è un punteggio sotto 0,33. Oneri finanziari / fatturato è "
                 "riportato ma non entra nella classe di rischio.",
                 kpis,
                 [s.table("intermedio-crisi-tabella", "I quindici indicatori", columns, rows)],
                 "indicatori", form="single")


# ── Segnali extracontabili ───────────────────────────────────────────────────


def _segnali(model: IntermediateReportModel) -> dict[str, Any]:
    crisi = model.crisi
    attivi = sum(1 for seg in model.segnali if seg.attivo)
    kpis = [s.kpi("segnali extracontabili attivi", f"{attivi} su {len(model.segnali)}"),
            s.kpi(f"classe di rischio · infrannuale {model.period_months}M",
                  f"{crisi.infrannuale.rating.codice} · {crisi.infrannuale.rating.etichetta}")]
    if crisi.proiezione is not None:
        kpis.append(s.kpi(f"classe di rischio · proiezione {model.partial_year}",
                          f"{crisi.proiezione.rating.codice} · {crisi.proiezione.rating.etichetta}"))
    elenco = {"id": "intermedio-segnali", "kind": "segnali", "title": "I sette segnali",
              "entries": [{"n": n, "label": seg.etichetta, "attivo": seg.attivo}
                          for n, seg in enumerate(model.segnali, start=1)]}
    return {"id": "segnali", "title": "Segnali extracontabili", "family": "Crisi d'impresa", "form": "single",
            "subtitle": "Gli inadempimenti che la pratica dichiara: ogni segnale attivo peggiora la classe di "
                        "rischio dell'infrannuale e della proiezione, mai quella dello storico.",
            "kpis": [k for k in kpis if k is not None], "items": [elenco], "comment": ""}


# ── Allegati: i prospetti completi ─────────────────────────────────────────


# Righe per pagina: quelle del finale (`dossier_catalog.allegati.APPENDIX_ROWS_PER_PART`),
# tarate sulla stessa geometria.
RIGHE_PER_PAGINA = 24


def _allegato(statement: Any, lettera: str, rapporto: tuple[str, str, str] | None) -> list[dict[str, Any]]:
    """Il prospetto completo, spezzato in pagine da 24 righe come nel finale.
    `rapporto` = (id periodo numeratore, id periodo denominatore, intestazione):
    la colonna percentuale che la Stampa affiancava al prospetto."""
    periods = list(statement.periods)
    righe = s.appendix_table_rows(statement, periods)
    if rapporto is not None:
        num, den, _ = rapporto
        by_row = {f"row:{statement.id}:{r.id}": r for r in statement.rows}
        for riga in righe:
            origine = by_row[riga["id"]]
            valori = dict(zip((p.id for p in periods), origine.values))
            variazione = (None if origine.kind in ("section", "group")
                          else _var_pct(valori.get(num), valori.get(den)))
            # Senza base (storico a zero o assente) il rapporto non esiste: la
            # cella resta vuota. «n.d.» qui direbbe «dato mancante», e il dato
            # c'e' — e' zero.
            riga["cells"].append("" if variazione is None else s.exact(variazione))
            riga["units"].append(None if variazione is None else "percent")
    columns = ["Voce", *[p.label for p in periods]] + ([rapporto[2]] if rapporto else [])
    parti = s.chunk(righe, RIGHE_PER_PAGINA)
    pagine = []
    for n, parte in enumerate(parti, start=1):
        suffisso = f" · parte {n} di {len(parti)}" if len(parti) > 1 else ""
        pid = f"allegato-{lettera}-{n}"
        pagine.append({"id": pid, "title": f"{lettera} · {statement.title}", "family": "Allegati",
                       "subtitle": f"Allegato {lettera}{suffisso} · valori in euro · n.d. = dato non disponibile.",
                       "kpis": [], "items": [s.table(pid, f"Prospetto completo{suffisso}", columns, parte)],
                       "comment": ""})
    return pagine


def _allegati(model: IntermediateReportModel) -> list[dict[str, Any]]:
    ids_ce = {p.id for p in model.prospetto_ce.periods}
    ids_sp = {p.id for p in model.prospetto_sp.periods}
    rapporto_ce = (("annualizzato", "storico", "Annualizz. / storico")
                   if "annualizzato" in ids_ce else None)
    rapporto_sp = (("proiezione", "storico", "Proiez. / storico") if "proiezione" in ids_sp
                   else ("infrannuale", "storico", "Infrann. / storico"))
    return _allegato(model.prospetto_ce, "A", rapporto_ce) + _allegato(model.prospetto_sp, "B", rapporto_sp)


def documento_titolo(model: IntermediateReportModel) -> str:
    return f"Report infrannuale {model.period_months}M {model.partial_year}"


#: Le pagine che la copertina elenca, nell'ordine del catalogo.
COVER_SECTIONS = ("sintesi", "ce-confronto", "sp-confronto", "ce-proiezione", "sp-proiezione",
                  "crisi-quadro", "crisi-indicatori", "segnali", "allegato-A-1", "allegato-B-1")


def build_inventory(model: IntermediateReportModel) -> list[dict[str, Any]]:
    pages = [p for p in (_copertina(model), _sintesi(model), _ce_confronto(model), _sp_confronto(model),
                         _ce_proiezione(model), _sp_proiezione(model), _crisi_quadro(model),
                         _crisi_indicatori(model), _segnali(model), *_allegati(model)) if p is not None]
    shaped = [_apply_page_form(p) for p in pages]
    shaped[0]["toc"] = [{"label": p["title"], "page": n} for n, p in enumerate(shaped, start=1)
                        if p["id"] in COVER_SECTIONS]
    return shaped
