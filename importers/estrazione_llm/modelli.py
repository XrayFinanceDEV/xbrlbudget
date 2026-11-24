"""Gli schemi pydantic dell'estrazione strutturata e PDFImportError.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import pydantic
import re
from decimal import Decimal
from typing import Optional


class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass

# ---------------------------------------------------------------------------
# Pydantic models for structured extraction
# ---------------------------------------------------------------------------

def _coerce_number(v):
    """Coerce an LLM-returned amount to float, tolerating Italian/mangled formats.

    Claude sometimes serialises a numeric field as a STRING using Italian
    thousands/decimal separators ("8.144.680,93") or a mangled hybrid where the
    decimal comma was already turned into a dot but the thousands dots were left
    in ("8.144.680.93"). Plain pydantic float-parsing rejects both, which made a
    whole BalanceSheetExtraction fail validation and the extractor return nothing
    (budget_405). Normalise here so one oddly-formatted field never sinks the
    whole extraction.

    Rules (no comma vs comma):
      - comma present  -> Italian: drop '.', then ',' -> '.'   ("1.234,56" -> 1234.56)
      - >1 dot, no comma -> last 2-digit group is the decimal, others thousands
                            ("8.144.680.93" -> 8144680.93; "1.234.567" -> 1234567)
      - <=1 dot         -> leave as-is (normal float / int)
    Trailing '-' and parentheses denote negatives.
    """
    if v is None or isinstance(v, (int, float, dict, list)):
        return v
    s = str(v).strip()
    if not s:
        return 0
    neg = s.endswith('-') or (s.startswith('(') and s.endswith(')'))
    s = s.strip('()').rstrip('-').strip().replace(' ', '').replace(' ', '')
    if not s:
        return 0
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif s.count('.') > 1:
        head, _, tail = s.rpartition('.')
        s = (head.replace('.', '') + '.' + tail) if len(tail) == 2 else s.replace('.', '')
    try:
        f = float(s)
    except ValueError:
        return 0
    return -f if neg else f

class _ItalianNumberModel(pydantic.BaseModel):
    """Base model whose float fields tolerate Italian/mangled numeric strings."""

    @pydantic.field_validator('*', mode='before')
    @classmethod
    def _coerce_italian_numbers(cls, v):
        return _coerce_number(v)

class BalanceSheetExtraction(_ItalianNumberModel):
    """IV CEE Stato Patrimoniale fields (single year)."""
    sp01_crediti_soci: float = pydantic.Field(0, description="A) Crediti verso soci per versamenti ancora dovuti")
    sp02_immob_immateriali: float = pydantic.Field(0, description="B.I) Immobilizzazioni immateriali")
    sp03_immob_materiali: float = pydantic.Field(0, description="B.II) Immobilizzazioni materiali")
    sp04_immob_finanziarie: float = pydantic.Field(0, description="B.III) Immobilizzazioni finanziarie")
    sp05_rimanenze: float = pydantic.Field(0, description="C.I) Rimanenze")
    sp06_crediti_breve: float = pydantic.Field(0, description="C.II) Crediti esigibili entro l'esercizio successivo")
    sp07_crediti_lungo: float = pydantic.Field(0, description="C.II) Crediti esigibili oltre l'esercizio successivo")
    # Debtor-type breakdown for C.II Crediti per OIC art. 2424 (entro/oltre per group).
    # Must sum to sp06_crediti_breve and sp07_crediti_lungo respectively.
    sp06a_crediti_clienti_breve: float = pydantic.Field(0, description="C.II.1) Crediti verso clienti — entro l'esercizio")
    sp07a_crediti_clienti_lungo: float = pydantic.Field(0, description="C.II.1) Crediti verso clienti — oltre l'esercizio")
    sp06b_crediti_controllate_breve: float = pydantic.Field(0, description="C.II.2) Crediti verso imprese controllate — entro l'esercizio")
    sp07b_crediti_controllate_lungo: float = pydantic.Field(0, description="C.II.2) Crediti verso imprese controllate — oltre l'esercizio")
    sp06c_crediti_collegate_breve: float = pydantic.Field(0, description="C.II.3) Crediti verso imprese collegate — entro l'esercizio")
    sp07c_crediti_collegate_lungo: float = pydantic.Field(0, description="C.II.3) Crediti verso imprese collegate — oltre l'esercizio")
    sp06d_crediti_controllanti_breve: float = pydantic.Field(0, description="C.II.4) Crediti verso controllanti — entro l'esercizio")
    sp07d_crediti_controllanti_lungo: float = pydantic.Field(0, description="C.II.4) Crediti verso controllanti — oltre l'esercizio")
    sp06e_crediti_tributari_breve: float = pydantic.Field(0, description="C.II.5-bis) Crediti tributari — entro l'esercizio")
    sp07e_crediti_tributari_lungo: float = pydantic.Field(0, description="C.II.5-bis) Crediti tributari — oltre l'esercizio")
    sp06f_imposte_anticipate_breve: float = pydantic.Field(0, description="C.II.5-ter) Imposte anticipate — entro l'esercizio")
    sp07f_imposte_anticipate_lungo: float = pydantic.Field(0, description="C.II.5-ter) Imposte anticipate — oltre l'esercizio")
    sp06g_crediti_altri_breve: float = pydantic.Field(0, description="C.II.5-quater) Crediti verso altri — entro l'esercizio")
    sp07g_crediti_altri_lungo: float = pydantic.Field(0, description="C.II.5-quater) Crediti verso altri — oltre l'esercizio")
    sp08_attivita_finanziarie: float = pydantic.Field(0, description="C.III) Attivita finanziarie che non costituiscono immobilizzazioni")
    sp09_disponibilita_liquide: float = pydantic.Field(0, description="C.IV) Disponibilita liquide")
    sp10_ratei_risconti_attivi: float = pydantic.Field(0, description="D) Ratei e risconti attivi")
    sp11_capitale: float = pydantic.Field(0, description="A.I) Capitale sociale")
    sp12_riserve: float = pydantic.Field(0, description="Sum of all reserves (II-VIII): sovrapprezzo, rivalutazione, legale, statutarie, altre, copertura flussi, utili portati, azioni proprie")
    sp13_utile_perdita: float = pydantic.Field(0, description="A.IX) Utile (perdita) dell'esercizio")
    sp14_fondi_rischi: float = pydantic.Field(0, description="B) Fondi per rischi e oneri")
    sp15_tfr: float = pydantic.Field(0, description="C) Trattamento di fine rapporto di lavoro subordinato")
    sp16_debiti_breve: float = pydantic.Field(0, description="D) Debiti esigibili entro l'esercizio successivo")
    sp17_debiti_lungo: float = pydantic.Field(0, description="D) Debiti esigibili oltre l'esercizio successivo")
    # Creditor-type breakdown per OIC art. 2424 (entro/oltre per group).
    # Must sum to sp16_debiti_breve and sp17_debiti_lungo respectively.
    sp16a_debiti_banche_breve: float = pydantic.Field(0, description="D.4) Debiti verso banche — entro l'esercizio")
    sp17a_debiti_banche_lungo: float = pydantic.Field(0, description="D.4) Debiti verso banche — oltre l'esercizio")
    sp16b_debiti_altri_finanz_breve: float = pydantic.Field(0, description="D.3)+D.5) Debiti verso soci per finanziamenti + verso altri finanziatori — entro l'esercizio")
    sp17b_debiti_altri_finanz_lungo: float = pydantic.Field(0, description="D.3)+D.5) Debiti verso soci per finanziamenti + verso altri finanziatori — oltre l'esercizio")
    sp16c_debiti_obbligazioni_breve: float = pydantic.Field(0, description="D.1)+D.2)+D.8) Obbligazioni + obbligazioni convertibili + debiti rappresentati da titoli di credito — entro l'esercizio")
    sp17c_debiti_obbligazioni_lungo: float = pydantic.Field(0, description="D.1)+D.2)+D.8) Obbligazioni + obbligazioni convertibili + debiti rappresentati da titoli di credito — oltre l'esercizio")
    sp16d_debiti_fornitori_breve: float = pydantic.Field(0, description="D.7) Debiti verso fornitori — entro l'esercizio")
    sp17d_debiti_fornitori_lungo: float = pydantic.Field(0, description="D.7) Debiti verso fornitori — oltre l'esercizio")
    sp16e_debiti_tributari_breve: float = pydantic.Field(0, description="D.12) Debiti tributari — entro l'esercizio")
    sp17e_debiti_tributari_lungo: float = pydantic.Field(0, description="D.12) Debiti tributari — oltre l'esercizio")
    sp16f_debiti_previdenza_breve: float = pydantic.Field(0, description="D.13) Debiti verso istituti di previdenza e di sicurezza sociale — entro l'esercizio")
    sp17f_debiti_previdenza_lungo: float = pydantic.Field(0, description="D.13) Debiti verso istituti di previdenza e di sicurezza sociale — oltre l'esercizio")
    sp16g_altri_debiti_breve: float = pydantic.Field(0, description="D.6)+D.9-11bis)+D.14) Acconti + verso controllate/collegate/controllanti + altri debiti — entro l'esercizio")
    sp17g_altri_debiti_lungo: float = pydantic.Field(0, description="D.6)+D.9-11bis)+D.14) Acconti + verso controllate/collegate/controllanti + altri debiti — oltre l'esercizio")
    sp18_ratei_risconti_passivi: float = pydantic.Field(0, description="E) Ratei e risconti passivi")
    totale_attivo: float = pydantic.Field(0, description="Totale attivo (total assets)")
    totale_passivo: float = pydantic.Field(0, description="Totale passivo (total equity + liabilities)")
    totale_debiti: float = pydantic.Field(0, description="Totale debiti (D) — the explicit 'Totale debiti' line from the PDF, sum of all debt categories (both entro and oltre). Used for validation.")
    totale_crediti: float = pydantic.Field(0, description="Totale crediti (C.II) — the explicit 'Totale crediti' line from the PDF, sum of all C.II debtor categories (both entro and oltre). Used for validation.")

class IncomeStatementExtraction(_ItalianNumberModel):
    """IV CEE Conto Economico fields."""
    ce01_ricavi_vendite: float = pydantic.Field(0, description="A.1) Ricavi delle vendite e delle prestazioni")
    ce02_variazioni_rimanenze: float = pydantic.Field(0, description="A.2) Variazioni delle rimanenze di prodotti in corso di lavorazione, semilavorati e finiti")
    ce03_lavori_interni: float = pydantic.Field(0, description="A.3) Variazioni dei lavori in corso su ordinazione")
    ce03a_incrementi_immobilizzazioni: float = pydantic.Field(0, description="A.4) Incrementi di immobilizzazioni per lavori interni")
    ce04_altri_ricavi: float = pydantic.Field(0, description="A.5) Altri ricavi e proventi")
    ce05_materie_prime: float = pydantic.Field(0, description="B.6) Per materie prime, sussidiarie, di consumo e di merci")
    ce06_servizi: float = pydantic.Field(0, description="B.7) Per servizi")
    ce07_godimento_beni: float = pydantic.Field(0, description="B.8) Per godimento di beni di terzi")
    ce08_costi_personale: float = pydantic.Field(0, description="B.9) Totale costi per il personale")
    ce08a_tfr_accrual: float = pydantic.Field(0, description="B.9c) Trattamento di fine rapporto (sub-item of personnel costs)")
    ce09_ammortamenti: float = pydantic.Field(0, description="B.10) Totale ammortamenti e svalutazioni")
    ce09a_ammort_immateriali: float = pydantic.Field(0, description="B.10a) Ammortamento delle immobilizzazioni immateriali")
    ce09b_ammort_materiali: float = pydantic.Field(0, description="B.10b) Ammortamento delle immobilizzazioni materiali")
    ce09c_svalutazioni: float = pydantic.Field(0, description="B.10c) Altre svalutazioni delle immobilizzazioni")
    ce09d_svalutazione_crediti: float = pydantic.Field(0, description="B.10d) Svalutazioni dei crediti compresi nell'attivo circolante")
    ce10_var_rimanenze_mat_prime: float = pydantic.Field(0, description="B.11) Variazioni delle rimanenze di materie prime, sussidiarie, di consumo e merci")
    ce11_accantonamenti: float = pydantic.Field(0, description="B.12) Accantonamenti per rischi")
    ce11b_altri_accantonamenti: float = pydantic.Field(0, description="B.13) Altri accantonamenti")
    ce12_oneri_diversi: float = pydantic.Field(0, description="B.14) Oneri diversi di gestione")
    ce13_proventi_partecipazioni: float = pydantic.Field(0, description="C.15) Proventi da partecipazioni")
    ce14_altri_proventi_finanziari: float = pydantic.Field(0, description="C.16) Altri proventi finanziari")
    ce15_oneri_finanziari: float = pydantic.Field(0, description="C.17) Interessi e altri oneri finanziari")
    ce16_utili_perdite_cambi: float = pydantic.Field(0, description="C.17-bis) Utili e perdite su cambi")
    ce17_rettifiche_attivita_fin: float = pydantic.Field(0, description="D) Totale delle rettifiche di valore di attivita e passivita finanziarie")
    ce18_proventi_straordinari: float = pydantic.Field(0, description="E.20) Proventi straordinari")
    ce19_oneri_straordinari: float = pydantic.Field(0, description="E.21) Oneri straordinari")
    ce20_imposte: float = pydantic.Field(0, description="22) Imposte sul reddito dell'esercizio")

class TwoYearBalanceSheetExtraction(pydantic.BaseModel):
    """IV CEE Stato Patrimoniale — both columns (current year + prior year)."""
    current_year: BalanceSheetExtraction = pydantic.Field(description="Current year values (leftmost/first column)")
    prior_year: BalanceSheetExtraction = pydantic.Field(description="Prior year values (rightmost/second column)")

class TwoYearIncomeStatementExtraction(pydantic.BaseModel):
    """IV CEE Conto Economico — both columns (current year + prior year)."""
    current_year: IncomeStatementExtraction = pydantic.Field(description="Current year values (leftmost/first column)")
    prior_year: IncomeStatementExtraction = pydantic.Field(description="Prior year values (rightmost/second column)")

# ---------------------------------------------------------------------------
# Deterministic IV-CEE detail-line reconciler (clean legal statements)
# ---------------------------------------------------------------------------
# A fully-printed IV-CEE bilancio (Micro/Abbreviato/Ordinario) lists every legal
# sub-line verbatim — including the patrimonio-netto reserve detail (II..X) and the
# personnel split (B.9 a/b/c/e). The LLM extractor only captures the AGGREGATES
# (sp12_riserve, ce08_costi_personale), so the sub-fields come back 0 and, worse, a
# NEGATIVE reserve line (VIII - utili (perdite) portati a nuovo) is dropped from the
# aggregate — which inflates equity and gets masked into cash by the balance reconcile
# (and the old _validate_equity, removed 2026-11-24, refused the correct fix because it yielded
# "negative reserves").
# These helpers read the explicit lines deterministically and, gated on the printed
# control total (anti-masking), fill the sub-fields and fix the aggregate. Text-path
# only (the lines are unambiguous in PyMuPDF text); the vision path keeps LLM behaviour.

def _parse_it_number(tok: str) -> Optional[Decimal]:
    """Parse one Italian-formatted amount token. Parentheses or trailing '-' = negative."""
    tok = tok.strip()
    if not tok:
        return None
    neg = False
    if tok.startswith('(') and tok.endswith(')'):
        neg = True
        tok = tok[1:-1].strip()
    if tok.endswith('-'):
        neg = True
        tok = tok[:-1].strip()
    if tok.startswith('-'):
        neg = True
        tok = tok[1:].strip()
    t = tok.replace('.', '').replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d+)?', t):
        return None
    v = Decimal(t)
    return -v if neg else v
