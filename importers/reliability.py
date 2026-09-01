"""Per-account reliability verdicts for an imported balance sheet.

An import can BALANCE AND BE FALSE. The reference case is 613_2024: 2,25M of
fondi ammortamento stay booked as debts, the assets stay gross (4,98M instead
of 3,13M), every gate passes and the file is saved as `verified`.

This module turns evidence the pipeline already computes into a verdict on the
three accounts that decide every KPI. It is a PURE function: dicts in, verdict
out, no I/O.

Design rule: UNRELIABLE requires POSITIVE evidence of contradiction, never the
mere absence of a control. A route A/B file runs no contra scan at all; an
abbreviated statement prints no patrimonio-netto subtotal. Treating those as
unreliable would block most of the corpus.
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

Z = Decimal('0')


class AccountStatus(Enum):
    VERIFIED = 'verified'      # corroborated by independent source evidence
    DERIVED = 'derived'        # inferred but internally consistent
    UNRELIABLE = 'unreliable'  # evidence says the figure is probably wrong


_BANK_FIELDS = ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo')
_NON_BANK_SHORT = (
    'sp16b_debiti_altri_finanz_breve', 'sp16c_debiti_obbligazioni_breve',
    'sp16d_debiti_fornitori_breve', 'sp16e_debiti_tributari_breve',
    'sp16f_debiti_previdenza_breve', 'sp16g_altri_debiti_breve',
)
_NON_BANK_LONG = (
    'sp17b_debiti_altri_finanz_lungo', 'sp17c_debiti_obbligazioni_lungo',
    'sp17d_debiti_fornitori_lungo', 'sp17e_debiti_tributari_lungo',
    'sp17f_debiti_previdenza_lungo', 'sp17g_altri_debiti_lungo',
)


def _d(bs: dict, key: str) -> Decimal:
    value = bs.get(key)
    if value is None:
        return Z
    return value if isinstance(value, Decimal) else Decimal(str(value))


def materiality_threshold(total: Decimal) -> Decimal:
    """M = max(1.000 EUR; 0,1% del totale attivo).

    Canonical definition for the whole import pipeline. This module is pure and
    dependency-free, so every other module imports it from here rather than
    re-deriving it (Task 3 defined a temporary copy in
    situazione_contabile_parser; Step 5 below replaces it with a re-export).
    """
    return max(Decimal('1000'), abs(total or Z) * Decimal('0.001'))


_threshold = materiality_threshold   # internal alias


@dataclass(frozen=True)
class ReliabilityReport:
    immobilizzazioni: AccountStatus
    immobilizzazioni_reason: str
    patrimonio_netto: AccountStatus
    patrimonio_netto_reason: str
    debiti_banche: AccountStatus
    debiti_banche_reason: str
    unclassified_mass: Decimal = Z
    # Il verdetto sulla massa non classificata e' separato dall'importo perche'
    # zero da solo non dice nulla: puo' essere «misurato contro il totale
    # stampato, non manca massa» oppure «nessun totale da confrontare».
    massa_non_classificata: AccountStatus = AccountStatus.DERIVED
    massa_non_classificata_reason: str = (
        'nessuna misura della massa non classificata dichiarata')

    @property
    def all_critical_ok(self) -> bool:
        # Deliberatamente i TRE conti storici, non quattro. Questo flag e' letto
        # dal backend per conservare l'esito d'importazione
        # (backend/app/api/v1/financial_years.py): allargarlo alla massa non
        # classificata cambierebbe il gating su file reali senza che la
        # decisione sia stata presa da nessuno. La distinzione si legge dal
        # proprio campo, che e' il punto di questo verdetto.
        return AccountStatus.UNRELIABLE not in (
            self.immobilizzazioni, self.patrimonio_netto, self.debiti_banche)

    def to_dict(self) -> dict:
        return {
            'immobilizzazioni': {'status': self.immobilizzazioni.value,
                                 'reason': self.immobilizzazioni_reason},
            'patrimonio_netto': {'status': self.patrimonio_netto.value,
                                 'reason': self.patrimonio_netto_reason},
            'debiti_banche': {'status': self.debiti_banche.value,
                              'reason': self.debiti_banche_reason},
            # Chiave e formato storici: i lettori di oggi non si rompono.
            'unclassified_mass': str(self.unclassified_mass),
            'massa_non_classificata': {
                'status': self.massa_non_classificata.value,
                'reason': self.massa_non_classificata_reason},
            'all_critical_ok': self.all_critical_ok,
        }


def _assess_immobilizzazioni(bs: dict):
    if '_contra_detected' not in bs:
        return (AccountStatus.DERIVED,
                'nessuno scan contro-conti per questa rotta (schema di legge)')
    detected = _d(bs, '_contra_detected')
    applied = _d(bs, '_contra_applied')
    reason = bs.get('_contra_reason') or ''
    if detected <= Z:
        return (AccountStatus.DERIVED,
                'nessuna massa contro rilevata: il documento e gia netto')
    if applied > Z:
        return (AccountStatus.VERIFIED,
                f'contro-conti riconciliati e applicati ({applied:,.2f})')
    return (AccountStatus.UNRELIABLE,
            f'rilevati {detected:,.2f} di contro-conti NON applicati '
            f'({reason}): immobilizzazioni lorde e fondi fra i debiti')


def _assess_patrimonio_netto(bs: dict, declared: Optional[dict]):
    computed = (_d(bs, 'sp11_capitale') + _d(bs, 'sp12_riserve')
                + _d(bs, 'sp13_utile_perdita'))
    printed = (declared or {}).get('patrimonio_netto')
    if printed is None:
        return (AccountStatus.DERIVED,
                'nessun totale patrimonio netto stampato da confrontare')
    printed = printed if isinstance(printed, Decimal) else Decimal(str(printed))
    gap = abs(computed - printed)
    if gap <= _threshold(_d(bs, 'totale_attivo')):
        return (AccountStatus.VERIFIED,
                f'riconcilia col totale stampato ({printed:,.2f})')
    return (AccountStatus.UNRELIABLE,
            f'ricostruito {computed:,.2f} contro {printed:,.2f} stampato '
            f'(scarto {gap:,.2f})')


def _assess_debiti_banche(bs: dict):
    explicit = sum((_d(bs, f) for f in _BANK_FIELDS), Z)
    short_gap = _d(bs, 'sp16_debiti_breve') - (
        _d(bs, 'sp16a_debiti_banche_breve')
        + sum((_d(bs, f) for f in _NON_BANK_SHORT), Z))
    long_gap = _d(bs, 'sp17_debiti_lungo') - (
        _d(bs, 'sp17a_debiti_banche_lungo')
        + sum((_d(bs, f) for f in _NON_BANK_LONG), Z))
    gap = max(Z, short_gap) + max(Z, long_gap)
    if gap > _threshold(_d(bs, 'totale_attivo')):
        return (AccountStatus.UNRELIABLE,
                f'{gap:,.2f} di debiti non tipizzati: base_bank_debt li '
                f'attribuirebbe alle banche, gonfiando la PFN')
    if explicit > Z:
        return (AccountStatus.VERIFIED,
                f'letti da sotto-campi espliciti ({explicit:,.2f})')
    return (AccountStatus.DERIVED,
            'nessuna esposizione bancaria e nessuno scarto da attribuire')


def _assess_massa_non_classificata(bs: dict):
    """Due zeri che non sono lo stesso zero.

    `_unclassified_mass` a zero significa «pulito» solo se un totale di
    controllo esisteva davvero: senza, non c'era nulla contro cui misurare, e
    la risposta onesta e' «non lo so». La distinzione arriva da
    `_unclassified_mass_measured`, scritta da `declare_unclassified_mass`.

    Una chiave assente vale «non misurato», non «misurato e pulito»: a valle
    una chiave assente vale zero, quindi tacere non puo' valere come promessa.
    Il caso non e' teorico — il file di riferimento (AMB AMBIENTA) non stampa
    nessuna riga «Totale …»: i totali stanno nelle intestazioni di sezione.

    UNRELIABLE resta riservato alla contraddizione: massa stampata, misurata, e
    materialmente non arrivata in nessun campo. Un controllo assente da'
    DERIVED, mai un verdetto negativo — o un'intera famiglia di layout
    legittimi risulterebbe inaffidabile.
    """
    if _d(bs, '_unclassified_mass_measured') <= Z:
        return (AccountStatus.DERIVED,
                'nessun totale di sezione stampato: la massa non classificata '
                'non e misurabile su questo documento')
    mass = _d(bs, '_unclassified_mass')
    threshold = _threshold(_d(bs, 'totale_attivo'))
    if mass > threshold:
        return (AccountStatus.UNRELIABLE,
                f'{mass:,.2f} di massa stampata non e finita in nessun campo '
                f'IV-CEE (soglia {threshold:,.2f})')
    return (AccountStatus.VERIFIED,
            f'misurata contro il totale stampato: {mass:,.2f} non classificati')


def assess(bs: dict, ce: dict,
           declared: Optional[dict] = None) -> ReliabilityReport:
    """Verdict on the three accounts that decide every KPI.

    `bs` uses full DB field names and may carry the `_contra_*` metadata written
    by net_contra_accounts. `declared` may carry a 'patrimonio_netto' control
    total read from the document. `ce` is accepted for symmetry and future use.
    """
    immo_status, immo_reason = _assess_immobilizzazioni(bs)
    pn_status, pn_reason = _assess_patrimonio_netto(bs, declared)
    bank_status, bank_reason = _assess_debiti_banche(bs)
    mass_status, mass_reason = _assess_massa_non_classificata(bs)
    return ReliabilityReport(
        immobilizzazioni=immo_status, immobilizzazioni_reason=immo_reason,
        patrimonio_netto=pn_status, patrimonio_netto_reason=pn_reason,
        debiti_banche=bank_status, debiti_banche_reason=bank_reason,
        unclassified_mass=_d(bs, '_unclassified_mass'),
        massa_non_classificata=mass_status,
        massa_non_classificata_reason=mass_reason,
    )
