"""Le regole del proprietario sulla natura dei conti, come istruzioni al modello (Fase 5, Task 7).

Decisione del proprietario (2026-11-11): niente correzioni a parole chiave; la voce di un conto la sceglie il modello,
dentro le classi ammesse, e le regole che sono un giudizio sulla natura entrano nelle sue istruzioni. Restano
deterministici, e quindi NON stanno qui: il lato (lo decide la colonna), il segno e i saldi a lato invertito (D2, D12,
D15, R3-CARTE, R3-RATEI, R3-NCR, P2/P3), la scadenza (`classifica.scadenza_dei_debiti`, `scadenza_dei_crediti`,
`imposte_anticipate_oltre`), la parentela dei conti (il totale stampato).

Fonte: i file `ISTRUZIONI-*.md` del campione (fuori git), regole D1-D17, P2-P7, W4, R3-*. Una riga per regola, generale,
senza nomi di clienti. Prompt e documentazione leggono la stessa fonte.

Interruttore `IMPORT_REGOLE_NEL_PROMPT` (spento per default: il prompt resta quello di prima, parola per parola).
"""
from __future__ import annotations

import os

_SPENTO = ("0", "false", "no", "off")


def accese() -> bool:
    """`IMPORT_REGOLE_NEL_PROMPT`: acceso con un valore qualunque fuori da 0/false/no/off; assente = spento."""
    return os.environ.get("IMPORT_REGOLE_NEL_PROMPT", "0").strip().lower() not in _SPENTO + ("",)


# D6: nessun campo straordinario. Le voci stampate come straordinarie vanno nella voce di natura (regola sotto).
MACRO_ESCLUSE = ("ce18", "ce19")

# La frase del prompt di prima va precisata per P6: un fornitore qualunque con saldo dare fra le attivita' resta un
# saldo a lato invertito (crediti verso altri, come nelle verita': 1531), ma un anticipo, un acconto o una caparra a
# fornitori dichiarati sono acconti (rimanenze o immobilizzazioni, 1566). Toglierla del tutto mandava il fornitore a
# saldo dare fra i ratei e risconti (misura fase5-ee2a506).
FRASE_CONTRARIA_A_P6 = "un fornitore, un debito o un rateo passivo con saldo dare fra le attivita'"
FRASE_SENZA_FORNITORE = ("un fornitore che non e' un anticipo o una caparra, un debito o un rateo passivo con saldo "
                         "dare fra le attivita'")

# Passo 1: la macro-voce. (sigla, istruzione)
REGOLE_MACRO: tuple[tuple[str, str], ...] = (
    ("P6", "Un conto che si dichiara anticipo, acconto o caparra versati ai fornitori e' un acconto: nelle "
           "rimanenze (sp05), oppure fra le immobilizzazioni materiali (sp03) se l'acquisto e' un cespite; senza "
           "indicazione, nelle rimanenze. Un fornitore qualunque con saldo dare resta un credito (sp06)."),
    ("FSC", "Un fondo svalutazione crediti o un fondo rischi su crediti (anche «tassato») stampato fra le passivita' "
            "rettifica i crediti verso clienti (sp06.F): non e' un fondo rischi. Un fondo ammortamento rettifica il "
            "suo cespite (sp02.F o sp03.F), mai i crediti."),
    ("P5", "I depositi cauzionali versati sono immobilizzazioni finanziarie (sp04), anche se il nome dice una "
           "scadenza."),
    ("P7", "Costi di ricerca, sviluppo e pubblicita' capitalizzati sono immobilizzazioni immateriali (sp02)."),
    ("D11", "I prelevamenti dei soci o del titolare stampati fra le attivita' sono crediti (sp06), non riducono il "
            "patrimonio netto."),
    ("D13", "Conti correnti, finanziamenti e crediti verso controllanti, controllate o collegate stampati fra le "
            "attivita' sono crediti (sp06)."),
    ("D16", "I crediti verso il factor per cessioni pro-solvendo sono crediti (sp06)."),
    ("D4", "Ricavi per natura, non per mastro: ricavi delle vendite (ce01) l'attivita' tipica dell'impresa, anche "
           "se il gestionale la stampa fra gli altri ricavi; altri ricavi (ce04) il resto: locazioni non "
           "caratteristiche, plusvalenze, sopravvenienze attive, rimborsi, contributi e incentivi."),
    ("R3-RIVALSE", "Rivalse di spese addebitate ai clienti (trasporto, installazione, incasso), penalita' su vendite "
                   "e contributo CONAI riaddebitato sono altri ricavi (ce04), anche se stampati fra le vendite; "
                   "i riaddebiti che fanno parte della fornitura (impianti di stampa, fustelle, scaffalature, "
                   "componente energia) restano ricavi delle vendite (ce01); un indennizzo pagato ai clienti, "
                   "stampato negativo fra le vendite, resta nei ricavi delle vendite."),
    ("D5", "I resi su vendite riducono i ricavi delle vendite (ce01)."),
    ("R3-FTV", "Fotovoltaico: incentivi e contributi sono altri ricavi (ce04); l'energia venduta al GSE e' ricavo "
               "delle vendite (ce01) quando l'impresa produce energia come attivita', altri ricavi (ce04) quando "
               "e' un'impresa d'altro tipo con un impianto per i propri consumi."),
    ("R3-ASSOC", "I ricavi da associazione in partecipazione sono altri ricavi (ce04)."),
    ("W4", "La variazione dei lavori in corso su ordinazione e' ce03; i lavori interni capitalizzati (incrementi di "
           "immobilizzazioni) sono ce03a."),
    ("D3", "Lavoro somministrato, interinale o staff leasing e' costo del personale (ce08), non servizi."),
    ("D8", "Costi per natura, anche contro il mastro del gestionale: carburanti, cancelleria, materiale di consumo "
           "e di pulizia, DPI, imballaggi, dazi e oneri accessori d'acquisto sono materie (ce05); bolli, tasse di "
           "possesso e di concessione, imposte indirette, quote associative, multe e sanzioni sono oneri diversi "
           "(ce12); formazione, visite mediche, mensa e buoni pasto da terzi sono servizi (ce06); canoni di leasing "
           "e noleggi sono godimento beni di terzi (ce07)."),
    ("D9", "Spese e commissioni bancarie e costi del factoring sono oneri finanziari (ce15), ma servizi (ce06) se "
           "il documento li stampa sotto un mastro di servizi."),
    ("D10", "Contributi, premi e merchandising pagati ai clienti sono servizi (ce06): non riducono i ricavi."),
    ("R3-ACCANT", "Trattamento di fine mandato degli amministratori e indennita' suppletiva di clientela stampati "
                  "fra i servizi sono altri accantonamenti (ce11b); stampati fra il personale restano personale "
                  "(ce08); il TFR dei dipendenti resta personale; contributi Enasarco e FIRR per gli agenti restano "
                  "servizi (ce06)."),
    ("D6", "Nessuna voce straordinaria: sopravvenienze e plusvalenze attive sono altri ricavi (ce04); "
           "sopravvenienze, minusvalenze e oneri straordinari sono oneri diversi (ce12) salvo natura piu' precisa; "
           "le imposte di esercizi precedenti sono imposte (ce20)."),
)

# Passo 2: la sotto-voce, dentro la macro gia' assegnata.
REGOLE_DETTAGLIO: tuple[tuple[str, str], ...] = (
    ("R3-FINSOCI", "I debiti verso soci senza altra indicazione sono finanziamenti dei soci (altri finanziatori); un "
                   "conto che mescola soci e collaboratori resta fra gli altri debiti."),
    ("D16", "I crediti verso il factor per cessioni pro-solvendo sono crediti verso clienti."),
    ("R3-CONTROPARTE", "Crediti diversi che non stampano la controparte restano altri crediti, anche se potrebbero "
                       "essere verso il gruppo."),
    ("P7", "Costi di ricerca, sviluppo e pubblicita' capitalizzati sono costi di sviluppo."),
    ("D3", "Il lavoro somministrato o interinale va negli altri costi del personale."),
)


def _elenco(regole: tuple[tuple[str, str], ...]) -> str:
    return " ".join(f"({sigla}) {testo}" for sigla, testo in regole)


def prompt_macro(base: str) -> str:
    """Il prompt del passo 1 con le regole: senza la frase contraria a P6, con le regole in coda prima della forma
    della risposta."""
    testo = base.replace(FRASE_CONTRARIA_A_P6, FRASE_SENZA_FORNITORE)
    coda = "Non scrivere mai importi."
    i = testo.rfind(coda)
    regole = "Regole del revisore, prevalgono su ogni altra indicazione: " + _elenco(REGOLE_MACRO) + " "
    return testo[:i] + regole + testo[i:] if i >= 0 else testo + " " + regole


def prompt_dettaglio(base: str) -> str:
    coda = "Non scrivere mai importi."
    i = base.rfind(coda)
    regole = "Regole del revisore: " + _elenco(REGOLE_DETTAGLIO) + " "
    return base[:i] + regole + base[i:] if i >= 0 else base + " " + regole
