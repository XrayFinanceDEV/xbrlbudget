"""Indicatori della crisi d'impresa: calcolo, punteggio e rating.

Un solo motore, e sta qui. Fino al 2026-09-21 viveva solo nel client
(`frontend/lib/pratica-indicators.ts`), e il report PDF dell'infrannuale, che
il server genera, non avrebbe potuto firmare numeri mai calcolati dal server.
Il porto e' fedele, commenti compresi dove spiegano un ramo: ogni guardia
«degenere» ha una ragione di dominio, e toglierla sposta la classe di rischio
di aziende reali.

Le chiavi dei campi sono i nomi delle colonne del DB (`sp09_disponibilita_liquide`,
`ce01_ricavi_vendite`), quindi gli ingressi sono le mappe che si leggono da un
`BalanceSheet`/`IncomeStatement`, da un `ForecastYear` o dal confronto
infrannuale. Valori assenti o `None` valgono zero.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, NamedTuple

ZERO = Decimal("0")
UNO = Decimal("1")
CENTO = Decimal("100")
NEUTRO = Decimal("0.5")
# Sotto questa soglia un indicatore e' «oltre»: la conta degli oltre, con i
# segnali extracontabili, decide la classe di rischio.
SOGLIA_OLTRE = Decimal("0.33")


class IndicatoriCrisi(NamedTuple):
    dscr: Decimal
    ebitda_margin: Decimal
    mt: Decimal
    ccn: Decimal
    current_ratio: Decimal
    ms: Decimal
    copertura_immob: Decimal
    indipendenza: Decimal
    pfn: Decimal
    pfn_ebitda: Decimal
    roi: Decimal
    roe: Decimal
    ros: Decimal
    # Due domande diverse, tenute entrambe: `of_mol` dice quanto pesano gli
    # oneri sulla capacita' di generare cassa ed e' quello del punteggio;
    # `of_revenue` dice quanto pesano sul giro d'affari.
    of_mol: Decimal
    of_revenue: Decimal
    materials_revenue: Decimal
    services_revenue: Decimal
    # Grezzi: servono al punteggio (distinguere «zero» da «il rapporto non
    # esiste») e ai grafici, che su un denominatore nullo non disegnano il punto.
    ebitda_raw: Decimal
    quick_ratio: Decimal
    equity_over_fixed: Decimal
    revenue_raw: Decimal
    total_assets_raw: Decimal
    equity_raw: Decimal
    oneri_finanziari_raw: Decimal


class Indicatore(NamedTuple):
    chiave: str
    etichetta: str
    formato: str  # "euro" | "pct" | "ratio"


INDICATORI: tuple[Indicatore, ...] = (
    Indicatore("dscr", "DSCR", "ratio"),
    Indicatore("ebitda_margin", "EBITDA %", "pct"),
    Indicatore("mt", "Margine di Tesoreria", "euro"),
    Indicatore("ccn", "CCN", "euro"),
    Indicatore("current_ratio", "Liquidità Corrente", "ratio"),
    Indicatore("ms", "Margine di Struttura", "euro"),
    Indicatore("copertura_immob", "Copertura Immobilizzazioni", "pct"),
    Indicatore("indipendenza", "Indipendenza Finanziaria", "pct"),
    Indicatore("pfn", "PFN", "euro"),
    Indicatore("pfn_ebitda", "PFN / EBITDA", "ratio"),
    Indicatore("roi", "ROI", "pct"),
    Indicatore("roe", "ROE", "pct"),
    Indicatore("ros", "ROS", "pct"),
    Indicatore("of_mol", "Oneri Finanziari / MOL", "pct"),
    Indicatore("of_revenue", "Oneri Finanziari / Fatturato", "pct"),
)

# Gli indicatori che alimentano il PUNTEGGIO di crisi, che non sono tutti
# quelli che la tabella rende. `of_revenue` e' fuori di proposito: le bande di
# `rating_crisi` sono tarate sul NUMERO di indicatori che le alimentano, e
# sugli oneri finanziari il punteggio usa gia' `of_mol` — contarli due volte
# peserebbe lo stesso fatto su un altro denominatore. Il pallino di riga resta
# invece calcolato per ogni indicatore.
CHIAVI_PUNTEGGIO: tuple[str, ...] = tuple(i.chiave for i in INDICATORI if i.chiave != "of_revenue")

# I grezzi escono con il prefisso `_` che il client usa da sempre.
_GREZZI = ("ebitda_raw", "quick_ratio", "equity_over_fixed", "revenue_raw",
           "total_assets_raw", "equity_raw", "oneri_finanziari_raw")


def _dec(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _div(numeratore: Decimal, denominatore: Decimal) -> Decimal:
    """Zero su denominatore nullo, come `safeDivide` del client: i rami
    degeneri del punteggio guardano il grezzo, non questo zero."""
    return numeratore / denominatore if denominatore != 0 else ZERO


def calcola_indicatori(bs: Mapping[str, Any], ce: Mapping[str, Any]) -> IndicatoriCrisi:
    def v(obj: Mapping[str, Any], key: str) -> Decimal:
        return _dec(obj.get(key))

    revenue = v(ce, "ce01_ricavi_vendite")
    vp = (revenue + v(ce, "ce02_variazioni_rimanenze") + v(ce, "ce03_lavori_interni")
          + v(ce, "ce03a_incrementi_immobilizzazioni") + v(ce, "ce04_altri_ricavi"))
    op_costs = (v(ce, "ce05_materie_prime") + v(ce, "ce06_servizi") + v(ce, "ce07_godimento_beni")
                + v(ce, "ce08_costi_personale") + v(ce, "ce10_var_rimanenze_mat_prime")
                + v(ce, "ce11_accantonamenti") + v(ce, "ce11b_altri_accantonamenti")
                + v(ce, "ce12_oneri_diversi"))
    ebitda = vp - op_costs
    ebit = ebitda - v(ce, "ce09_ammortamenti")
    oneri = v(ce, "ce15_oneri_finanziari")
    imposte = v(ce, "ce20_imposte")
    proventi = (v(ce, "ce13_proventi_partecipazioni") + v(ce, "ce14_altri_proventi_finanziari")
                + v(ce, "ce16_utili_perdite_cambi"))
    straordinari = v(ce, "ce18_proventi_straordinari") - v(ce, "ce19_oneri_straordinari")
    net_profit = ebit - oneri + proventi + straordinari + v(ce, "ce17_rettifiche_attivita_fin") - imposte

    fixed = v(bs, "sp02_immob_immateriali") + v(bs, "sp03_immob_materiali") + v(bs, "sp04_immob_finanziarie")
    inventory = v(bs, "sp05_rimanenze")
    cash = v(bs, "sp09_disponibilita_liquide")
    financial_assets = v(bs, "sp08_attivita_finanziarie")
    current_assets = (inventory + v(bs, "sp06_crediti_breve") + financial_assets + cash
                      + v(bs, "sp10_ratei_risconti_attivi"))
    # `sp07_crediti_lungo` non e' circolante ma sta nel totale attivo: ometterlo
    # sottostima l'attivo e sovrastima indipendenza e ROI, nella direzione
    # sbagliata per un indicatore di rischio.
    total_assets = v(bs, "sp01_crediti_soci") + fixed + current_assets + v(bs, "sp07_crediti_lungo")
    equity = v(bs, "sp11_capitale") + v(bs, "sp12_riserve") + v(bs, "sp13_utile_perdita")
    current_liab = v(bs, "sp16_debiti_breve")
    long_debt = v(bs, "sp17_debiti_lungo")

    # PFN: banche + obbligazioni. Senza quel dettaglio, il totale dei debiti
    # meno i debiti non finanziari noti (fornitori, tributari, previdenza, altri
    # finanziatori); `sp16g`/`sp17g` restano dentro perche' sono il secchio che
    # assorbe il non classificato. Nessun dettaglio (abbreviato): il totale.
    bank = (v(bs, "sp16a_debiti_banche_breve") + v(bs, "sp17a_debiti_banche_lungo")
            + v(bs, "sp16c_debiti_obbligazioni_breve") + v(bs, "sp17c_debiti_obbligazioni_lungo"))
    known_non_bank = (v(bs, "sp16b_debiti_altri_finanz_breve") + v(bs, "sp17b_debiti_altri_finanz_lungo")
                      + v(bs, "sp16d_debiti_fornitori_breve") + v(bs, "sp17d_debiti_fornitori_lungo")
                      + v(bs, "sp16e_debiti_tributari_breve") + v(bs, "sp17e_debiti_tributari_lungo")
                      + v(bs, "sp16f_debiti_previdenza_breve") + v(bs, "sp17f_debiti_previdenza_lungo"))
    total_debt = current_liab + long_debt
    if bank > 0:
        financial_debt = bank
    elif known_non_bank > 0:
        financial_debt = total_debt - known_non_bank
    else:
        financial_debt = total_debt
    pfn = financial_debt - cash - financial_assets

    return IndicatoriCrisi(
        dscr=_div(ebitda - imposte, oneri),
        ebitda_margin=_div(ebitda, revenue) * CENTO,
        mt=current_assets - inventory - current_liab,
        ccn=current_assets - current_liab,
        current_ratio=_div(current_assets, current_liab),
        ms=equity - fixed,
        copertura_immob=_div(equity + long_debt, fixed) * CENTO,
        indipendenza=_div(equity, total_assets) * CENTO,
        pfn=pfn,
        pfn_ebitda=_div(pfn, ebitda),
        roi=_div(ebit, total_assets) * CENTO,
        roe=_div(net_profit, equity) * CENTO,
        ros=_div(ebit, revenue) * CENTO,
        of_mol=_div(oneri, ebitda) * CENTO,
        of_revenue=_div(oneri, revenue) * CENTO,
        materials_revenue=_div(v(ce, "ce05_materie_prime"), revenue) * CENTO,
        services_revenue=_div(v(ce, "ce06_servizi"), revenue) * CENTO,
        ebitda_raw=ebitda,
        quick_ratio=_div(current_assets - inventory, current_liab),
        equity_over_fixed=_div(equity, fixed) * CENTO,
        revenue_raw=revenue,
        total_assets_raw=total_assets,
        equity_raw=equity,
        oneri_finanziari_raw=oneri,
    )


def _lineare(valore: Decimal, basso: Decimal | int, alto: Decimal | int) -> Decimal:
    """0 a `basso`, 1 a `alto`, interpolato e limitato a [0, 1]."""
    basso, alto = Decimal(basso), Decimal(alto)
    if valore <= basso:
        return ZERO
    if valore >= alto:
        return UNO
    return (valore - basso) / (alto - basso)


def _invertito(valore: Decimal, buono_sotto: Decimal | int, cattivo_sopra: Decimal | int) -> Decimal:
    return UNO - _lineare(valore, buono_sotto, cattivo_sopra)


def punteggio(chiave: str, ind: IndicatoriCrisi) -> Decimal:
    """Punteggio 0-1 di un indicatore, sulle soglie della pratica bancaria
    italiana e del CNDCEC.

    I rami degeneri valgono 0,5, «non lo so»: un denominatore assente non e'
    una contraddizione misurata, e un verdetto negativo ne vuole una. Non e'
    nemmeno un'eccellenza da premiare.
    """
    if chiave == "dscr":
        # Senza oneri finanziari il rapporto non esiste: su una scala diretta lo
        # zero di `_div` sarebbe il verdetto peggiore proprio per l'azienda
        # senza debito oneroso (#29).
        if ind.oneri_finanziari_raw <= 0:
            return NEUTRO
        return _lineare(ind.dscr, 1, Decimal("1.5"))
    if chiave == "ebitda_margin":
        return _lineare(ind.ebitda_margin, 5, 20)
    if chiave == "mt":
        return _lineare(ind.quick_ratio, Decimal("0.8"), Decimal("1.3"))
    if chiave in ("ccn", "current_ratio"):
        return _lineare(ind.current_ratio, Decimal("0.8"), Decimal("1.5"))
    if chiave == "ms":
        return _lineare(ind.equity_over_fixed, 50, 120)
    if chiave == "copertura_immob":
        return _lineare(ind.copertura_immob, 80, 150)
    if chiave == "indipendenza":
        return _lineare(ind.indipendenza, 15, 50)
    if chiave in ("pfn", "pfn_ebitda"):
        if ind.ebitda_raw <= 0 and ind.pfn > 0:
            return ZERO
        return _invertito(ind.pfn_ebitda, 0, 6)
    if chiave == "roi":
        return _lineare(ind.roi, 0, 12)
    if chiave == "roe":
        # Patrimonio netto nullo o negativo: il rapporto non esiste, o cambia
        # segno per il denominatore e non per la redditivita'. Il dissesto non
        # sparisce dal conteggio: `indipendenza` e `ms` vanno a zero da soli.
        if ind.equity_raw <= 0:
            return NEUTRO
        return _lineare(ind.roe, 0, 12)
    if chiave == "ros":
        return _lineare(ind.ros, 0, 10)
    if chiave == "of_mol":
        if ind.ebitda_raw <= 0:
            return ZERO if ind.of_mol > 0 else NEUTRO
        return _invertito(ind.of_mol, 5, 30)
    if chiave == "of_revenue":
        # A ricavi zero `_div` da' 0, e su un punteggio INVERTITO lo zero vale
        # «ottimo»: senza questo ramo un'azienda senza ricavi sarebbe la piu'
        # sana del corpus.
        if ind.revenue_raw <= 0:
            return NEUTRO
        return _invertito(ind.of_revenue, 1, 5)
    return NEUTRO


def punteggi_crisi(ind: IndicatoriCrisi) -> list[Decimal]:
    """I punteggi da passare a `rating_crisi`, nell'ordine di `CHIAVI_PUNTEGGIO`."""
    return [punteggio(k, ind) for k in CHIAVI_PUNTEGGIO]


class RatingCrisi(NamedTuple):
    codice: str
    etichetta: str
    livello: str  # "verde" | "giallo" | "arancio" | "rosso"
    oltre: int
    segnali: int


def rating_crisi(punteggi: list[Decimal], segnali: int) -> RatingCrisi:
    """Classe di rischio da A3 (nessun rischio) a D (crisi), dal numero di
    indicatori oltre soglia e di segnali extracontabili attivi."""
    oltre = sum(1 for p in punteggi if p < SOGLIA_OLTRE)

    def r(codice: str, etichetta: str, livello: str) -> RatingCrisi:
        return RatingCrisi(codice, etichetta, livello, oltre, segnali)

    if oltre == 0 and segnali == 0:
        return r("A3", "Nessun rischio", "verde")
    if oltre <= 2 and segnali == 0:
        return r("A2", "Rischio minimo", "verde")
    if oltre == 3 and segnali == 0:
        return r("A1", "Rischio basso", "verde")
    if oltre <= 5 and segnali == 0:
        return r("B3", "Rischio moderato", "giallo")
    if segnali <= 1 and oltre <= 5:
        return r("B2", "Rischio significativo", "giallo")
    if segnali <= 2 and oltre <= 5:
        return r("B1", "Rischio elevato", "arancio")
    if segnali <= 3 and oltre <= 6:
        return r("C3", "Rischio alto", "arancio")
    if segnali <= 3 and oltre <= 7:
        return r("C2", "Rischio grave", "rosso")
    if segnali >= 3 and oltre > 5:
        return r("C1", "Pre-crisi", "rosso")
    return r("D", "Crisi", "rosso")


def indicatori_come_mappa(ind: IndicatoriCrisi) -> dict[str, Decimal]:
    """L'insieme con le chiavi del client (`IndicatorSet`, grezzi con `_`)."""
    return {(f"_{k}" if k in _GREZZI else k): v for k, v in ind._asdict().items()}
