"""Rilievo 4 della revisione (giro di correzione 1): la protezione di `sp16a`/
`sp17a` dal residuo di quadratura non deve dipendere dall'ORDINE in cui
`_normalize_balance_sheet_cents` cammina a ritroso sul resto del gruppo.

**Il difetto strutturale del lotto, ricomparso sei volte** (`CLAUDE.md` ›
Previsionale): i normalizzatori al centesimo scaricano il residuo su un campo
di dettaglio e lo sovrascrivono in silenzio, a meno che quel campo sia in
`forced_fields`. Prima di questa correzione `sp16a`/`sp17a` (la ripartizione
pregresso/prestito nuovo che il Task 16 scrive di proposito) non erano MAI in
quell'insieme — la revisione ha misurato «zero posature su 44 osservazioni»,
ma per l'ordine con cui il cammino a ritroso incontra `sp16c`/`sp17c` (mai
forzati oggi) PRIMA di arrivare a `sp16a`/`sp17a`, non per una protezione
esplicita: un domani in cui qualcosa forza anche `sp16b`/`sp16c` (o
`sp17b`/`sp17c`) — per esempio un piano di scadenziamento nuovo su quelle voci
— farebbe leggere il residuo direttamente su `sp16a`/`sp17a`, e nessun test
esistente lo vedrebbe perche' nessuno lo simula.

Questo file NON rilancia il motore per intero: chiama direttamente
`ForecastEngine._normalize_balance_sheet_cents` (puro, senza DB) con un
`forced_fields` che SIMULA quella regressione futura — ogni altro campo del
gruppo forzato, `sp16a`/`sp17a` esclusi — e verifica che:

1. SENZA la protezione esplicita (`forced_fields` senza `sp16a`/`sp17a`, come
   il motore li costruiva prima di quel giro), il residuo NON raggiunge più
   `sp16a`/`sp17a`: dal giro di correzione 2 (rilievo I3b) i tre lati
   finanziari `a`/`b`/`c` di ciascun gruppo sono esclusi dal ripiego PER
   CATEGORIA, non per elenco — la vulnerabilità che la prova rossa misurava
   non esiste più, e questo test è il cancello che non la fa riseminare.
2. Con l'intero gruppo forzato il residuo non ricade più nemmeno sul secchio
   di default (che FORZATO lo è per definizione): segue la somma delle righe
   nell'AGGREGATO, che del gruppo è letteralmente la definizione — e resta
   dichiarato in `residuo_quadratura`.
3. L'espressione REALE che `compute_forecast` costruisce ad ogni anno
   (`_declared_sp_fields() | _pregresso_sp_forced_fields(pregresso) |
   _indexed_sp_forced_fields(details) | _BANK_DEBT_SPLIT_FIELDS`) contiene
   sempre `sp16a`/`sp17a`, anche nel caso piu' comune (nessun piano di
   pregresso, nessuna indicizzazione) — cosi' il punto 2 non resta un fatto
   isolato sulla sola costante.
"""
from decimal import Decimal as D

from calculations.forecast_engine import ForecastEngine

SP16A = "sp16a_debiti_banche_breve"
SP17A = "sp17a_debiti_banche_lungo"

# I due gruppi, con un residuo di quadratura DICHIARATO (0,03: l'aggregato
# supera la somma dei dettagli di tre centesimi) su entrambi — un residuo
# nullo non proverebbe nulla, e' esattamente il modo in cui questo difetto e'
# rimasto invisibile ogni volta finora (vedi il rilievo nel docstring).
_DETTAGLI_16 = {
    SP16A: D("1000.00"),
    "sp16b_debiti_altri_finanz_breve": D("200.00"),
    "sp16c_debiti_obbligazioni_breve": D("300.00"),
    "sp16d_debiti_fornitori_breve": D("4000.00"),
    "sp16e_debiti_tributari_breve": D("500.00"),
    "sp16f_debiti_previdenza_breve": D("600.00"),
    "sp16g_altri_debiti_breve": D("700.00"),
}
_DETTAGLI_17 = {
    SP17A: D("2000.00"),
    "sp17b_debiti_altri_finanz_lungo": D("300.00"),
    "sp17c_debiti_obbligazioni_lungo": D("400.00"),
    "sp17d_debiti_fornitori_lungo": D("5000.00"),
    "sp17e_debiti_tributari_lungo": D("600.00"),
    "sp17f_debiti_previdenza_lungo": D("700.00"),
    "sp17g_altri_debiti_lungo": D("800.00"),
}
_RESIDUO = D("0.03")


def _valori():
    valori = dict(_DETTAGLI_16)
    valori["sp16_debiti_breve"] = sum(_DETTAGLI_16.values(), D("0")) + _RESIDUO
    valori.update(_DETTAGLI_17)
    valori["sp17_debiti_lungo"] = sum(_DETTAGLI_17.values(), D("0")) + _RESIDUO
    return valori


# La regressione simulata: ogni campo del gruppo tranne `sp16a`/`sp17a` e'
# gia' forzato (come se un futuro piano di scadenziamento coprisse anche i
# finanziatori diversi dalle banche, o riordinasse il cammino) — il caso
# ESATTO in cui, senza una protezione esplicita, il cammino a ritroso
# raggiunge `sp16a`/`sp17a` prima di fermarsi.
_REGRESSIONE_SIMULATA = frozenset({
    "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
    "sp16d_debiti_fornitori_breve", "sp16e_debiti_tributari_breve",
    "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve",
    "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
    "sp17d_debiti_fornitori_lungo", "sp17e_debiti_tributari_lungo",
    "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo",
})


def test_senza_la_protezione_esplicita_il_residuo_non_raggiunge_piu_sp16a_sp17a():
    """Giro 2 (I3b): la vulnerabilita' strutturale che questo test dimostrava
    — cammino a ritroso libero di arrivare ad `a` quando tutto il resto e'
    forzato — e' stata ELIMINATA alla radice: `a`/`b`/`c` sono esclusi dal
    ripiego PER CATEGORIA (debito finanziario: confine PFN e confine del
    rendiconto), non per elenco e non per ordine. Qui restano FUORI da
    `forced_fields` — la mutazione originale del test — eppure non si
    muovono: il centesimo segue la somma delle righe, che e' la sua
    definizione (riga `sp16 = sp16a + … + sp16g`)."""
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori(), forced_fields=_REGRESSIONE_SIMULATA, recompute_cash=False,
    )
    assert esito[SP16A] == D("1000.00"), (
        f"il cammino ha ancora raggiunto sp16a: {esito[SP16A]}"
    )
    assert esito[SP17A] == D("2000.00"), (
        f"il cammino ha ancora raggiunto sp17a: {esito[SP17A]}"
    )
    # Stesso divieto per `b` e `c`, che prima erano al riparo solo perche'
    # nessuno li forzava mai: ora lo sono di diritto.
    assert esito["sp16b_debiti_altri_finanz_breve"] == D("200.00")
    assert esito["sp16c_debiti_obbligazioni_breve"] == D("300.00")
    assert esito["sp17b_debiti_altri_finanz_lungo"] == D("300.00")
    assert esito["sp17c_debiti_obbligazioni_lungo"] == D("400.00")
    # E il residuo dov'e' finito? Da nessuna riga: nell'aggregato, dichiarato.
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0"))
    assert esito["sp17_debiti_lungo"] == sum(_DETTAGLI_17.values(), D("0"))


def test_con_bank_debt_split_fields_il_residuo_non_tocca_mai_sp16a_sp17a():
    """La correzione: unire `_BANK_DEBT_SPLIT_FIELDS` a `forced_fields` — quello
    che `compute_forecast` fa oggi, sempre — protegge `sp16a`/`sp17a` anche
    sotto la STESSA regressione simulata sopra. La protezione non dipende
    dall'ordine: dipende dall'essere elencati, punto."""
    forzati = _REGRESSIONE_SIMULATA | ForecastEngine._BANK_DEBT_SPLIT_FIELDS
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori(), forced_fields=forzati, recompute_cash=False,
    )
    assert esito[SP16A] == D("1000.00"), f"sp16a spostato: {esito[SP16A]}"
    assert esito[SP17A] == D("2000.00"), f"sp17a spostato: {esito[SP17A]}"
    # Un centesimo va pur posato da qualche parte (docstring della funzione):
    # con l'intero gruppo forzato NON ricade piu' sul secchio di default (che
    # forzato e' per definizione, e la dichiarazione sua — piano o indice che
    # sia — resterebbe bugiarda): lo segue la somma delle righe, l'aggregato.
    assert esito["sp16g_altri_debiti_breve"] == D("700.00")
    assert esito["sp17g_altri_debiti_lungo"] == D("800.00")
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0"))
    assert esito["sp17_debiti_lungo"] == sum(_DETTAGLI_17.values(), D("0"))


def test_riordinare_il_cammino_non_rompe_piu_la_protezione():
    """Variante della stessa mutazione: forzare SOLO `sp16c`/`sp17c` (il campo su
    cui oggi il cammino si ferma per caso) non deve bastare a mettere in dubbio
    la protezione — perche' la protezione non passa piu' da li'."""
    forzati = (
        frozenset({"sp16c_debiti_obbligazioni_breve", "sp17c_debiti_obbligazioni_lungo"})
        | ForecastEngine._BANK_DEBT_SPLIT_FIELDS
    )
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori(), forced_fields=forzati, recompute_cash=False,
    )
    assert esito[SP16A] == D("1000.00")
    assert esito[SP17A] == D("2000.00")


def test_bank_debt_split_fields_e_esattamente_i_due_campi():
    assert ForecastEngine._BANK_DEBT_SPLIT_FIELDS == frozenset({SP16A, SP17A})


def test_compute_forecast_forza_sempre_sp16a_sp17a_anche_nel_caso_piu_comune():
    """L'espressione REALE che `compute_forecast` costruisce ad ogni anno
    (`_declared_sp_fields() | _pregresso_sp_forced_fields(pregresso) |
    _indexed_sp_forced_fields(details) | _BANK_DEBT_SPLIT_FIELDS`) contiene
    sempre `sp16a`/`sp17a` — anche nel caso piu' comune di tutti, nessun piano
    di pregresso e nessuna indicizzazione, dove gli altri tre addendi sono
    vuoti e solo `_BANK_DEBT_SPLIT_FIELDS` porta la protezione."""
    forzati = (
        ForecastEngine._declared_sp_fields()
        | ForecastEngine._pregresso_sp_forced_fields(None)
        | ForecastEngine._indexed_sp_forced_fields(None)
        | ForecastEngine._BANK_DEBT_SPLIT_FIELDS
    )
    assert SP16A in forzati and SP17A in forzati
