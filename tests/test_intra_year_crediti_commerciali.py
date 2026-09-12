"""_distribute_sp06/_distribute_sp07 ripartivano i crediti proiettati con le
proporzioni del bilancio di RIFERIMENTO -- lo stesso schema del debito
bancario (indagine-1, test_intra_year_debito_bancario.py), "Mirrors
_distribute_sp16" per commento del codice. Quando il riferimento non ha
dettaglio reale sui crediti (tutto il totale in 'g', il secchio di ripiego --
il caso comune per un bilancio da schema di legge) l'intera massa dei crediti
commerciali del parziale (verso clienti, sp06a/sp07a) veniva riclassificata
in 'altri crediti' senza alcuna diagnostica (indagine-2, 2026-09-12).

A differenza del debito bancario, i crediti commerciali SONO trainati dal
fatturato (rotazione/DSO): l'aggregato sp06/sp07 continua a scalare sulla
rotazione dei costi/ricavi del riferimento come prima -- cambia solo la fonte
delle PROPORZIONI con cui l'aggregato si ripartisce fra le sotto-voci, che
diventa il parziale (il dato reale, gia' classificato), mai il riferimento.

Un secondo difetto, indipendente da quale fonte si usi per le proporzioni: i
campi GOVERNATI altrove (sp06e dalla posizione tributaria, sp06f/sp07f dalle
differite quando impostate) potevano ricevere comunque una quota dalla
ripartizione proporzionale, quota poi scartata dal calcolo fiscale che li
sovrascrive -- la massa scartata spariva in cassa senza alcun flusso
(indagine-2: 40.000,00 su un caso sintetico, TEST C sotto). Ora quei campi
sono esclusi dalla ripartizione PRIMA che avvenga, cosi' la massa non si
perde mai.
"""
from decimal import Decimal as D

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)


def _sessione():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _stato_sp06(**over):
    """Stato patrimoniale minimo per i test di questo file: solo i campi di
    sp06/sp07 e il minimo per far quadrare Attivo=Passivo (sp09, sp11)."""
    zero = D("0")
    base = dict(
        sp06_crediti_breve=zero, sp06a_crediti_clienti_breve=zero, sp06b_crediti_controllate_breve=zero,
        sp06c_crediti_collegate_breve=zero, sp06d_crediti_controllanti_breve=zero,
        sp06e_crediti_tributari_breve=zero, sp06f_imposte_anticipate_breve=zero, sp06g_crediti_altri_breve=zero,
        sp07_crediti_lungo=zero, sp07a_crediti_clienti_lungo=zero, sp07b_crediti_controllate_lungo=zero,
        sp07c_crediti_collegate_lungo=zero, sp07d_crediti_controllanti_lungo=zero,
        sp07e_crediti_tributari_lungo=zero, sp07f_imposte_anticipate_lungo=zero, sp07g_crediti_altri_lungo=zero,
        sp09_disponibilita_liquide=D("500000"), sp11_capitale=D("100000"),
    )
    base.update(over)
    return base


def _proietta_crediti(stato_riferimento, ricavi_riferimento, stato_parziale, **ipotesi):
    """Costruisce un'azienda con uno stato patrimoniale DIVERSO per l'anno di
    riferimento (2025, pieno) e per il parziale (2026, 6 mesi): il ricavo del
    riferimento e la crescita a 0% (default) rendono l'aggregato sp06
    proiettato ESATTAMENTE uguale a ``ref_sp06`` (rapporto di rotazione non
    degenere, nessuno scalamento) -- cosi' un test su massa conservata non
    dipende dall'aritmetica della rotazione, solo dalla ripartizione."""
    db = _sessione()
    azienda = Company(name="Crediti infrannuale", tax_id="CREDITI-INFRA", sector=1)
    db.add(azienda); db.flush()
    fy_ref = FinancialYear(company_id=azienda.id, year=2025, period_months=None,
                           validation_status="verified", forecastable=True)
    db.add(fy_ref); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_ref.id, **stato_riferimento))
    # ce05 = ce01 pareggia l'utile del CE a zero, coerente con sp13=0 di _stato_sp06
    # (il motore rifiuta un anno di riferimento il cui utile CE non torna con sp13).
    db.add(IncomeStatement(financial_year_id=fy_ref.id, ce01_ricavi_vendite=ricavi_riferimento,
                           ce05_materie_prime=ricavi_riferimento))
    fy_par = FinancialYear(company_id=azienda.id, year=2026, period_months=6,
                           validation_status="verified", forecastable=True)
    db.add(fy_par); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_par.id, **stato_parziale))
    db.add(IncomeStatement(financial_year_id=fy_par.id))
    scenario = BudgetScenario(company_id=azienda.id, name="crediti-test", base_year=2025,
                              scenario_type="infrannuale", period_months=6)
    db.add(scenario); db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2026, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"), **ipotesi))
    db.commit()
    result = IntraYearEngine(db).generate_projection(scenario.id)
    bs = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return bs, result['diagnostics']


# Fixture comune ai tre test: lo stesso parziale (6 mesi), con crediti verso
# clienti reali (sp06a) e una piccola quota tributaria e "altri".
_RIF_TOTALE = D("200000")
_PARZIALE = _stato_sp06(
    sp06_crediti_breve=D("120000"), sp06a_crediti_clienti_breve=D("90000"),
    sp06e_crediti_tributari_breve=D("5000"), sp06g_crediti_altri_breve=D("25000"),
    sp11_capitale=D("620000"),
)


def test_i_crediti_verso_clienti_si_portano_avanti_dal_parziale_quando_il_riferimento_non_ha_dettaglio():
    """Il riferimento ha l'intero sp06 nel secchio di ripiego 'g' (nessuna
    voce reale, il caso comune -- il 98% dei bilanci annuali completi del
    database secondo indagine-1 §6): il credito verso clienti REALE del
    parziale (90.000,00 su 120.000,00) non deve sparire in 'altri crediti'.
    Prima della correzione: sp06a 0,00 (indagine-2)."""
    ref = _stato_sp06(sp06_crediti_breve=_RIF_TOTALE, sp06g_crediti_altri_breve=_RIF_TOTALE,
                       sp11_capitale=D("700000"))
    bs, diagnostics = _proietta_crediti(ref, D("1000000"), _PARZIALE)
    assert bs.sp06_crediti_breve == D("200000.00")  # aggregato: rotazione non degenere, invariata
    assert bs.sp06a_crediti_clienti_breve == D("156521.74")  # non piu' zero
    codici = [d['code'] for d in diagnostics]
    assert 'reference_receivables_undetailed' in codici
    diag = next(d for d in diagnostics if d['code'] == 'reference_receivables_undetailed')
    assert diag['aggregate'] == 'sp06'
    assert diag['severity'] == 'warning'


def test_la_composizione_segue_il_parziale_anche_quando_il_riferimento_ha_dettaglio():
    """Il riferimento ha una propria quota clienti (160.000,00 su 200.000,00,
    80%): prima della correzione quella proporzione (80%) veniva applicata
    all'aggregato proiettato, dando sp06a = 160.000,00. Dopo, la composizione
    usata e' sempre quella del parziale (mai quella del riferimento, quale
    che sia): stesso risultato di quando il riferimento non ha dettaglio
    affatto (156.521,74), e nessuna diagnostica -- il riferimento avrebbe
    dato un segnale reale, semplicemente non e' piu' quello che conta."""
    ref = _stato_sp06(sp06_crediti_breve=_RIF_TOTALE, sp06a_crediti_clienti_breve=D("160000"),
                       sp06g_crediti_altri_breve=D("40000"), sp11_capitale=D("700000"))
    bs, diagnostics = _proietta_crediti(ref, D("1000000"), _PARZIALE)
    assert bs.sp06a_crediti_clienti_breve == D("156521.74")
    assert not any(d['code'] == 'reference_receivables_undetailed' for d in diagnostics)


def test_il_credito_tributario_non_riceve_una_quota_dalla_ripartizione_poi_scartata():
    """Il riferimento ha una quota REALE di crediti tributari (sp06e =
    40.000,00 su 200.000,00): una ripartizione ingenua le assegnerebbe una
    quota proporzionale, che il calcolo fiscale automatico (manual_tax_position
    False, nessun sp06e_growth_pct/sp16e_growth_pct impostato) scarta subito
    dopo sostituendola col proprio valore -- la massa scartata spariva in
    cassa (indagine-2): prima della correzione sp06 finale 160.000,00 invece
    di 200.000,00 (mancano esattamente i 40.000,00 di sp06e), sp09
    460.000,00 invece di 420.000,00. Dopo: sp06e e' escluso dalla
    ripartizione PRIMA che avvenga, e l'aggregato torna a conservare la
    massa esattamente."""
    ref = _stato_sp06(sp06_crediti_breve=_RIF_TOTALE, sp06e_crediti_tributari_breve=D("40000"),
                       sp06g_crediti_altri_breve=D("160000"), sp11_capitale=D("700000"))
    bs, _diagnostics = _proietta_crediti(ref, D("1000000"), _PARZIALE)
    assert bs.sp06_crediti_breve == D("200000.00")  # nessuna massa persa
    assert bs.sp09_disponibilita_liquide == D("420000.00")
