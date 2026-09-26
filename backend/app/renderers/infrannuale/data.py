"""Il modello del report infrannuale: numeri del motore allineati alle colonne C, 6M, Ann., F.

Fonte unica: IntermediateReportModel (`assemble_intermedio`). Gli indicatori vengono da `crisi_infrannuale`, per
periodo, e non si ricalcolano (spec §5). Qui si sommano e si sottraggono righe già presenti; un valore assente resta
None fino alla stampa, dove diventa «n.d.».
"""
from __future__ import annotations

import calendar
import json
import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal, Optional

Num = Optional[Decimal]
Kind = Literal["C", "6M", "Ann", "F"]

#: Chiavi delle colonne nel modello dell'intermedio, nell'ordine di stampa.
STORICO, INFRANNUALE, ANNUALIZZATO, PROIEZIONE = "storico", "infrannuale", "annualizzato", "proiezione"


@dataclass(frozen=True)
class Col:
    key: str
    label: str
    kind: Kind


@dataclass(frozen=True)
class CrisiCol:
    codice: str
    etichetta: str
    oltre: int
    segnali: int
    indicatori: dict
    punteggi: dict

    @property
    def classe(self) -> str:
        return f"{self.codice} · {self.etichetta}"


@dataclass(frozen=True)
class AnnexRow:
    label: str
    level: int
    kind: str
    values: tuple
    code: str = ""


@dataclass(frozen=True)
class InfrannualeData:
    company_name: str
    period_months: int
    reference_year: int
    partial_year: int
    period_end: str
    ce_cols: tuple
    sp_cols: tuple
    values: dict
    crisi: dict = field(default_factory=dict)
    definizioni: tuple = ()
    segnali: tuple = ()
    annex_ce: tuple = ()
    annex_sp: tuple = ()

    # -------------------------------------------------------------- lettura
    def v(self, key: str, col: str) -> Num:
        return self.values.get(key, {}).get(col)

    def var(self, key: str, col: str, base: str = STORICO) -> Num:
        """Variazione percentuale di `col` su `base` (v/b − 1): None se manca un termine o la base è zero.

        Sui valori ai centesimi, come il riferimento (1.224,51% sugli altri proventi finanziari di AMBIENTA; sugli
        importi all'euro verrebbe 1.224,63%).
        """
        v, b = self.v(key, col), self.v(key, base)
        if v is None or b is None or b == 0:
            return None
        return (v / b - 1) * 100

    @property
    def has_forecast(self) -> bool:
        return any(c.key == PROIEZIONE for c in self.sp_cols)

    @property
    def has_annualized(self) -> bool:
        return any(c.key == ANNUALIZZATO for c in self.ce_cols)

    @property
    def partial_label(self) -> str:
        return f"{self.period_months}M {self.partial_year}"

    @property
    def forecast_label(self) -> str:
        return f"{self.partial_year} F"

    @property
    def reference_label(self) -> str:
        return f"{self.reference_year} C"

    @property
    def legend(self) -> str:
        parts = ["C = consuntivo", f"{self.period_months}M = infrannuale al {self.period_end}"]
        if self.has_annualized:
            parts.append("Ann. = annualizzato")
        if self.has_forecast:
            parts.append("F = forecast")
        return " · ".join(parts)

    @property
    def header_title(self) -> str:
        base = f"Report infrannuale {self.partial_label}"
        return base + (f" e forecast {self.partial_year}" if self.has_forecast else "")

    def label_of(self, col: str) -> str:
        return next(c.label for c in self.ce_cols + self.sp_cols if c.key == col)


# ------------------------------------------------------------------ helpers
def _dec(x) -> Num:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    f = float(x)
    if math.isnan(f) or math.isinf(f):
        return None
    return Decimal(str(x))


def _euro(x: Num) -> Num:
    return None if x is None else x.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _add(*xs) -> Num:
    return None if any(x is None for x in xs) else sum(xs, Decimal(0))


def _neg(x) -> Num:
    return None if x is None else -x


#: chiave del report → codice di riga del prospetto (il codice di una riga composta è la somma dei suoi codici)
_CE_ROWS = {
    "altri_proventi_fin": "ce14_altri_proventi_finanziari",
    "materie": "ce05_materie_prime", "servizi": "ce06_servizi", "godimento": "ce07_godimento_beni",
    "personale": "ce08_costi_personale", "var_rim_materie": "ce10_var_rimanenze_mat_prime",
    "oneri_diversi": "ce12_oneri_diversi", "totale_costi_produzione": "production_cost",
}
_SP_ROWS = {
    "ratei_attivi": "sp10_ratei_risconti_attivi",
    "crediti_clienti_breve": "sp06a_crediti_clienti_breve", "crediti_clienti_lungo": "sp07a_crediti_clienti_lungo",
    "rimanenze": "sp05_rimanenze",
    "fornitori": "sp16d_debiti_fornitori_breve+sp17d_debiti_fornitori_lungo",
    "banche": "sp16a_debiti_banche_breve+sp17a_debiti_banche_lungo",
    "banche_breve": "sp16a_debiti_banche_breve", "banche_lungo": "sp17a_debiti_banche_lungo",
    "altri_finanziatori": "sp16b_debiti_altri_finanz_breve+sp17b_debiti_altri_finanz_lungo",
    "altri_finanziatori_breve": "sp16b_debiti_altri_finanz_breve",
    "altri_finanziatori_lungo": "sp17b_debiti_altri_finanz_lungo",
    "debiti_previdenziali": "sp16f_debiti_previdenza_breve+sp17f_debiti_previdenza_lungo",
    "debiti_tributari": "sp16e_debiti_tributari_breve+sp17e_debiti_tributari_lungo",
    "immob_finanziarie": "sp04_immob_finanziarie",
}
_CE_AGG = ("ricavi", "valore_produzione", "costi_operativi", "ebitda", "ammortamenti", "ebit",
           "risultato_ante_imposte", "risultato_netto")
_SP_AGG = {"immobilizzazioni": "immobilizzazioni", "attivo_circolante": "attivo_circolante",
           "totale_attivo": "totale_attivo", "patrimonio_netto": "patrimonio_netto",
           "debiti_finanziari": "debiti_finanziari", "debiti_operativi": "debiti_operativi",
           "liquidita": "cassa", "ccn_sp": "ccn"}
#: indicatori del motore della crisi letti così come sono
CRISI_KEYS = ("dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms", "copertura_immob", "indipendenza", "pfn",
              "pfn_ebitda", "roi", "roe", "ros", "of_mol", "of_revenue")

#: rapporto → grezzo del suo denominatore (come `DENOMINATORE_DEL_RAPPORTO` in frontend/lib/pratica-indicators.ts).
#: `crisi_impresa._div` restituisce 0 su denominatore nullo: zero oneri finanziari è copertura infinita, non un DSCR
#: di 0,000×, e un ROE su patrimonio netto negativo cambia segno per il denominatore, non per la redditività.
DENOMINATORE = {"pfn_ebitda": "_ebitda_raw", "of_mol": "_ebitda_raw",
                "ebitda_margin": "_revenue_raw", "of_revenue": "_revenue_raw", "ros": "_revenue_raw",
                "materials_revenue": "_revenue_raw", "services_revenue": "_revenue_raw",
                "roi": "_total_assets_raw", "roe": "_equity_raw", "dscr": "_oneri_finanziari_raw"}
_NEUTRO = Decimal("0.5")


def senza_denominatore(indicatori: dict, punteggi: dict) -> tuple[dict, dict]:
    """Un rapporto senza denominatore positivo è n.d. Il suo esito cade quando il motore ha dato il NEUTRO (il «non
    lo so»); resta quando ha dato un verdetto, come la PFN positiva senza EBITDA."""
    ind, pun = dict(indicatori), dict(punteggi)
    for k, den in DENOMINATORE.items():
        raw = ind.get(den)
        if k in ind and raw is not None and raw <= 0:
            ind[k] = None
            if pun.get(k) == _NEUTRO:
                pun[k] = None
    return ind, pun


def _statement(st) -> tuple[dict, tuple]:
    """Indice codice → {colonna: valore} e righe d'allegato di un prospetto dettagliato."""
    ids = [p.id for p in st.periods]
    by_code, annex = {}, []
    for r in st.rows:
        vals = tuple(_dec(x) for x in r.values)
        by_code[r.code] = dict(zip(ids, vals))
        annex.append(AnnexRow(r.label.strip(), r.level, r.kind, vals, r.code))
    return by_code, tuple(annex)


def _period_end(year: int, months: int) -> str:
    return f"{calendar.monthrange(year, months)[1]:02d}.{months:02d}.{year}"


# ------------------------------------------------------------------ ingresso
def from_intermedio(model) -> InfrannualeData:
    m, anno, rif = model.period_months, model.partial_year, model.reference_year
    kinds = {STORICO: ("C", f"{rif} C"), INFRANNUALE: ("6M", f"{m}M {anno}"),
             ANNUALIZZATO: ("Ann", f"Ann. {anno}"), PROIEZIONE: ("F", f"{anno} F")}
    ce_cols = tuple(Col(c.chiave, kinds[c.chiave][1], kinds[c.chiave][0]) for c in model.ce)
    sp_cols = tuple(Col(c.chiave, kinds[c.chiave][1], kinds[c.chiave][0]) for c in model.sp)

    values: dict = {}

    def put(key, col, val):
        values.setdefault(key, {})[col] = _dec(val)

    for c in model.ce:
        for k in _CE_AGG:
            put(k, c.chiave, getattr(c.ce, k))
        put("oneri_finanziari", c.chiave, _neg(c.ce.oneri_finanziari))
        put("imposte", c.chiave, _neg(c.ce.imposte))
    for c in model.sp:
        for k, attr in _SP_AGG.items():
            put(k, c.chiave, getattr(c.sp, attr))

    ce_rows, annex_ce = _statement(model.prospetto_ce)
    sp_rows, annex_sp = _statement(model.prospetto_sp)
    for k, code in _CE_ROWS.items():
        for col, val in ce_rows.get(code, {}).items():
            put(k, col, val)
    for k, code in _SP_ROWS.items():
        for col, val in sp_rows.get(code, {}).items():
            put(k, col, val)
    for c in sp_cols:
        g = lambda k: values.get(k, {}).get(c.key)  # noqa: E731
        put("crediti_clienti", c.key, _add(g("crediti_clienti_breve"), g("crediti_clienti_lungo")))
        # somma degli importi all'euro stampati nelle righe: la tabella si rifà a mano (833.386, non 833.385)
        cred, rim, forn = (_euro(g(k)) for k in ("crediti_clienti", "rimanenze", "fornitori"))
        put("cc_comm", c.key, None if None in (cred, rim, forn) else cred + rim - forn)

    crisi = {}
    for key in (STORICO, INFRANNUALE, PROIEZIONE):
        col = getattr(model.crisi, key, None)
        if col is None:
            continue
        ind, pun = senza_denominatore({k: _dec(v) for k, v in col.indicatori.items()},
                                      {k: _dec(v) for k, v in col.punteggi.items()})
        crisi[key] = CrisiCol(col.rating.codice, col.rating.etichetta, col.rating.oltre, col.rating.segnali, ind, pun)
        for k in CRISI_KEYS:
            put(k, key, ind.get(k))
    if INFRANNUALE in crisi and any(c.key == ANNUALIZZATO for c in ce_cols):
        put("ebitda_margin", ANNUALIZZATO, values.get("ebitda_margin", {}).get(INFRANNUALE))

    return InfrannualeData(
        company_name=model.company_name, period_months=m, reference_year=rif, partial_year=anno,
        period_end=_period_end(anno, m), ce_cols=ce_cols, sp_cols=sp_cols, values=values, crisi=crisi,
        definizioni=tuple((d.chiave, d.etichetta, d.formato, d.nel_punteggio) for d in model.crisi.definizioni),
        segnali=tuple((s.chiave, s.etichetta, s.attivo) for s in model.segnali),
        annex_ce=annex_ce, annex_sp=annex_sp,
    )


# ------------------------------------------------------------------ JSON del banco
def _enc(x) -> Optional[str]:
    return None if x is None else str(x)


def dump_json(d: InfrannualeData) -> dict:
    return {
        "company_name": d.company_name, "period_months": d.period_months, "reference_year": d.reference_year,
        "partial_year": d.partial_year, "period_end": d.period_end,
        "ce_cols": [c.__dict__ for c in d.ce_cols], "sp_cols": [c.__dict__ for c in d.sp_cols],
        "values": {k: {c: _enc(x) for c, x in v.items()} for k, v in d.values.items()},
        "crisi": {k: {"codice": c.codice, "etichetta": c.etichetta, "oltre": c.oltre, "segnali": c.segnali,
                      "indicatori": {i: _enc(x) for i, x in c.indicatori.items()},
                      "punteggi": {i: _enc(x) for i, x in c.punteggi.items()}} for k, c in d.crisi.items()},
        "definizioni": [list(x) for x in d.definizioni], "segnali": [list(x) for x in d.segnali],
        "annex_ce": [[r.label, r.level, r.kind, [_enc(x) for x in r.values], r.code] for r in d.annex_ce],
        "annex_sp": [[r.label, r.level, r.kind, [_enc(x) for x in r.values], r.code] for r in d.annex_sp],
    }


def load_json(path) -> InfrannualeData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    dec = lambda x: None if x is None else Decimal(x)  # noqa: E731
    return InfrannualeData(
        company_name=raw["company_name"], period_months=raw["period_months"], reference_year=raw["reference_year"],
        partial_year=raw["partial_year"], period_end=raw["period_end"],
        ce_cols=tuple(Col(**c) for c in raw["ce_cols"]), sp_cols=tuple(Col(**c) for c in raw["sp_cols"]),
        values={k: {c: dec(x) for c, x in v.items()} for k, v in raw["values"].items()},
        crisi={k: CrisiCol(c["codice"], c["etichetta"], c["oltre"], c["segnali"],
                           {i: dec(x) for i, x in c["indicatori"].items()},
                           {i: dec(x) for i, x in c["punteggi"].items()}) for k, c in raw.get("crisi", {}).items()},
        definizioni=tuple(tuple(x) for x in raw.get("definizioni", [])),
        segnali=tuple(tuple(x) for x in raw.get("segnali", [])),
        annex_ce=tuple(AnnexRow(r[0], r[1], r[2], tuple(dec(x) for x in r[3]), *r[4:5])
                       for r in raw.get("annex_ce", [])),
        annex_sp=tuple(AnnexRow(r[0], r[1], r[2], tuple(dec(x) for x in r[3]), *r[4:5])
                       for r in raw.get("annex_sp", [])),
    )
