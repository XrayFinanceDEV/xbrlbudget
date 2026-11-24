"""Il bilancio di verifica letto dal modello (pass CoGe).

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import anthropic
import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple
from importers import llm_provider
from importers.estrazione_llm.modelli import (
    BalanceSheetExtraction, IncomeStatementExtraction, PDFImportError,
)
from importers.estrazione_llm.pagine import (
    _extract_full_text,
)
from importers.estrazione_llm.chiamate import (
    _extract_with_llm, _extract_with_llm_vision, _is_image_pdf, _render_pdf_pages_as_images,
    _text_layer_is_garbled,
)
from importers.estrazione_llm.riconciliazioni import (
    _model_to_decimal_dict, _normalize_ce_signs,
)
from importers.estrazione_llm.totali_dichiarati import (
    _TB_ASSET_KEYS, _TB_PASSIVO_KEYS_NO_RESULT, _declared_control_totals, _reconcile_trial_to_declared,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


# ---------------------------------------------------------------------------
# Trial-balance (situazione contabile / sezioni contrapposte) CoGe extraction
# ---------------------------------------------------------------------------
# Macro-area C documents are NOT legal IV-CEE statements: they are flat lists of
# general-ledger accounts (conti di contabilita' generale, "CoGe") with Dare/Avere
# or Saldo balances and NO art.2424/2425 schema. The IV-CEE prompts above read the
# legal schema and misfire on these. These dedicated prompts teach the model the
# trial-balance sign convention (Dare=asset/cost, Avere=liability/equity/revenue),
# contra-account netting (fondi ammortamento / svalutazione), and that the year's
# result is the Attivo-vs-Passivo gap — so the LLM actually reads the CoGe list.

TRIAL_BALANCE_SP_SYSTEM_PROMPT = """You are an expert Italian accountant reading a TRIAL BALANCE (bilancio di verifica / situazione contabile / saldi di contabilita' generale).

This is NOT a legal IV-CEE statement. It is a flat list of general-ledger accounts (conti CoGe), each with a code and one or two amount columns. Your job: classify the PATRIMONIAL accounts (assets, liabilities, equity) into the IV-CEE Stato Patrimoniale fields (sp01-sp18). IGNORE economic accounts (costi/ricavi) here — they belong to the income statement.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimals (1.234.567,89 = 1234567.89)
- Parentheses or a trailing minus mean negative
- Return plain numbers without formatting (no dots, no commas), in full euros

TRIAL-BALANCE LAYOUTS (handle all):
- Two columns "Dare" (debit) and "Avere" (credit): each account has a balance on ONE side; use that side's amount.
- A single "Saldo" column, sometimes with a D/A flag or a sign: the flag/sign tells the side.
- The COLUMN is ground truth for the side. Do NOT move an account to the other side based on its name.

SIGN / SIDE CONVENTION:
- ATTIVO (assets) accounts normally carry a DARE (debit) balance: cassa, banche c/c attive, crediti verso clienti, immobilizzazioni (immateriali/materiali/finanziarie), rimanenze/magazzino, ratei e risconti attivi, crediti tributari/erario c/, crediti v/altri.
- PASSIVO + PATRIMONIO NETTO accounts normally carry an AVERE (credit) balance: debiti verso fornitori, banche c/c passive (scoperti), capitale sociale, riserve, fondo rischi, fondo TFR, debiti tributari, debiti v/istituti previdenziali, ratei e risconti passivi.
- Report every sp* field as a POSITIVE magnitude on its natural side.

CONTRA ACCOUNTS — NET THEM, never put in passivo:
- "Fondo ammortamento ..." (any: immobilizzazioni immateriali/materiali) is an AVERE account that REDUCES the related asset. Subtract it from the gross asset so sp02/sp03 are reported NET of their fondi ammortamento.
- "Fondo svalutazione crediti" reduces crediti: report sp06/sp07 NET of it.
- Do NOT classify these fondi as fondi rischi (sp14) or debiti.
- CRITICAL — DO NOT CONFUSE the FONDO with the YEAR'S EXPENSE. Two kinds of
  "ammortamento" accounts exist and only ONE nets the assets:
  * FONDO ammortamento (patrimonial, ACCUMULATED depreciation): named "FONDO
    AMM.TO ..." / "F.DO AMM ..." / "F/AMM ..." and listed AMONG THE PATRIMONIAL
    accounts (Stato Patrimoniale / Attivita'-Passivita' section). These NET the
    assets. The Fondo prefix may be OCR-garbled ("roNDO AMM.TO", "FONDa"): an
    account containing AMM that sits among the SP accounts is a fondo even with a
    corrupted prefix.
  * The YEAR'S depreciation EXPENSE: named "AMM.TO ..." / "AMMORTAMENTO ..." /
    "QUOTA AMMORTAMENTO ..." WITHOUT the Fondo prefix and listed among the COSTI
    of the CONTO ECONOMICO section. This is an economic account: NEVER subtract it
    from sp02/sp03 — doing so double-counts (the expense already reduced the
    year's result) and fabricates a wrong net book value.
  The reliable discriminator is the SECTION the account appears in (SP vs CE
  costs), not the exact spelling. If an asset has no patrimonial FONDO account,
  its net value IS the gross value.

MAPPING (description -> field), report NET magnitudes:
- sp01_crediti_soci: crediti verso soci per versamenti dovuti
- sp02_immob_immateriali: immobilizzazioni immateriali (avviamento, software, costi pluriennali) NET of fondo amm.to immateriali
- sp03_immob_materiali: immobilizzazioni materiali (terreni, fabbricati, impianti, macchinari, attrezzature, automezzi, mobili) NET of fondo amm.to materiali
- sp04_immob_finanziarie: partecipazioni, crediti immobilizzati, titoli immobilizzati
- sp05_rimanenze: rimanenze / magazzino (materie prime, prodotti, merci, lavori in corso)
- sp06_crediti_breve: crediti dell'attivo circolante esigibili ENTRO l'esercizio (clienti, tributari, v/altri) NET of fondo svalutazione
- sp07_crediti_lungo: crediti dell'attivo circolante esigibili OLTRE l'esercizio
- sp08_attivita_finanziarie: attivita' finanziarie non immobilizzate (titoli, partecipazioni non durevoli)
- sp09_disponibilita_liquide: cassa, denaro, banche e poste c/c ATTIVI (saldo Dare)
- sp10_ratei_risconti_attivi: ratei e risconti attivi
- sp11_capitale: capitale sociale
- sp12_riserve: TUTTE le riserve (sovrapprezzo, rivalutazione, legale, statutarie, straordinaria, altre) + utili/(perdite) portati a nuovo. Do NOT include the current-year result here.
- sp13_utile_perdita: the CURRENT YEAR result — see RESULT rule below
- sp14_fondi_rischi: fondi per rischi e oneri (NOT fondi ammortamento)
- sp15_tfr: fondo trattamento di fine rapporto (TFR)
- sp16_debiti_breve: debiti esigibili ENTRO l'esercizio (fornitori, banche c/c passive, tributari, previdenziali, v/altri)
- sp17_debiti_lungo: debiti esigibili OLTRE l'esercizio (mutui, finanziamenti a lungo)
- sp18_ratei_risconti_passivi: ratei e risconti passivi

CREDITOR / DEBTOR BREAKDOWN — PRESERVE THE SOURCE'S DETAIL DEPTH:
- A trial balance names each account by type (es. "DEBITI V/FORNITORI", "ERARIO C/IVA",
  "INPS C/CONTRIBUTI", "MUTUO BANCA..."). When the type is determinable from the
  description, you MUST fill the matching typed sub-field — do NOT collapse everything
  into the aggregate. The sub-fields must sum to the aggregate:
  * crediti: sp06a/sp07a clienti, sp06e/sp07e tributari (erario, IVA, ritenute),
    sp06f imposte anticipate, sp06g/sp07g altri
  * debiti: sp16a/sp17a banche, sp16b/sp17b altri finanziatori, sp16c/sp17c obbligazioni,
    sp16d/sp17d fornitori, sp16e/sp17e tributari, sp16f/sp17f previdenza, sp16g/sp17g altri
- RECOGNISE THE DEBT TYPE FROM THE ITALIAN DESCRIPTION (do NOT default to 'altri'):
  * banche (sp16a/sp17a): any "Banca"/"Banco"/name ending in -banca (EmilBanca), "Banco BPM",
    "BPER Banca"; a "c/c" or "c.c." account standing on the PASSIVO / Avere side is a bank
    OVERDRAFT (fido) = debito verso banche, NOT cash; also "mutuo", "finanziamento bancario",
    "anticipo fatture", "anticipi su crediti", "anticipi s.b.f.", "SBF", "scoperto di c/c".
  * fornitori (sp16d/sp17d): "fornitori", "debiti commerciali", "fatture da ricevere" / "FDR",
    "note credito da ricevere".
  * tributari (sp16e/sp17e): "erario", "erariali", "IVA", "imposte", "ritenute", "F24".
  * previdenza (sp16f/sp17f): "INPS", "INAIL", "enti previdenziali", "ENPALS", "INARCASSA".
  * altri finanziatori (sp16b/sp17b): "altri finanziatori", "factor"; "soci c/finanziamento"
    and "soci c/c" are altri finanziatori (D.3/D.5), NOT bank c/c.
- Only leave a sub-field at 0 when no account of that type exists. Put a debt/credit
  whose type you genuinely cannot tell into the 'altri' bucket (sp16g / sp06g), never
  silently into the bare aggregate.

RESULT OF THE YEAR (sp13) — THE BALANCING RULE:
- A trial balance usually has NO "utile d'esercizio" account: the profit/loss is implicit.
- Compute sp13 so that the sheet balances: sp13 = totale_attivo - (sp11 + sp12 + sp14 + sp15 + sp16 + sp17 + sp18).
- A POSITIVE sp13 = utile; a NEGATIVE sp13 = perdita. Keep the sign.
- Only if the trial balance EXPLICITLY shows a separate "Utile/Perdita d'esercizio" account, use that value and verify it equals the gap.

COMPLETENESS — THE MOST IMPORTANT RULE (do not drop accounts):
- EVERY patrimonial account line in the trial balance must be classified into exactly one sp field. Do not skip lines, do not stop early on long lists, scan ALL pages.
- The trial balance prints its OWN control total ("TOTALE A PAREGGIO", "TOTALE ATTIVITA'", "TOTALE PASSIVITA'"). Your sum of the asset accounts MUST reconcile to the declared "TOTALE ATTIVITA'" (GROSS, i.e. before you net the fondi). If your running asset total is materially below the printed total, you have MISSED accounts — go back and find them before answering. The single most common error is dropping a whole block of debiti (fornitori, banche, tributari, previdenziali) or a large immobilizzazioni mastro.
- MASTRO + DOTTED CHILDREN layout: some trial balances print each voce as a level-1 "mastro" WITH its subtotal (e.g. "102 IMMOBILIZZAZIONI IMMATERIALI 2.429.051"), immediately followed by indented dotted children ("102.00002 Software 12.000"). Book the MASTRO SUBTOTAL ONCE. Do NOT also add its children (double-count) and do NOT add only the children while skipping the mastro (drops the rounding/other lines). One amount per voce.

TOTALS:
- totale_attivo = sum of sp01..sp10 (all NET of contra accounts)
- totale_passivo = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18
- totale_attivo MUST equal totale_passivo (sp13 absorbs the difference). Set both fields.
- Leave totale_debiti and totale_crediti at 0 unless the trial balance prints an explicit "Totale debiti"/"Totale crediti" line."""
TRIAL_BALANCE_CE_SYSTEM_PROMPT = """You are an expert Italian accountant reading a TRIAL BALANCE (bilancio di verifica / situazione contabile / saldi di contabilita' generale).

This is NOT a legal IV-CEE statement. It is a flat list of general-ledger accounts (conti CoGe). Your job: classify the ECONOMIC accounts (costi e ricavi) into the IV-CEE Conto Economico fields (ce01-ce20). IGNORE patrimonial accounts (assets, liabilities, equity) here.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimals (1.234.567,89 = 1234567.89)
- Parentheses or a trailing minus mean negative
- Return plain numbers without formatting, in full euros
- Report ALL COSTS as POSITIVE magnitudes (the model subtracts them). Report revenues as positive.

TRIAL-BALANCE SIGN CONVENTION:
- RICAVI / PROVENTI (revenue) accounts carry an AVERE (credit) balance.
- COSTI / ONERI (cost) accounts carry a DARE (debit) balance.
- Use the account's balance magnitude; the side identifies whether it is a revenue or a cost.

MAPPING (description -> field):
RICAVI (A — valore della produzione):
- ce01_ricavi_vendite: ricavi delle vendite e delle prestazioni (vendite merci/prodotti/servizi)
- ce02_variazioni_rimanenze: variazioni rimanenze di prodotti/semilavorati/lavori in corso
- ce03_lavori_interni: A.3 variazione dei lavori in corso su ordinazione
- ce03a_incrementi_immobilizzazioni: A.4 incrementi di immobilizzazioni per lavori interni
- ce04_altri_ricavi: altri ricavi e proventi, contributi in conto esercizio, sopravvenienze attive, rimborsi
COSTI (B — costi della produzione), all positive:
- ce05_materie_prime: acquisti di materie prime, sussidiarie, di consumo e merci
- ce06_servizi: costi per servizi (consulenze, utenze, trasporti, provvigioni, manutenzioni, compensi)
- ce07_godimento_beni: godimento beni di terzi (affitti, leasing, noleggi, royalties)
- ce08_costi_personale: TOTALE costi del personale (salari, stipendi, oneri sociali, TFR, altri)
- ce08a_tfr_accrual: quota TFR dell'esercizio (sub-item of ce08)
- ce09_ammortamenti: ammortamenti e svalutazioni (amm.to immateriali + materiali + svalutazioni crediti)
- ce10_var_rimanenze_mat_prime: variazioni rimanenze di materie prime/merci (segno: incremento rimanenze RIDUCE i costi)
- ce11_accantonamenti: accantonamenti per rischi
- ce11b_altri_accantonamenti: altri accantonamenti
- ce12_oneri_diversi: oneri diversi di gestione (imposte indirette, IMU, bolli, sopravvenienze passive, perdite su crediti)
AREA FINANZIARIA (C):
- ce13_proventi_partecipazioni: proventi da partecipazioni
- ce14_altri_proventi_finanziari: interessi attivi e altri proventi finanziari
- ce15_oneri_finanziari: interessi passivi e altri oneri finanziari (positive)
- ce16_utili_perdite_cambi: utili/perdite su cambi
RETTIFICHE (D) / STRAORDINARI (E) / IMPOSTE:
- ce17_rettifiche_attivita_fin: rivalutazioni/svalutazioni di attivita' finanziarie (net)
- ce18_proventi_straordinari: proventi straordinari
- ce19_oneri_straordinari: oneri straordinari (positive)
- ce20_imposte: imposte sul reddito dell'esercizio (IRES + IRAP) (positive)

RULES:
- AGGREGATE all account lines that map to the same ce* field (a trial balance has many detail accounts per IV-CEE item).
- NEVER leave the whole CE at zero when revenue and cost accounts are clearly present.
- Leave a field at 0 if no matching account exists.
- Extract the CURRENT YEAR values only."""

# Completeness retry for the CoGe SP pass: the LLM stochastically drops accounts on
# long trial-balance lists. Re-run up to N times and keep the lowest-residual draw; stop
# early once a draw's estimated residual is under _COGE_SP_CLEAN_PCT of total assets.
_COGE_SP_MAX_ATTEMPTS = 3

_COGE_SP_CLEAN_PCT = Decimal("0.02")  # 2% of totale_attivo = "clean enough", stop retrying

def extract_trial_balance_with_llm(
    file_path: str,
    ocr_text: Optional[str] = None,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Extract a macro-area C trial balance (situazione contabile / CoGe accounts)
    with a dedicated LLM pass that understands Dare/Avere account balances.

    Unlike extract_pdf_with_llm (which reads the legal IV-CEE schema), this sends
    the FULL trial-balance text and uses CoGe-specific prompts to classify
    general-ledger accounts into sp01-sp18 / ce01-ce20, netting contra accounts
    and deriving the year's result as the Attivo-vs-Passivo gap.

    Returns:
        (balance_sheet_data, income_data) - dicts with full DB field names + Decimal values.

    Raises:
        PDFImportError: if the API key is missing or extraction fails.
    """
    provider = llm_provider.provider_coge()
    client = None
    api_key = llm_provider.chiave_anthropic()
    if provider == "anthropic":
        if not api_key:
            raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")
        try:
            client = anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    # Scanned PDF already OCR'd by the caller: prefer the TEXT path over vision. Vision
    # mis-parses Italian number formatting on noisy scans (reads "50.704,41" as
    # 5.070.441, inflating values ~100x and dumping the gap into sp13); the linear OCR
    # text keeps the decimal comma, so numbers come out right.
    use_ocr = bool(ocr_text and ocr_text.strip())
    text_garbled = False
    if use_ocr:
        is_image = False
        images = None
        full_text = ocr_text
    else:
        is_image = _is_image_pdf(file_path)
        if is_image and provider == "gx10":
            # La vision non ha un fornitore locale: resta sul cloud (decisione del
            # proprietario, 2026-09-23). Senza chiave Anthropic si dichiara, e la route C
            # prosegue col candidato deterministico.
            if not api_key:
                raise PDFImportError("PDF solo immagine: il pass CoGe richiede la vision, "
                                     "che non ha un fornitore locale (ANTHROPIC_API_KEY assente)")
            client = anthropic.Anthropic(api_key=api_key)
        images = _render_pdf_pages_as_images(file_path) if is_image else None
        full_text = None
        if not is_image:
            full_text = _extract_full_text(file_path)
            if not full_text.strip():
                raise PDFImportError("No text extracted from trial-balance PDF")
            # A PRESENT-but-CORRUPTED text layer (broken ToUnicode font map —
            # budget_337) makes the text path stochastic. Switching to vision was
            # TRIED (2026-07-15) and is NOT better on these dense layouts (drops
            # whole blocks, misreads small print); the file is flagged as garbled
            # by pdf_importer instead, so the user knows every value needs review.
            if _text_layer_is_garbled(full_text):
                text_garbled = True
                logger.warning("Trial-balance text layer is GARBLED (broken font "
                               "map) — extraction unreliable, declared totals ignored")

    # Declared control totals (TOTALE A PAREGGIO / ATTIVO / explicit Utile-Perdita) read
    # deterministically from the printed footer — used BOTH as a hint to the LLM AND as
    # the post-pass reconciliation anchor. On a scanned PDF read them from the OCR text.
    # On a GARBLED text layer the declared totals are misreads (a CE-section total can
    # land in 'perdita' and flip the result sign) — do not read them at all.
    try:
        declared = ({} if text_garbled else
                    _declared_control_totals(file_path, text=full_text if use_ocr else None))
    except Exception:
        declared = {}
    # Inject the declared totals as a completeness anchor in the SP system prompt.
    sp_prompt = TRIAL_BALANCE_SP_SYSTEM_PROMPT
    _anchor = declared.get("attivo") or declared.get("pareggio") if declared else None
    if _anchor:
        sp_prompt = (TRIAL_BALANCE_SP_SYSTEM_PROMPT
                     + f"\n\nDOCUMENT CONTROL TOTAL: the printed TOTALE ATTIVITA' / A PAREGGIO of "
                       f"THIS document is approximately {_anchor:,.0f} euro (gross). Your classified "
                       f"asset accounts (before netting fondi) must reconcile to this figure — if your "
                       f"sum is materially lower, you have dropped accounts: re-scan all pages.")

    def _extract_ce():
        if is_image:
            return _extract_with_llm_vision(
                client, images, TRIAL_BALANCE_CE_SYSTEM_PROMPT,
                IncomeStatementExtraction, "Situazione Contabile (CE)", tool_name="income_statement")
        return _extract_with_llm(
            client, full_text, TRIAL_BALANCE_CE_SYSTEM_PROMPT,
            IncomeStatementExtraction, "Situazione Contabile (CE)", tool_name="income_statement",
            provider=provider)

    def _extract_sp_once():
        if is_image:
            res = _extract_with_llm_vision(
                client, images, sp_prompt,
                BalanceSheetExtraction, "Situazione Contabile (SP)", tool_name="balance_sheet")
        else:
            res = _extract_with_llm(
                client, full_text, sp_prompt,
                BalanceSheetExtraction, "Situazione Contabile (SP)", tool_name="balance_sheet",
                provider=provider)
        bs = _model_to_decimal_dict(res)
        bs = _balance_trial_via_result(bs, "coge")
        try:
            bs = _reconcile_trial_to_declared(bs, declared, "coge")
        except Exception as _rec_err:
            logger.warning(f"[coge] declared-total reconciliation skipped: {_rec_err}")
        return bs

    # COMPLETENESS RETRY: the LLM stochastically drops accounts on long lists (proven by
    # byte-identical files extracting one complete / one short). Run the SP pass up to
    # _COGE_SP_MAX_ATTEMPTS times and keep the draw with the SMALLEST post-reconcile
    # _plug_residual (least estimated mass). Stop early once a draw is materially clean.
    best_bs = None
    best_resid = None
    for attempt in range(_COGE_SP_MAX_ATTEMPTS):
        bs = _extract_sp_once()
        resid = bs.get("_plug_residual", Decimal("0"))
        att = bs.get("totale_attivo", Decimal("0")) or Decimal("1")
        if best_bs is None or resid < best_resid:
            best_bs, best_resid = bs, resid
        logger.info(f"[CoGe] SP attempt {attempt + 1}/{_COGE_SP_MAX_ATTEMPTS}: "
                    f"totale_attivo={bs.get('totale_attivo')} plug_residual={resid}")
        if resid <= max(Decimal("1"), att * _COGE_SP_CLEAN_PCT):
            break  # clean enough, no need to retry

    balance_sheet_data = best_bs
    income_data = _normalize_ce_signs(_model_to_decimal_dict(_extract_ce()))

    logger.info(f"[CoGe] SP totale_attivo = {balance_sheet_data.get('totale_attivo')} "
                f"(plug_residual={best_resid})")

    # CE is left exactly as extracted; canonical validation happens downstream.

    return balance_sheet_data, income_data

def _balance_trial_via_result(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Expose the balancing-result candidate without writing it into ``sp13``.

    The double-entry gap is useful evidence only when extraction coverage is known.
    Treating it as the actual result made every omitted liability look like profit.
    The explicit result and the independently reconstructed CE must confirm this
    candidate before an import can be accepted.
    """
    result = dict(balance_sheet_data)
    att = sum(balance_sheet_data.get(k, Decimal('0')) for k in _TB_ASSET_KEYS)
    pas_no_result = sum(balance_sheet_data.get(k, Decimal('0')) for k in _TB_PASSIVO_KEYS_NO_RESULT)
    candidate = att - pas_no_result
    current_sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    result['totale_attivo'] = att
    result['totale_passivo'] = pas_no_result + current_sp13
    result['_derived_result_candidate'] = candidate
    difference = candidate - current_sp13
    if abs(difference) > Decimal('0.01'):
        result['_unexplained_result_difference'] = difference
        result['_plug_residual'] = max(
            abs(result.get('_plug_residual', Decimal('0'))), abs(difference)
        )
        logger.warning(
            f"[{label}] risultato implicito {candidate:,.2f} non confermato: sp13 "
            f"estratto {current_sp13:,.2f}; nessun valore è stato modificato"
        )
    return result
