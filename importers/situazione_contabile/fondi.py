"""Riconoscimento dei fondi (ammortamento, svalutazione) dalla descrizione del conto.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""



def _is_fondo_amm(desc_upper: str) -> bool:
    """Recognise depreciation/amortisation funds at any aggregation level, incl. the
    aggregate mastro 'FONDI AMMORTAMENTO IMMOBILIZ' the rule table below misses.

    Questa funzione governa l'INTERO netting dei fondi, quindi il pareggio di
    tutta la route C: un fondo non riconosciuto non viene sottratto dal cespite,
    l'attivo resta lordo e il passivo gonfio della stessa massa, i due lati non
    tornano e la differenza diventa residuo non classificato -> oltre l'1%
    scatta QUADRATURA MASCHERATA e l'import viene rifiutato.

    Il test a sottostringhe qui sotto e' tenuto INVARIATO (non puo' regredire
    nulla) e viene solo AFFIANCATO dalla forma canonica del normalizzatore unico,
    che collassa `F.di ammor.to`, `Fdo amm`, `Fondo amm.` su `fondo ammortamento`
    — grafie reali che il solo test a sottostringhe non vede. L'allargamento e'
    additivo per costruzione: si riconoscono piu' fondi, mai meno.
    """
    d = desc_upper
    if (('AMMORT' in d or 'AMM.TO' in d or 'AMM.NTO' in d or 'F.DO AMM' in d or 'F/AMM' in d)
            and ('FOND' in d or 'F.DO' in d or 'F/' in d)):
        return True
    try:
        from importers.label_semantics import normalize_label
    except Exception:
        return False
    # `fondo ammortamento` CONTIGUO: "Ammortamento immobilizzazioni immateriali" e
    # "Quota ammortamento esercizio" sono COSTI del conto economico, non fondi
    # dello stato patrimoniale, e non devono mai essere nettati.
    return "fondo ammortamento" in normalize_label(d)

# Category qualifiers that make a fondo a SPECIFIC line rather than the grand-total
# aggregate. '. IMM' / 'IMMAT' mark the immateriali SUB-aggregate (also specific).
# NB: no 'MOBIL' — it is a substring of 'IMMOBILIZ' and would exclude the grand
# total itself; 'ARRED' covers "mobili e arredi".
_FONDO_CATEGORY_KW = (
    'FABBRICAT', 'IMPIANT', 'ATTREZZ', 'ARRED', 'AUTO', 'MACCHIN',
    'TERREN', 'MATER', 'SW', 'SOFTWARE', 'BREVETT', 'LICENZ', 'MARCHI',
    'MANUT', 'PLURIENN', 'COSTI', 'SPESE', 'AVVIAMENTO', 'TELEFON', 'BENI',
    '. IMM', 'IMMAT',
)

def _is_fondo_aggregate(desc_upper: str) -> bool:
    """True only for the top-level 'FONDI AMMORTAMENTO IMMOBILIZ(ZAZIONI)' grand
    total — generic immobilizzazioni, no category qualifier. Used to trust the
    printed aggregate over incompletely/mis-coded sub-lines on vision-OCR sheets;
    keyed on description so it never matches a specific leaf/sub-aggregate."""
    d = desc_upper
    return (_is_fondo_amm(d) and 'IMMOBILIZ' in d
            and not any(k in d for k in _FONDO_CATEGORY_KW))

# Specific immateriali sub-categories: their fondo is a LEAF, not the immateriali
# sub-aggregate 'FONDI AMMORT. IMMOBILIZZAZ. IMM(ATERIALI)'.
_FONDO_IMMAT_LEAF_KW = (
    'ALTRE', 'LICENZ', 'BREVETT', 'SW', 'SOFTWARE', 'MARCHI', 'COSTI', 'SPESE',
    'MANUT', 'PLURIENN', 'AVVIAMENTO', 'CONCESS',
)

def _is_fondo_immat_aggregate(desc_upper: str) -> bool:
    """True only for the generic immateriali SUB-aggregate 'FONDI AMMORT.
    IMMOBILIZZAZ. IMM' — the immateriali category header, not a specific
    immateriali leaf (ALTRE IMMOBILIZZ. IMMAT., licenze, software, ...)."""
    d = desc_upper
    return (_is_fondo_amm(d) and 'IMMOBILIZ' in d
            and ('IMMAT' in d or '. IMM' in d or d.rstrip().endswith(' IMM'))
            and not any(k in d for k in _FONDO_IMMAT_LEAF_KW))

# Asset-type markers of an INTANGIBLE (B.I) depreciation fund. The row is already
# known to be a fondo ammortamento, so these key on the ASSET category only and
# are prefix-agnostic (they fire on both 'F.DO AMM.TO ...' and 'FONDO AMM.TO ...',
# which the F.DO-gated _classify_sp_passivo rules missed → immateriali fondi such
# as LICENZE/CONSULENZE/COSTI RICERCA leaked into the materiali bucket, over-
# netting materiali and under-netting immateriali — budget_210).
_FONDO_IMMAT_KW = (
    'IMMAT', '. IMM', 'PLURIENN', 'SOFTWARE', 'BREVETT', 'MARCHI', 'MARCHIO',
    'AVVIAMENT', 'LICENZ', 'CONCESSION', 'RICERCA', 'SVILUPPO', 'PUBBLICIT',
    'WEB', 'PROGETTAZ', 'CONSULENZ', 'DIRITTI', 'INGEGNO', 'KNOW', 'MANUT',
    'AMPLIAMENT', "COSTI D'IMPIANTO", 'COSTI DI IMPIANTO',
    'AMPL.', 'COSTI IMP', 'COSTITUZ',  # "Fondi ammort.costi imp.e ampl.", "spese di costituzione"
    'DISAGG',                       # disaggi su prestiti (budget_435)
)

def _fondo_is_immat(desc_upper: str) -> bool:
    """immateriali (True) vs materiali (False) split for a row already known to be
    a fondo (ammortamento or svalutazione immobilizzazioni). Any intangible
    asset-type marker → immateriali; the tangible captions (impianti/macchinari/
    attrezzature/auto/fabbricati/mobili…) carry none, so they fall to materiali by
    default — mirroring the historical 'F.DO AMM' fallback while no longer
    depending on the 'F.DO' spelling."""
    return any(k in desc_upper for k in _FONDO_IMMAT_KW)

# Asset-type markers of a TANGIBLE (B.II) fixed asset — used only to recognise a
# fondo svalutazione as a contra to immobilizzazioni MATERIALI (the immat side is
# recognised by _fondo_is_immat / 'IMMOBILIZ').
_FONDO_MAT_KW = (
    'FABBRICAT', 'IMPIANT', 'ATTREZZ', 'MACCHIN', 'AUTO', 'ARRED', 'TERREN',
    'AUTOMEZZ', 'AUTOVEIC',
)
# A fondo svalutazione of these items reduces OTHER balance-sheet lines, NOT the
# B.I/B.II immobilizzazioni, so it stays OUT of the immobilizzazioni contra-netting
# (crediti → sp06, rimanenze/magazzino → sp05, titoli/partecipazioni → immob.
# finanziarie sp04).
_SVALUT_NON_IMMOB_KW = ('CREDIT', 'RIMANENZ', 'MAGAZZIN', 'TITOL', 'PARTECIP')

def _is_fondo_svalut_immob(desc_upper: str) -> bool:
    """A write-down fund (fondo svalutazione) of an INTANGIBLE or TANGIBLE fixed
    asset. It is a contra-asset that reduces the B.I/B.II net book value exactly
    like the depreciation fund, so the overlay nets it TOGETHER with the fondo
    ammortamento (spec: user rule 2026-07-14, budget_210/211 'FONDO SVALUTAZIONE
    MARCHI'). Svalutazione of crediti/rimanenze/titoli/partecipazioni is excluded
    (it reduces other items). Requires a positive immobilizzazione reference so a
    bare/other 'fondo svalutazione' is never mis-netted onto immobilizzazioni."""
    d = desc_upper
    if 'SVALUT' not in d:
        return False
    if not ('FOND' in d or 'F.DO' in d or 'F/' in d):
        return False
    if any(k in d for k in _SVALUT_NON_IMMOB_KW):
        return False
    return (_fondo_is_immat(d) or 'IMMOBILIZ' in d
            or any(k in d for k in _FONDO_MAT_KW))
