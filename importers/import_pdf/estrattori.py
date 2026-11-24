"""Gli estrattori deterministici e di ripiego che l'import prova, e come se ne adotta il candidato.

Spostato da importers/pdf_importer.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import logging
import os
from decimal import Decimal
from typing import Any, Dict, Optional
from importers.pdf_mapper import IVCEEMapper

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_importer")


# Soglia oltre cui un plug residuo del parser best-effort rende il bilancio inaffidabile
# (composizione per lo più fabbricata): sopra questa frazione del totale si rifiuta
# l'estrazione deterministica e si tenta l'LLM. Sotto, si importa con flag "BILANCIO NON
# QUADRATO" per correzione in Rettifiche (workflow esistente). Vedi iv_cee_hierarchy.
SC_PLUG_REJECT_PCT = Decimal("0.20")

# Map short keys from situazione_contabile_parser to full DB field names
_SC_KEY_MAP = {
    'sp01': 'sp01_crediti_soci', 'sp02': 'sp02_immob_immateriali', 'sp03': 'sp03_immob_materiali',
    'sp04': 'sp04_immob_finanziarie', 'sp04a': 'sp04a_partecipazioni', 'sp05': 'sp05_rimanenze',
    'sp06': 'sp06_crediti_breve', 'sp06g': 'sp06g_crediti_altri_breve',
    'sp07': 'sp07_crediti_lungo',
    'sp08': 'sp08_attivita_finanziarie', 'sp09': 'sp09_disponibilita_liquide',
    'sp10': 'sp10_ratei_risconti_attivi', 'sp11': 'sp11_capitale', 'sp12': 'sp12_riserve',
    'sp13': 'sp13_utile_perdita', 'sp14': 'sp14_fondi_rischi', 'sp15': 'sp15_tfr',
    # sp06g / sp16g are the KPI-neutral catch-all destinations named by
    # situazione_contabile_parser.FALLBACK_FIELDS. _map_sc_keys SILENTLY DROPS a
    # short key it does not know, so an unmapped fallback bucket would make read
    # mass disappear with no gate firing (the sp04a incident).
    'sp16': 'sp16_debiti_breve', 'sp16g': 'sp16g_altri_debiti_breve',
    'sp17': 'sp17_debiti_lungo',
    'sp18': 'sp18_ratei_risconti_passivi',
    'ce01': 'ce01_ricavi_vendite', 'ce02': 'ce02_variazioni_rimanenze',
    'ce03': 'ce03_lavori_interni',
    'ce03a': 'ce03a_incrementi_immobilizzazioni',
    'ce04': 'ce04_altri_ricavi',
    'ce05': 'ce05_materie_prime', 'ce06': 'ce06_servizi', 'ce07': 'ce07_godimento_beni',
    'ce08': 'ce08_costi_personale', 'ce09': 'ce09_ammortamenti',
    'ce10': 'ce10_var_rimanenze_mat_prime', 'ce11': 'ce11_accantonamenti',
    'ce11b': 'ce11b_altri_accantonamenti', 'ce12': 'ce12_oneri_diversi',
    'ce13': 'ce13_proventi_partecipazioni', 'ce14': 'ce14_altri_proventi_finanziari',
    'ce15': 'ce15_oneri_finanziari', 'ce16': 'ce16_utili_perdite_cambi',
    'ce17': 'ce17_rettifiche_attivita_fin',
    'ce17a': 'ce17a_rivalutazioni', 'ce17b': 'ce17b_svalutazioni',
    'ce18': 'ce18_proventi_straordinari',
    'ce19': 'ce19_oneri_straordinari', 'ce20': 'ce20_imposte',
}
def _map_sc_keys(data: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Map short SC parser keys (sp03, ce01) to full DB field names (sp03_immob_materiali)."""
    result = {}
    for k, v in data.items():
        # Already a full key? Pass through.
        if '_' in k:
            result[k] = v
        elif k in _SC_KEY_MAP:
            result[_SC_KEY_MAP[k]] = v
        # else: skip (totale_attivo, totale_passivo, etc.)
    return result

def _coge_attivo(api_key: str) -> bool:
    """Il pass CoGe di route C puo' girare? Con il fornitore di default (Haiku) serve la
    chiave Anthropic, come sempre; con gx10 serve la chiave gx10, e la chiave Anthropic
    non conta (la route C deve poter girare interamente in locale)."""
    from importers.llm_provider import gx10_disponibile, provider_coge
    if provider_coge() == "gx10":
        return gx10_disponibile()
    return bool(api_key)

def _ivcee_attivo(api_key: str) -> bool:
    """Il ramo IV-CEE via LLM (route A/B, e l'ultima risorsa di route C) puo' girare?
    Con il fornitore di default (Haiku) serve la chiave Anthropic, come sempre; con
    gx10 (PDF_LLM_PROVIDER_IVCEE=gx10) serve la chiave gx10, e la chiave Anthropic non
    conta per il ramo testuale. La vision resta sempre su Anthropic: i suoi cancelli,
    dentro pdf_extractor_llm.py, restano un controllo separato e invariato."""
    from importers.llm_provider import gx10_disponibile, provider_ivcee
    if provider_ivcee() == "gx10":
        return gx10_disponibile()
    return bool(api_key)

def _modello_non_disponibile(messaggio_storico: str) -> str:
    """Il messaggio quando serve un modello che non c'e'. Con Anthropic consentito resta quello
    di sempre; senza, dice la verita': la fase richiederebbe Anthropic (non consentito) o gx10
    (non configurato), ed e' stata saltata - mai un ripiego su un servizio a pagamento."""
    from importers.llm_provider import anthropic_consentito, gx10_disponibile
    if anthropic_consentito():
        return messaggio_storico
    if not gx10_disponibile():
        return ("Lettura col modello non disponibile: gx10 non configurato (GX10_API_KEY) e "
                "Anthropic non consentito. Nessun lettore a regole ha riconosciuto il documento.")
    return ("Questa fase richiederebbe Anthropic, che non e' consentito (solo gx10 e MinerU "
            "locali): fase saltata. Nessun lettore a regole ha riconosciuto il documento.")

def _ripiego_classico_acceso() -> bool:
    """Interruttore del ripiego sul percorso classico (Fase 4): acceso salvo
    ``IMPORT_RIPIEGO_CLASSICO`` = 0/false/no/off. Spento, un documento che lo snello non adotta
    esce con un ``PDFImportError`` chiaro invece di passare al classico."""
    return os.environ.get("IMPORT_RIPIEGO_CLASSICO", "1").strip().lower() not in ("0", "false", "no", "off")

def _motivo_ripiego_classico(snello_report: Optional[dict]) -> str:
    """Perche' lo snello ha ceduto al classico, per ``validation_report['import_snello']``."""
    if snello_report is None:
        return "motore_classico"
    if snello_report.get("esito") == "non_applicabile":
        return "non_applicabile"
    if snello_report.get("fase") == "eccezione":
        return "eccezione"
    if snello_report.get("fonte_testo") == "tabelle_mineru":
        return "scansione_non_quadra"
    return "ripiego"

def _motore_snello() -> bool:
    """L'importatore e' il motore di default (decisione del proprietario, 2026-10-16:
    "devono essere tutti su snello"): lettori a regole prima di qualunque modello, poi gx10.
    ``IMPORT_MOTORE=classico`` (o qualunque valore diverso da "snello") torna all'importatore
    di prima; la variabile assente vale "snello"."""
    return os.environ.get("IMPORT_MOTORE", "snello").strip().lower() == "snello"

def _xbrl_reso_extract(file_path: str):
    """(bs, ce, prior_bs, prior_ce) del PDF reso da un XBRL depositato, oppure None.

    Lo stesso lettore che l'importatore prova per primo (``xbrl_reso_parser``: ogni totale
    stampato riprodotto al centesimo, nessuna tolleranza), qui anche per il percorso di sempre:
    senza, un micro reso da XBRL (SGH 31/12/2025) finiva al modello, sei minuti e il passivo
    perso. Si adotta solo il candidato che il lettore dichiara ``adottabile`` e che passa gli
    stessi cancelli degli altri lettori deterministici."""
    from importers import xbrl_reso_parser

    return _adotta_candidato_reso(xbrl_reso_parser.estrai(file_path), "PDF reso da XBRL")

def _adotta_candidato_reso(candidato: Optional[dict], nome: str):
    """(bs, ce, prior_bs, prior_ce) di un candidato del cuore del lettore XBRL
    (``xbrl_reso_parser.estrai_da_righe``: il reso XBRL e lo schema di legge generico), oppure
    None. Si adotta solo il candidato ``adottabile`` che passa ``validate_balance`` e
    ``check_quadratura``; l'anno precedente solo se li passa anche lui."""
    from importers.iv_cee_hierarchy import check_quadratura

    if candidato is None:
        return None
    if not candidato.get("adottabile"):
        logger.info("%s riconosciuto ma non adottato: %s", nome, candidato.get("rifiuto"))
        return None
    mapper = IVCEEMapper()
    bs, ce = dict(candidato["bs"]), dict(candidato["ce"])

    def _con_totali(b, stampati):
        if stampati.get("totale_attivo") is not None:
            b["totale_attivo"] = Decimal(stampati["totale_attivo"])
        if stampati.get("totale_passivo") is not None:
            b["totale_passivo"] = Decimal(stampati["totale_passivo"])
        return b

    bs = _con_totali(bs, candidato.get("stampati") or {})
    if not (mapper.validate_balance(bs) and check_quadratura(bs, ce, tol=Decimal("2")).quadra):
        return None
    prior_bs, prior_ce = candidato.get("prior_bs"), candidato.get("prior_ce")
    if prior_bs is not None and prior_ce is not None:
        from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS
        prior_bs = dict(prior_bs)
        prior_bs["totale_attivo"] = sum((Decimal(prior_bs.get(k, 0) or 0) for k in _ATTIVO_FIELDS), Decimal(0))
        prior_bs["totale_passivo"] = sum((Decimal(prior_bs.get(k, 0) or 0) for k in _PASSIVO_FIELDS), Decimal(0))
        if not (mapper.validate_balance(prior_bs)
                and check_quadratura(prior_bs, prior_ce, tol=Decimal("2")).quadra):
            prior_bs = prior_ce = None
    logger.info("Using deterministic legal schema reader: %s (prior=%s)", nome,
                candidato.get("prior_stato"))
    return bs, ce, prior_bs, prior_ce

def _schema_etichette_extract(file_path: str, extraction_context: Any = None):
    """(bs, ce, prior_bs, prior_ce) dello schema col percorso nell'etichetta, oppure None.

    Le tabelle MinerU quando c'e' una scansione, altrimenti il testo del PDF. Il lettore ha
    gia' verificato ogni totale stampato; qui passano gli stessi cancelli degli altri lettori
    deterministici (``validate_balance`` e ``check_quadratura``), e l'anno precedente si
    porta solo se li passa anche lui. Un anno che il lettore rifiuta non si sostituisce:
    si torna None e prosegue la catena di sempre, che lo dichiarera' a modo suo."""
    from importers import schema_etichette_parser as etichette

    if extraction_context is not None:
        letto = etichette.estrai_da_mineru(extraction_context)
    else:
        letto = etichette.estrai(file_path)
    return _adotta_schema(letto, extraction_context, "Schema con percorso nell'etichetta")

def _schema_generico_mineru_extract(extraction_context: Any):
    """(bs, ce, prior_bs, prior_ce) dello schema di legge di una scansione senza percorso
    nell'etichetta, dalle tabelle MinerU, oppure None.

    Le stesse regole e gli stessi controlli al centesimo del lettore dello schema di legge
    generico (``schema_legge_generico.estrai_da_mineru``): prima di MinerU 4 le tabelle di
    una scansione non erano abbastanza pulite, e questa famiglia finiva sull'estrattore
    Anthropic, vietato, cioe' su un errore (budget_1322, 2026-10-26)."""
    from importers import schema_legge_generico as generico

    adottato = _adotta_candidato_reso(generico.estrai_da_mineru(extraction_context),
                                      "Schema di legge dalle tabelle MinerU")
    if adottato is not None:
        for dati in (adottato[0], adottato[2]):
            if dati is not None:
                dati["_mineru_source_detail_fields"] = Decimal(sum(
                    1 for k, v in dati.items() if not k.startswith("_") and k.startswith("sp")
                    and len(k.split("_")[0]) > 4 and v))
    return adottato

def _prospetto_sintetico_mineru_extract(extraction_context: Any):
    """(bs, ce, None, None) del prospetto CEE sintetico a una colonna di una scansione, dalle
    tabelle MinerU (``prospetto_sintetico.estrai_da_mineru``, budget_1405), oppure None. Le
    stesse verifiche dell'importatore (``deterministico._esito``: ogni totale stampato, la
    massa non classificata) e gli stessi cancelli degli altri lettori. Le approssimazioni
    (il totale di una voce senza dettaglio nel suo sotto-campo convenzionale) restano
    dichiarate in ``_approssimazioni_prospetto``, come le dichiara lo snello."""
    from importers import prospetto_sintetico
    from importers.import_snello.deterministico import _esito

    letto = prospetto_sintetico.estrai_da_mineru(extraction_context)
    if letto is None or letto.get("bs") is None:
        if letto is not None:
            logger.info("Prospetto sintetico dalle tabelle MinerU non adottato: %s", letto.get("rifiuto"))
        return None
    esito = _esito("prospetto_sintetico", letto["bs"], letto["ce"], letto["stampati"])
    if not esito.get("adottato") or esito.get("esito") != "ok":
        logger.info("Prospetto sintetico dalle tabelle MinerU non adottato: %s", esito.get("esito"))
        return None
    adottato = _adotta_candidato_reso(
        {"adottabile": True, "bs": esito["bs"], "ce": esito["ce"], "stampati": letto["stampati"]},
        "Prospetto sintetico dalle tabelle MinerU")
    if adottato is not None:
        adottato[0]["_approssimazioni_prospetto"] = sorted(
            {x["campo"] for x in letto.get("approssimazioni") or []})
        adottato[0]["_source_prospetto_sintetico"] = Decimal("1")
    return adottato

def _adotta_schema(letto: Optional[dict], extraction_context: Any, nome: str):
    """I cancelli comuni ai lettori deterministici dello schema di legge: il lettore ha
    gia' verificato ogni totale stampato; qui ``validate_balance`` e ``check_quadratura``, e
    l'anno precedente si porta solo se li passa anche lui."""
    from importers.iv_cee_hierarchy import check_quadratura

    mapper = IVCEEMapper()
    if letto is None:
        return None
    bs, ce = letto.get("bs"), letto.get("ce")
    if bs is None or ce is None:
        logger.info("%s riconosciuto ma non adottato: %s", nome, letto.get("rifiuto"))
        return None

    def _passa(b, c) -> bool:
        return mapper.validate_balance(b) and check_quadratura(b, c, tol=Decimal("2")).quadra

    if not _passa(bs, ce):
        logger.info("%s letto ma non quadrato: catena di sempre", nome)
        return None
    prior_bs, prior_ce = letto.get("prior_bs"), letto.get("prior_ce")
    prior_ok = prior_bs is not None and prior_ce is not None and _passa(prior_bs, prior_ce)
    if extraction_context is not None:
        for dati in (bs, prior_bs if prior_ok else None):
            if dati is not None:
                dati["_mineru_source_detail_fields"] = Decimal(sum(
                    1 for k, v in dati.items() if not k.startswith("_") and k.startswith("sp")
                    and len(k.split("_")[0]) > 4 and v))
    logger.info("Using deterministic legal schema: %s (prior_valid=%s, anni=%s)",
                nome, prior_ok, letto.get("anni"))
    return bs, ce, (prior_bs if prior_ok else None), (prior_ce if prior_ok else None)

def _dettagli_gia_letti(snello_report: Optional[dict], mineru_tabelle: bool,
                        da_mineru: bool, bs: dict) -> Optional[str]:
    """Il motivo per non rifare la ricerca dei dettagli, o None se va fatta.

    - Reso XBRL adottato dall'importatore (Task 25): i dettagli sono gia' quelli del
      prospetto e delle tabelle di nota, riconciliati al centesimo o dichiarati.
    - Situazione contabile dalle tabelle MinerU: ogni sottoconto e' gia' una cella letta; sulla
      scansione la ricerca non ha testo e finiva su Qwen (6 minuti su Unicarton, per nessuna
      proposta).
    - Schema di legge letto dalle tabelle MinerU (col percorso nell'etichetta, generico, o
      prospetto sintetico): il lettore ha gia' verificato ogni dettaglio sul suo totale
      stampato, e il prospetto sintetico un dettaglio non lo stampa affatto (le sue voci
      sono dichiarate nell'avviso PROSPETTO SINTETICO). Col testo pulito di
      MinerU 4 la ricerca partiva su Qwen e ne respingeva ogni proposta (budget_1319: 70-115 s
      invece di 6-9, e otto avvisi «DETTAGLI NON APPLICATI» su un foglio gia' dettagliato).
    - Percorso del lettore adottato (Fase 3): dettagli e scadenze sono gia' decisi foglia per foglia."""
    if snello_report is not None and snello_report.get("fonte") == "deterministico:xbrl_reso_parser":
        return "dettagli_letti_dal_prospetto_xbrl"
    if snello_report is not None and snello_report.get("fonte") == "deterministico:lettore":
        # Fase 3, Task 11: il lettore ha gia' deciso per ogni foglia il dettaglio piu' fine e la scadenza dal testo
        # stampato (senza prova a breve); la ricerca rileggeva il documento con la regola gestionale «finanziamenti e
        # mutui oltre 12 mesi» e spostava sp16/sp17 contro quella decisione
        return "dettagli_letti_dal_lettore"
    if mineru_tabelle:
        return "dettagli_letti_dalle_tabelle_mineru"
    if da_mineru and (bs.get("_source_schema_etichette") or bs.get("_source_xbrl_reso")
                      or bs.get("_source_prospetto_sintetico")):
        return "dettagli_letti_dallo_schema_mineru"
    return None

def _extract_route_c_last_resort(llm_extract):
    """Run the IV-CEE last resort without claiming a gross-vs-net measurement.

    Route C documents can print gross control totals while the IV-CEE extractor
    correctly nets contra-assets.  The extractor's unclassified-mass diagnostic
    is therefore not comparable on this route: keep the keys explicit, but mark
    the measurement as unknown for both the current and comparative years.

    ``llm_extract`` is injected so this production seam is testable without an
    API call or a corpus document capable of exhausting both route-C parsers.
    """
    from importers.iv_cee_hierarchy import withdraw_unclassified_mass

    balance_sheet_data, income_data, prior_bs_data, prior_ce_data = llm_extract()
    balance_sheet_data.update(
        withdraw_unclassified_mass("route-c-ultima-risorsa")
    )
    if prior_bs_data:
        prior_bs_data.update(
            withdraw_unclassified_mass("route-c-ultima-risorsa-prior")
        )
    return balance_sheet_data, income_data, prior_bs_data, prior_ce_data
