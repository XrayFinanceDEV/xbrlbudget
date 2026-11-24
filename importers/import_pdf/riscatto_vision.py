"""Il riscatto vision di uno stato patrimoniale che il testo non legge.

Spostato da importers/pdf_importer.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from importers.import_pdf.estrattori import (
    _map_sc_keys,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_importer")


def _apply_vision_rescue(file_path: str,
                         balance_sheet_data: Dict[str, Decimal],
                         income_data: Dict[str, Decimal],
                         declared: Dict[str, Optional[Decimal]],
                         donor_bs: Optional[Dict[str, Decimal]],
                         ocr_text: Optional[str],
                         reader=None) -> Tuple[Dict[str, Decimal], Dict[str, Decimal],
                                               List[str], Dict[str, str]]:
    """Riscatto vision per sezione, in coda alla catena route C.

    Ritorna (bilancio, conto economico, sezioni riscattate, motivi). I `motivi` sono
    la stringa che il cancello ha prodotto per OGNI sezione tentata, accettata o no:
    e' la provenienza che finisce nel validation_report persistito (spec §5).

    Innesco: check_quadratura sul foglio FINITO. La posizione e' deliberata — innescare
    prima del netting farebbe scattare il riscatto su un attivo ancora lordo, un divario
    che il netting dei fondi chiude da solo. Le due sezioni si innescano in modo
    indipendente: un file puo' riscattare il CE e lasciare l'SP com'e'.

    Ogni errore e' NON fatale: si logga e si tiene il candidato precedente. Se il
    riscatto non riesce, il foglio resta esattamente com'e' oggi.
    """
    from importers import vision_rescue as vr
    from importers.iv_cee_hierarchy import check_quadratura
    from importers import situazione_contabile_parser as scp

    read = reader or vr.read_section
    rescued: List[str] = []
    reasons: Dict[str, str] = {}
    try:
        before = check_quadratura(balance_sheet_data, income_data)
    except Exception as err:
        logger.warning(f"Riscatto vision: quadratura iniziale non calcolabile ({err})")
        return balance_sheet_data, income_data, rescued, reasons

    sp_broken = before.is_empty or abs(before.sbilancio) > Decimal("0.01") or before.masked
    ce_broken = not before.utile_match
    if not sp_broken and not ce_broken:
        return balance_sheet_data, income_data, rescued, reasons

    try:
        pages = scp.section_pages(file_path)
    except Exception as err:
        logger.warning(f"Riscatto vision: pagine per sezione non determinabili ({err})")
        return balance_sheet_data, income_data, rescued, reasons

    # --- Conto economico ---------------------------------------------------
    if ce_broken:
        try:
            sec = read(file_path, pages.get("ce", []), "ce")
            # Stesso reintegro dello SP (vedi il ramo sotto): la riga saltata dalla
            # vision si ripesca dal text layer solo se spiega il divario al centesimo.
            # Qui la voce si risolve con il resolver del CE, non con quelli dell'SP.
            if sec is not None:
                sec = vr.close_gaps(file_path, pages.get("ce", []), sec)
            if sec is not None and sec.rows:
                new_ce = _map_sc_keys(scp.build_ce_from_vision(
                    [(r.code, r.description, r.amount, r.column) for r in sec.rows]))
                rebuilt = sum((r.amount for r in sec.rows if r.column == "left"),
                              Decimal("0"))
                # Il CE non tocca il bilancio: lo si passa immutato su entrambi i lati
                # del confronto. Con ce=None `utile_match` varrebbe True per difetto e
                # il ramo `fixed_identity` del cancello scatterebbe a vuoto.
                after = check_quadratura(balance_sheet_data, new_ce)
                # `residual_measured` resta al suo default True: qui il bilancio non
                # viene toccato, quindi after.plug_residual == before.plug_residual e il
                # parametro non cambierebbe nulla in nessuno dei due valori.
                ok, why = vr.accept_rescue("ce", rebuilt, sec, declared, before, after)
                logger.info(f"Riscatto vision CE: {'accettato' if ok else 'scartato'} — {why}")
                reasons["ce"] = why
                if ok:
                    income_data = new_ce
                    before = after
                    rescued.append("ce")
        except Exception as err:
            logger.warning(f"Riscatto vision CE fallito ({type(err).__name__}: {err})")

    # --- Stato patrimoniale ------------------------------------------------
    if sp_broken:
        try:
            sec = read(file_path, pages.get("sp", []), "sp")
            # La vision salta a intermittenza una riga, e la tolleranza del cancello
            # (0,5% del totale stampato) puo' essere piu' larga della riga saltata:
            # il riscatto passerebbe col buco dentro, e quel buco diventerebbe lo
            # sbilancio finale. Misurato su budget_623 (9.079,77 = i debiti verso
            # istituti previdenziali). Il reintegro ripesca dal TEXT LAYER solo una
            # riga che spieghi il divario al centesimo: non inventa massa, e se non
            # trova nulla la sezione resta com'era.
            if sec is not None:
                sec = vr.close_gaps(file_path, pages.get("sp", []), sec)
            if sec is not None and sec.rows:
                # Il segno del risultato lo decide l'identita' che ha VALIDATO i totali
                # letti, non l'ordine delle chiavi: un documento stampa spesso sia un
                # "utile" sia una "perdita" e preferire il primo ribalta il risultato
                # quando e' il ramo della perdita a tornare.
                utile = vr.vision_result(sec)
                # Letto sul `declared` COME RICEVUTO, prima che la ricaduta qui sotto
                # sovrascriva _decl coi totali vision: e' la presenza di un'ancora
                # INDIPENDENTE (stampata e letta dal testo) a rendere misurabile il
                # residuo del foglio riscattato. I totali vision non lo sono — sono la
                # stessa lettura che si sta riscattando.
                _has_text_anchor = any((declared or {}).get(_k)
                                       for _k in ('attivo', 'passivo', 'pareggio'))
                if utile is None:
                    logger.info("Riscatto vision SP: totali letti non coerenti — non tentato")
                else:
                    _raw_bs = scp.build_sp_from_vision(
                        [(r.code, r.description, r.amount, r.column) for r in sec.rows],
                        utile=utile)
                    new_bs = _map_sc_keys(_raw_bs)
                    # Letto PRIMA della catena: dopo net_contra_accounts questa chiave
                    # non descrive piu' la stessa massa.
                    netted = new_bs.get('_netted_contra', Decimal('0'))
                    # Il totale stampato e' LORDO quando i fondi stanno sul passivo: si
                    # misura il lordo contro il lordo (stesso cancello di _hier_reconstruct).
                    rebuilt = new_bs.get('totale_attivo', Decimal('0')) + netted
                    # L'omologo della colonna di destra, costruito per essere
                    # confrontabile con il TOTALE PASSIVITA' stampato:
                    #   totale_passivo somma _PASSIVO_KEYS, sp13 COMPRESO, mentre il
                    #   totale di colonna stampato NON comprende il risultato (che il
                    #   documento espone come riga di pareggio: attivo == passivo +
                    #   utile, oppure attivo + perdita == passivo) -> si sottrae `utile`;
                    #   i fondi ammortamento sono righe della colonna DESTRA che
                    #   build_sp_from_vision sottrae dall'attivo, quindi non sono in
                    #   totale_passivo mentre sono nel totale stampato -> si risomma
                    #   `netted`, esattamente come per l'attivo qui sopra.
                    # Il risultato e' la somma delle righe lette a destra: la stessa
                    # cosa che il documento stampa come totale di colonna.
                    rebuilt_pas = (_raw_bs.get('totale_passivo', Decimal('0'))
                                   - utile + netted)

                    # Stessa post-elaborazione degli altri candidati.
                    if donor_bs is not None:
                        new_bs = scp.overlay_debt_typing(new_bs, donor_bs)
                    new_bs, _contra = scp.net_contra_accounts(
                        new_bs, file_path, text=ocr_text, declared=declared)
                    from importers.pdf_extractor_llm import _reconcile_trial_to_declared
                    _decl = dict(declared or {})
                    # Su un layer di testo illeggibile le ancore dichiarate sono vuote
                    # (route C le azzera di proposito), e senza ancora
                    # _reconcile_trial_to_declared non misura NULLA: lo zero asserito da
                    # build_sp_from_vision sopravvivrebbe fino al cancello, regalandogli
                    # un miglioramento che nessuno ha verificato. I totali letti in
                    # vision hanno gia' superato il controllo di coerenza interna
                    # (vision_result), quindi qui valgono da ancora — e' la stessa
                    # sanzione per cui section_anchor li preferisce.
                    if not any(_decl.get(_k) for _k in ('attivo', 'passivo', 'pareggio')):
                        _vis_att, _vis_pas = sec.totals.get("left"), sec.totals.get("right")
                        if _vis_att:
                            _decl['attivo'] = _vis_att
                        if _vis_pas:
                            _decl['passivo'] = _vis_pas
                    # La riduzione vale anche per le ancore vision: sono LORDE quanto
                    # quelle stampate, quindi passano di qui prima del confronto.
                    _cut = _contra if _contra > 0 else netted
                    if _cut > 0:
                        for _k in ('attivo', 'passivo', 'pareggio'):
                            if _decl.get(_k):
                                _decl[_k] = _decl[_k] - _cut
                    # Indispensabile: build_sp_from_vision ASSERISCE _plug_residual = 0,
                    # non lo misura. E' questa chiamata a sostituirlo con il divario
                    # misurato contro il totale dichiarato — senza, ogni riscatto SP
                    # entrerebbe nel cancello con un miglioramento regalato.
                    new_bs = _reconcile_trial_to_declared(new_bs, _decl, "vision")

                    after = check_quadratura(new_bs, income_data)
                    ok, why = vr.accept_rescue("sp", rebuilt, sec, declared, before,
                                               after,
                                               residual_measured=_has_text_anchor,
                                               rebuilt_passivo=rebuilt_pas)
                    logger.info(f"Riscatto vision SP: {'accettato' if ok else 'scartato'} — {why}")
                    reasons["sp"] = why
                    if ok:
                        balance_sheet_data = new_bs
                        rescued.append("sp")
        except Exception as err:
            logger.warning(f"Riscatto vision SP fallito ({type(err).__name__}: {err})")

    return balance_sheet_data, income_data, rescued, reasons
