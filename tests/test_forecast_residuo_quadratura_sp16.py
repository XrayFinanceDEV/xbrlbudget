"""Rilievo I3 della revisione finale: il residuo di quadratura atterrava su
`sp16c`/`sp17c` (obbligazioni) — su scenari SENZA piano e SENZA indicizzazione,
e con segno negativo su aziende che di obbligazioni non ne hanno.

La causa era doppia, e doppia e' la prova:

* **(a)** `compute_forecast` includeva `_declared_sp_fields()` in `forced_fields`
  **sempre**, congelando cosi' le 8 righe dei quattro saldi anche quando nessun
  piano le scriveva: con il secchio `sp16g` forzato e `a` protetto, il cammino a
  ritroso posava il residuo sul primo campo libero — `sp16c`, un confine PFN e
  (dopo questo lotto) il confine operativo/finanziario del rendiconto. La
  sonda 40f0332 vs head su uno scenario a 5 anni, via tributaria manuale, senza
  piano ne' indicizzazione, misurava la divergenza su 6 percentuali di crescita
  su 8 (G=1,11 → +0,01/+0,02 dal 2028; G=2,22 → −0,01…−0,02; G=7,77 → −0,01 per
  quattro anni). Qui si fissa il lato pulito: su quello scenario `sp16c`/`sp17c`
  e gli altri finanziari NON SI MUOVONO MAI, e ogni posatura finita in
  `residuo_quadratura` nomina solo il proprio secchio o il proprio aggregato.

* **(b)** Il ripiego del cammino ora esclude PER CATEGORIA `a`/`b`/`c`
  (`_BANK_DEBT_FIELDS_SP16`/`_SP17`), e quando non resta nessun operativo libero
  il residuo non torna piu' sul secchio (che forzato e' per definizione):
  segue la somma delle righe nell'AGGREGATO, perche' l'aggregato del gruppo
  DEBITI E' la loro somma (riga `sp16 = sp16a + … + sp16g`).

  ~~Ma questo vale solo se l'aggregato stesso non e' forzato: un `sp_overrides`
  su `sp16` fissa il totale, e li' il centesimo resta al secchio, dichiarato.~~
  **Falso**, ed e' il rilievo I-1 della revisione di `6e5c0f7`: quella frase
  descriveva un ramo che `compute_forecast` non raggiungeva MAI (gli
  `sp_overrides` non entravano in `forced_fields`), e su cui questo stesso file
  aveva un test costruito a mano. Ora l'aggregato forzato entra, il ramo e'
  reale, e la risposta e' un RIFIUTO: li' il residuo non e' un centesimo di
  arrotondamento bensi' la MASSA dell'override (sonda `AO16`: 31.666,66 di
  cassa in meno sotto un `forecast_generated: true`, su 40 anni su 40).

* **(c)** L'insieme dei campi forzati lo costruisce UNA funzione,
  `_sp_forced_fields`, e il selettore dei dichiarati e' PER GRUPPO: un'
  indicizzazione della sola `sp17g` non puo' togliere il ripiego al gruppo
  `sp16` (rilievo I-2, tabella in laboratorio: `sp16_debiti_breve` −0,01).
"""
from decimal import Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import ForecastEngine
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, read_forecast_maps

from tests.test_forecast_dichiarato_vs_persistito import (
    _base_year, INVESTIMENTI_SOTTO_CENTESIMO, PIANI,
)

# Le righe FINANZIARIE dei due gruppi: mai destinazione di un residuo.
_FINANZIARIE = (
    "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
    "sp16c_debiti_obbligazioni_breve", "sp17a_debiti_banche_lungo",
    "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
)
_DESTINAZIONI_AMMESSE = {
    "sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo",
    "sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo",
    "sp16e_debiti_tributari_breve", "sp17e_debiti_tributari_lungo",
    "sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo",
    "sp16_debiti_breve", "sp17_debiti_lungo",   # reintegro dell'aggregato
}


@pytest.mark.parametrize("crescita", ["1.11", "2.22", "7.77"])
def test_scenario_quinquennale_legacy_i_finanziari_non_si_muovono_mai(monkeypatch, crescita):
    """Lo scenario esatto della sonda della revisione: fixture con massa su ogni
    voce (il `_base_year` della batteria dichiarato-vs-persistito), 5 anni, via
    tributaria MANUALE (le tre percentenze `sp*e_growth_pct` a zero), nessun
    piano, nessuna indicizzazione, nessuno scoperto. Un atterraggio su una riga
    diversa dal proprio secchio/aggregato appare in `residuo_quadratura` — e li'
    i nomi dei sei finanziari non devono comparire MAI. (La sonda della
    revisione misurava il centesimo anche su questo percorso; qui non si
    riproduce: senza rate a terzi l'aggregato coincide col totale delle righe
    al centesimo e il residuo e' zero — il test resta come guardia, il red
    lo porta il test col piano qui sotto.)"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    user = f"i3-legacy-{crescita}"
    try:
        with sessions() as db:
            company_id = _base_year(db, user)
            rows = [
                {"forecast_year": y, "revenue_growth_pct": D(crescita),
                 "sp06e_growth_pct": 0, "sp16e_growth_pct": 0, "sp17e_growth_pct": 0,
                 **INVESTIMENTI_SOTTO_CENTESIMO}
                for y in range(2027, 2032)
            ]
            sc = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="i3", base_year=2026,
                                     scenario_type="budget"),
                user_id=user, db=db)
            res = budget_scenarios.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
                user_id=user, db=db)
            assert res["forecast_generated"] is True, res["message"]
            for _year, bs, _ce in read_forecast_maps(db, sc.id):
                # Il fixture non ha obbligazioni: devono restarci a zero per sempre.
                for campo in _FINANZIARIE:
                    if campo.endswith("obbligazioni_breve") or campo.endswith("obbligazioni_lungo"):
                        assert bs[campo] == D("0.00"), \
                            f"{campo} si e' mosso: {bs[campo]}"
            prev = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=user, db=db)
            for anno in prev["forecast_years"]:
                for posa in anno["details"].get("residuo_quadratura") or []:
                    assert posa["campo"] in _DESTINAZIONI_AMMESSE, (
                        f"{anno['year']}: residuo {posa['importo']} posato su "
                        f"{posa['campo']} — fuori dal gruppo operativo")
    finally:
        engine.dispose()


@pytest.mark.parametrize("nome_piano", ["altri debiti", "fornitori + tributari"])
@pytest.mark.parametrize("crescita", ["1.11", "3.33"])
def test_piano_quinquennale_il_residuo_non_raggiunge_i_finanziari(
        monkeypatch, nome_piano, crescita):
    """La riproduzione esatta della misura della revisione: piano con rate a
    terzi (le uniche che producono frazioni sotto il centesimo), 5 anni.
    Sulla testa precedente il `residuo_quadratura` nomina
    `sp16c_debiti_obbligazioni_breve` per −0,01 (misurato: 2027/2028 su
    entrambi i piani) — debito obbligazionario NEGATIVO su un'azienda che non
    ne ha, scritto da un centesimo di arrotondamento. Qui si fissa che nessun
    finanziario riceve posature e che le obbligazioni restano a zero."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    user = f"i3-piano-{nome_piano}-{crescita}"
    try:
        with sessions() as db:
            company_id = _base_year(db, user)
            rows = [{"forecast_year": y, "revenue_growth_pct": D(crescita)}
                    for y in range(2027, 2032)]
            rows[0]["pregresso"] = PIANI[nome_piano]
            sc = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="i3p", base_year=2026,
                                     scenario_type="budget"),
                user_id=user, db=db)
            res = budget_scenarios.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
                user_id=user, db=db)
            assert res["forecast_generated"] is True, res["message"]
            prev = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=user, db=db)
            for anno in prev["forecast_years"]:
                for posa in anno["details"].get("residuo_quadratura") or []:
                    assert posa["campo"] not in _FINANZIARIE, (
                        f"{anno['year']}: residuo {posa['importo']} posato su "
                        f"{posa['campo']} — il cammino raggiunge ancora il "
                        f"debito finanziario")
            for _year, bs, _ce in read_forecast_maps(db, sc.id):
                assert bs["sp16c_debiti_obbligazioni_breve"] == D("0.00"), \
                    f"{_year}: obbligazioni a {bs['sp16c_debiti_obbligazioni_breve']}"
                assert bs["sp17c_debiti_obbligazioni_lungo"] == D("0.00"), \
                    f"{_year}: obbligazioni lunghe a {bs['sp17c_debiti_obbligazioni_lungo']}"
    finally:
        engine.dispose()


# ── (b) la regola del reintegro, in laboratorio ──
#
# Stessa palestra di `test_forecast_residuo_sp16a_sp17a.py`: la normalizzazione
# chiamata diretta, senza DB. Qui si fissa PERO' il discrimine nuovo: il
# reintegro dell'aggregato scatta quando NON RESTA nessun operativo libero,
# e non scatta (non deve scattare) se ne resta uno: il centesimo va a lui,
# che e' il comportamento di sempre.

_DETTAGLI_16 = {
    "sp16a_debiti_banche_breve": D("1000.00"),
    "sp16b_debiti_altri_finanz_breve": D("200.00"),
    "sp16c_debiti_obbligazioni_breve": D("300.00"),
    "sp16d_debiti_fornitori_breve": D("4000.00"),
    "sp16e_debiti_tributari_breve": D("500.00"),
    "sp16f_debiti_previdenza_breve": D("600.00"),
    "sp16g_altri_debiti_breve": D("700.00"),
}
_RESIDUO = D("0.03")


def _valori_16():
    v = dict(_DETTAGLI_16)
    v["sp16_debiti_breve"] = sum(_DETTAGLI_16.values(), D("0")) + _RESIDUO
    return v


def test_operativo_libero_il_residuo_va_a_lui_non_all_aggregato():
    """Con `d`/`e`/`g` forzati ma `f` libero, il residuo va su `f`: il
    reintegro dell'aggregato e' il ripiego dei ripieghi, non la prima scelta."""
    forzati = frozenset({
        "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
        "sp16d_debiti_fornitori_breve", "sp16e_debiti_tributari_breve",
        "sp16g_altri_debiti_breve", "sp16a_debiti_banche_breve",
    })
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori_16(), forced_fields=forzati, recompute_cash=False,
    )
    assert esito["sp16f_debiti_previdenza_breve"] == D("600.00") + _RESIDUO
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0")) + _RESIDUO


def test_aggregato_forzato_senza_niente_di_libero_si_rifiuta():
    """Gruppo interamente forzato E aggregato fissato da `sp_overrides`: non e'
    un arrotondamento da posare, e' la massa dell'override (rilievo I-1 della
    revisione di `6e5c0f7`), e nessun posto la accetta in onesta'.

    La versione precedente di questo test asseriva il contrario («il centesimo
    resta sul secchio e lo dichiara `residuo_quadratura`»), e il suo docstring
    era cio' che la revisione chiamava «falso sul percorso reale»: il ramo
    `aggregate in forced_fields` non veniva mai raggiunto da `compute_forecast`,
    perche' gli `sp_overrides` non entravano in `forced_fields` — lo esercitava
    solo questo test, costruito a mano. Da ora l'aggregato FORZATO ci entra
    (quando nessuna sua voce lo e'), quindi il ramo e' reale, e la sua risposta
    e' un rifiuto: la misura della revisione (sonda `AO16`) dice che
    sull'altra strada si perdono 31.666,66 di cassa sotto un
    `forecast_generated: true`, e che la cifra persistita (118.333,34) non e'
    quella chiesta (150.000).
    """
    forzati = frozenset(_DETTAGLI_16) | {"sp16_debiti_breve"}
    with pytest.raises(ValueError) as rv:
        ForecastEngine._normalize_balance_sheet_cents(
            _valori_16(), forced_fields=forzati, recompute_cash=False, details={},
        )
    assert "sp16_debiti_breve" in str(rv.value)
    assert "Forza una voce di dettaglio" in str(rv.value)


def test_aggregato_forzato_senza_residuo_non_si_rifiuta():
    """Il rifiuto e' per la MASSA che non ha dove andare, non per la cella
    forzata in se': se l'aggregato forzato coincide con la somma delle righe
    il `if not residual: continue` sopra congela tutto, e la forzatura passa
    (e' il caso documentato di `API-PREVISIONALE.md` §… — «un `sp_overrides` su
    `sp16a` o sul suo aggregato fissa il totale: vince»)."""
    valori = _valori_16()
    valori["sp16_debiti_breve"] = sum(_DETTAGLI_16.values(), D("0"))
    esito = ForecastEngine._normalize_balance_sheet_cents(
        valori, forced_fields=frozenset(_DETTAGLI_16) | {"sp16_debiti_breve"},
        recompute_cash=False, details={},
    )
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0"))


def test_reintegro_dell_aggregato_quando_non_resta_niente_libero():
    """Gruppo interamente forzato, aggregato NO: segue la somma delle righe,
    e la posatura nomina l'aggregato (chiave dichiarata anche qui)."""
    forzati = frozenset(_DETTAGLI_16)
    details = {}
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori_16(), forced_fields=forzati, recompute_cash=False, details=details,
    )
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0"))
    for campo, val in _DETTAGLI_16.items():
        assert esito[campo] == val, f"{campo} mosso: {esito[campo]} != {val}"
    assert details["residuo_quadratura"] == [{"campo": "sp16_debiti_breve",
                                              "importo": -_RESIDUO}]


# ─────────────── I-1: l'aggregato forzato, sul percorso di servizio ───────────────

def _esito_aggregato(db, user, tag, piano=None, indice=None, anno_forza=2027,
                     manuale=False):
    """Bulk reale, `sp_overrides` sull'AGGREGATO `sp16_debiti_breve` in ogni anno."""
    company_id = _base_year(db, user)
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name=tag, base_year=2026,
                                         scenario_type="budget"), user_id=user, db=db)
    ov = {"sp16_debiti_breve": "150000.00"}
    if anno_forza is not None:
        rows = [dict(forecast_year=y, revenue_growth_pct=D("3.33"), sp_overrides=dict(ov))
                for y in (2027, 2028, 2029)]
    else:
        rows = [dict(forecast_year=y, revenue_growth_pct=D("3.33")) for y in (2027, 2028, 2029)]
    if manuale:
        # La VIA MANUALE fiscale (le percentuali esplicite che fanno
        # `manual_tax_position`): l'unica rotta che porta `sp16e` fuori dal
        # calendario anche senza piano, e l'abbinamento con l'indice era da
        # provare (rilievo m-E, punto 4).
        for r in rows:
            r["sp06e_growth_pct"] = 0
            r["sp16e_growth_pct"] = 0
    if piano is not None:
        rows[0]["pregresso"] = piano
    if indice is not None:
        rows[0]["sp_indexing"] = indice
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
        user_id=user, db=db)
    return res, sc.id, rows


def test_piano_altri_aggregato_forzato_si_rifiuta_e_non_lascia_nulla(monkeypatch):
    """Rilievo I-1: piano `altri_debiti` + `sp_overrides` su `sp16` = 150.000.

    Su `6e5c0f7` risponda `forecast_generated: true` e persisteva 118.333,34:
    la meta' dell'override sparita, la cassa a 73.661,89 invece di 105.328,55,
    e `residuo_quadratura` che lo annotava per −31.666,66 senza che nessuna
    schermata lo legga. Ora e' un rifiuto, e il rifiuto non lascia niente: la
    prova distruttiva (un `PUT /assumptions` successivo senza override)
    dimostra che la cella contesa non era rimasta scritta.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, sid, _rows = _esito_aggregato(db, "i1-piano", "x",
                                               piano=PIANI["altri debiti"])
            assert res["forecast_generated"] is False, res["message"]
            assert "sp16_debiti_breve" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == [], "un previsionale monco e' persistito"
    finally:
        engine.dispose()


def test_indicizzazione_solo_sp17g_non_rifiuta_l_aggregato_sp16(monkeypatch):
    """Rilievo I-2, parte di servizio: l'indice su `sp17g` toglie il ripiego al
    gruppo `sp17`, NON al gruppo `sp16`. Con la condizione globale di
    `6e5c0f7` un override di `sp16` si sarebbe rifiutato anche qui (la revisione
    lo nota: «con la correzione di I-1, lo stesso errore farebbe RIFIUTARE un
    override di `sp16` che ha il secchio libero»).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, sid, _rows = _esito_aggregato(db, "i2-indice-17g", "x",
                                               indice={"sp17g": "ricavi"})
            assert res["forecast_generated"] is True, res["message"]
    finally:
        engine.dispose()


def test_aggregato_forzato_senza_piano_vince_e_il_residuo_sta_al_secchio(monkeypatch):
    """Nessun piano, nessuna indicizzazione: il totale forzato E' il numero
    voluto, e il centesimo di ripiego finisce sul secchio `sp16g` — mai su
    `sp16c` (il difetto del genitore, che questa riga uccide: mutazione M1).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, sid, _rows = _esito_aggregato(db, "i1-senza-piano", "x")
            assert res["forecast_generated"] is True, res["message"]
            for anno, bs, ce in read_forecast_maps(db, sid):
                assert bs["sp16_debiti_breve"] == D("150000.00"), anno
                assert bs["sp16c_debiti_obbligazioni_breve"] == D("0"), (
                    anno, "il residuo e' tornato a posarsi su un confine PFN: "
                    "e' la mutazione M1, il difetto del genitore")
                assert sum((bs[c] for c in ForecastEngine._SP16_RIGHE), D("0")) == \
                    bs["sp16_debiti_breve"], anno
    finally:
        engine.dispose()


def test_aggregato_forzato_senza_piano_il_residuo_NOMINA_il_secchio(monkeypatch):
    """Rilievo m-E, punto 3: il test sopra asserisce il persistito, mai la
    DICHIARAZIONE. Qui `details['residuo_quadratura']` deve nominare
    `sp16g_altri_debiti_breve` — la massa che si e' spostata dall'aggregato
    al secchio deve potersi leggere, non solo quadrare.

    Misura (questa coda, 2027): +15.000,00 sul secchio — l'intera differenza
    fra il forzato 150.000,00 e il 135.000,00 delle righe.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, sid, rows = _esito_aggregato(db, "i1-nomina", "x")
            assert res["forecast_generated"] is True, res["message"]
            cid = db.query(BudgetScenario).filter(
                BudgetScenario.id == sid).one().company_id
            prev = budget_scenarios.preview_forecast_route(
                cid, sid, request={"assumptions": rows}, user_id="i1-nomina", db=db)
            nominato = {a["year"]: [p for p in (a["details"].get("residuo_quadratura") or [])
                                   if p["campo"] == "sp16g_altri_debiti_breve"]
                        for a in prev["forecast_years"]}
            assert nominato[2027], (nominato, "nessuna posatura nomina il secchio")
            assert D(str(nominato[2027][0]["importo"])) == D("15000.00"), nominato[2027]
    finally:
        engine.dispose()


def test_aggregato_forzato_con_indice_sp16g_e_via_manuale_si_rifiuta(monkeypatch):
    """Rilievo m-E, punto 4: I-1 sul PERCORSO DI SERVIZIO, non solo in
    batteria. L'indice su `sp16g` congela per gruppo tutto il breve
    (`_SP_OPERATIVI`), la via manuale toglie anche l'ultima scusa (che
    `sp16e` segua il calendario): con nessuna riga libera il totale forzato
    non e' un centesimo di quadratura bensi' la MASSA dell'override, e la
    risposta e' il rifiuto — `forecast_generated is False`, come lo fu per
    il piano di `test_piano_altri_aggregato_forzato_si_rifiuta_e_non_lascia_nulla`.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, sid, _rows = _esito_aggregato(
                db, "i1-ind-man", "x", indice={"sp16g": "ricavi"}, manuale=True)
            assert res["forecast_generated"] is False, res["message"]
            assert "Il totale forzato" in res["message"], res["message"]
            assert "sp16_debiti_breve" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == [], "un rifiuto non lascia nulla"
    finally:
        engine.dispose()


# ─────────────── I-2: `_sp_forced_fields`, la prova pura ───────────────

def test_sp_forced_fields_e_per_gruppo_non_per_unione():
    """Mutazione M5: `and`/`or` sbagliati nella condizione del secchio.

    Un'indicizzazione della SOLA `sp17g` forza `sp17d`…`sp17g` e NON tocca le
    quattro righe di `sp16`: con la condizione globale le otto righe entravano
    tutte, e il gruppo `sp16` restava senza ripiego (il centesimo finiva
    sull'aggregato e da li' sulla cassa).
    """
    # Le CHIAVI sono i codici di `SP_INDEXABLE_FIELDS`, non i nomi di colonna:
    # `_indexed_sp_forced_fields` mappa `code -> campo`, e una chiave scritta
    # col nome lungo non indicizza nulla (il test sarebbe verde per vuoto).
    da_indice = ForecastEngine._sp_forced_fields(
        None, {"indicizzazione": {"sp17g": {"voce": "ricavi"}}})
    assert "sp17g_altri_debiti_lungo" in da_indice, "la chiave non era quella giusta"
    assert {"sp17d_debiti_fornitori_lungo", "sp17e_debiti_tributari_lungo",
            "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo"} <= da_indice
    assert not ({"sp16d_debiti_fornitori_breve", "sp16e_debiti_tributari_breve",
                 "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve"} & da_indice), \
        sorted({"sp16d_debiti_fornitori_breve", "sp16e_debiti_tributari_breve",
                "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve"} & da_indice)


def test_sp_forced_fields_nessun_piano_nessuna_indicizzazione_non_gela_nulla():
    """Mutazione M1: `_declared_sp_fields()` rimesso dentro SEMPRE. Su questo
    cammino non deve comparire nessuna delle otto righe operative — e' la
    forma pura della frase «con il secchio libero il ripiego non parte mai».
    """
    base = ForecastEngine._sp_forced_fields(None, {})
    assert not (set(ForecastEngine._declared_sp_fields()) & base), sorted(
        set(ForecastEngine._declared_sp_fields()) & base)
    assert set(ForecastEngine._BANK_DEBT_SPLIT_FIELDS) <= base


def test_piano_altri_debiti_governa_entrambi_i_gruppi_interi():
    """`altri_debiti` e' l'unico saldo che tocca BOTH `sp16g` e `sp17g`: li' le
    otto righe sono tutte governate, e infatti l'aggregato forzato si rifiuta."""
    forzati = ForecastEngine._sp_forced_fields(
        {"altri_debiti": {"opening": 95000.00, "amounts": [47500.00, 47500.00]}}, {})
    assert set(ForecastEngine._declared_sp_fields()) <= forzati


def test_l_aggregato_entra_in_forced_fields_solo_se_forzato_lui_e_nessunaVoce():
    """La meta' di I-2 che viene da I-1: `forced_fields` deve dire al
    normalizzatore QUALI celle sono input dell'utente, e la regola non e'
    simmetrica — una voce forzata significa che l'aggregato lo ricostruisce
    `_apply_sp_overrides`, quindi il residuo torna un arrotondamento."""
    class _A:
        def __init__(self, ov):
            self.sp_overrides = ov

    assert "sp16_debiti_breve" in ForecastEngine._sp_forced_fields(
        None, {}, _A({"sp16_debiti_breve": "150000.00"}))
    assert "sp16_debiti_breve" not in ForecastEngine._sp_forced_fields(
        None, {}, _A({"sp16_debiti_breve": "150000.00",
                      "sp16d_debiti_fornitori_breve": "80000.00"}))
    assert "sp17_debiti_lungo" in ForecastEngine._sp_forced_fields(
        None, {}, _A({"sp17_debiti_lungo": "90000.00"}))
    assert not any(c in ForecastEngine._sp_forced_fields(None, {}, _A(None))
                   for c in ("sp16_debiti_breve", "sp17_debiti_lungo"))
