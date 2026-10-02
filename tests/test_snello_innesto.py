"""Innesto del percorso snello in pdf_importer.py, dietro IMPORT_MOTORE=snello.

Impianto identico a tests/test_provenienza_llm.py e tests/test_coge_provider.py: DB SQLite
in memoria agganciato a pdf_importer.SessionLocal, fixture PDF di route C (RIGHE_PAREGGIO)
letta dal parser deterministico SENZA bisogno di ANTHROPIC_API_KEY. import_snello.importa e'
sempre sostituita con una finta: nessuna rete, nessuna vera lettura di struttura documento.
"""
import json
from decimal import Decimal as D

import pytest

from importers import import_snello, llm_provider, pdf_importer
from importers.import_snello import SnelloNonRiuscito, Risultato
from importers.struttura_documento.analisi import Struttura
from tests.test_coge_provider import RIGHE_PAREGGIO, _pdf


def _db_in_memoria(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", session_factory)
    return session_factory


def _validation_report_persistito(session_factory, company_id, fiscal_year):
    from database.models import FinancialYear

    with session_factory() as db:
        fy = db.query(FinancialYear).filter_by(
            company_id=company_id, year=fiscal_year).one()
        return json.loads(fy.validation_report)


def _struttura(modo="legge", pagine_sp=(1,), pagine_dettaglio=(1,)):
    return Struttura(
        fonte="vision", route=None, pagine_sp=list(pagine_sp), pagine_ce=list(pagine_sp),
        pagine_dettaglio=list(pagine_dettaglio), chiamate_vision=0, secondi=0.1, modo=modo,
    )


def _risultato_quadrato(modo="legge"):
    bs = {"sp09_disponibilita_liquide": D("1000"), "sp11_capitale": D("1000"),
          "_plug_residual": D("0"), "_unclassified_mass": D("0")}
    ce = {}
    report = {"esito": "ok", "modo": modo, "struttura": {}, "misura": {"corrente": {}},
             "tappo": {"corrente": None}, "letture": {"sp": 1, "ce": 1},
             "diag": {"lato_irrisolti": []}, "anomalie": [], "secondi": 0.1}
    return Risultato(bs=bs, ce=ce, prior_bs=None, prior_ce=None, report=report,
                     struttura=_struttura(modo=modo))


def _vieta_estrattori_di_oggi(monkeypatch):
    """Route C e route A/B non devono girare affatto quando lo snello vince: se uno di
    questi tre entra, solleva ed il test fallisce con un messaggio esplicito."""
    from importers import macro_analysis, pdf_extractor_llm

    def _vietato(nome):
        def _f(*a, **k):
            raise AssertionError(f"{nome} chiamato mentre lo snello aveva gia' vinto")
        return _f

    monkeypatch.setattr(pdf_extractor_llm, "extract_trial_balance_with_llm",
                        _vietato("extract_trial_balance_with_llm"))
    monkeypatch.setattr(pdf_extractor_llm, "extract_pdf_with_llm",
                        _vietato("extract_pdf_with_llm"))
    monkeypatch.setattr(macro_analysis, "analyze_pdf_macros",
                        _vietato("analyze_pdf_macros"))


def test_interruttore_assente_non_chiama_la_finta_e_report_senza_chiave(tmp_path, monkeypatch):
    monkeypatch.delenv("IMPORT_MOTORE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _vietata(*a, **k):
        raise AssertionError("import_snello.importa chiamato senza IMPORT_MOTORE=snello")
    monkeypatch.setattr(import_snello, "importa", _vietata)
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Interruttore assente", create_company=True, sector=1,
        user_id="snello-assente", period_months=12,
    )
    assert "import_snello" not in result["validation_report"]
    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert "import_snello" not in persistito


def test_switch_acceso_finta_quadrata_vince_su_tutto(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)

    chiamate = []
    def finta_importa(file_path, *, ocr_text=None, **_):
        chiamate.append(file_path)
        return _risultato_quadrato()
    monkeypatch.setattr(import_snello, "importa", finta_importa)
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Switch acceso quadrato", create_company=True, sector=1,
        user_id="snello-ok", period_months=12,
    )
    assert len(chiamate) == 1
    assert result["extraction_method"] == "import_snello"
    assert result["validation_report"]["import_snello"]["esito"] == "ok"

    from database.models import FinancialYear
    with session_factory() as db:
        fy = db.query(FinancialYear).filter_by(
            company_id=result["company_id"], year=2025).one()
        assert fy.balance_sheet.sp09_disponibilita_liquide == D("1000.00")
        assert fy.balance_sheet.sp11_capitale == D("1000.00")

    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert persistito["import_snello"]["esito"] == "ok"


def test_snello_non_riuscito_dichiarato_ripiega_sull_estrattore_di_oggi(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def finta_importa(*a, **k):
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "verifica"})
    monkeypatch.setattr(import_snello, "importa", finta_importa)
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Ripiego dichiarato", create_company=True, sector=1,
        user_id="snello-ripiego", period_months=12,
    )
    # L'estrattore di oggi (deterministico, route C) prosegue e produce un bilancio quadrato:
    # nessuna delle due finte di route A/B/macro serve qui, la fixture RIGHE_PAREGGIO basta
    # come negli altri test di route C senza chiave Anthropic.
    assert result["success"] is True
    assert result["extraction_method"] != "import_snello"
    assert result["validation_report"]["import_snello"] == {"esito": "ripiego", "fase": "verifica"}

    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert persistito["import_snello"] == {"esito": "ripiego", "fase": "verifica"}


def test_eccezione_generica_diventa_ripiego_dichiarato(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def finta_importa(*a, **k):
        raise RuntimeError("qwen non risponde")
    monkeypatch.setattr(import_snello, "importa", finta_importa)
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Eccezione generica", create_company=True, sector=1,
        user_id="snello-eccezione", period_months=12,
    )
    assert result["success"] is True
    vr = result["validation_report"]["import_snello"]
    assert vr["esito"] == "ripiego"
    assert vr["fase"] == "eccezione"
    assert vr["errore"] == "RuntimeError"

    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert persistito["import_snello"]["errore"] == "RuntimeError"


def test_eccezione_dopo_limporta_riuscito_non_lascia_snello_agganciato(tmp_path, monkeypatch):
    """import_snello.importa() torna un Risultato (non solleva), ma il suo bs porta un valore
    non numerico: il calcolo di totale_attivo/totale_passivo (dentro il try, DOPO che importa()
    e' gia' tornato) solleva InvalidOperation. _snello non deve restare agganciato al risultato
    mai adottato per intero: i due cancelli restano aperti e l'import ripiega sull'estrattore di
    oggi, esattamente come una SnelloNonRiuscito o una RuntimeError sollevate PRIMA."""
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    bs_cattivo = {"sp09_disponibilita_liquide": "non-numerico",
                 "_plug_residual": D("0"), "_unclassified_mass": D("0")}
    report = {"esito": "ok", "modo": "legge", "struttura": {}, "misura": {"corrente": {}},
             "tappo": {"corrente": None}, "letture": {"sp": 1, "ce": 1},
             "diag": {"lato_irrisolti": []}, "anomalie": [], "secondi": 0.1}
    risultato_cattivo = Risultato(bs=bs_cattivo, ce={}, prior_bs=None, prior_ce=None,
                                  report=report, struttura=_struttura())
    monkeypatch.setattr(import_snello, "importa", lambda *a, **k: risultato_cattivo)
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Eccezione dopo importa riuscito", create_company=True, sector=1,
        user_id="snello-eccezione-dopo", period_months=12,
    )
    assert result["success"] is True
    assert result["extraction_method"] != "import_snello"
    vr = result["validation_report"]["import_snello"]
    assert vr["esito"] == "ripiego"
    assert vr["fase"] == "eccezione"
    assert vr["errore"] == "InvalidOperation"

    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert persistito["import_snello"]["errore"] == "InvalidOperation"


def test_modo_conti_disattiva_llm_dei_dettagli(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)

    monkeypatch.setattr(import_snello, "importa", lambda *a, **k: _risultato_quadrato(modo="conti"))

    from importers import detail_enrichment as DE
    visti = {}
    def finta_enrich(file_path, current, prior=None, *, fiscal_year=None, ocr_text=None,
                     pagine=None, usa_llm=True):
        visti["pagine"] = pagine
        visti["usa_llm"] = usa_llm
        return current, prior, {"version": "finta", "status": "skipped", "periods": {}}
    monkeypatch.setattr(DE, "enrich_pdf_details", finta_enrich)
    session_factory = _db_in_memoria(monkeypatch)

    pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Modo conti", create_company=True, sector=1,
        user_id="snello-conti", period_months=12,
    )
    assert visti["usa_llm"] is False
    assert visti["pagine"] is None


def test_modo_legge_passa_le_pagine_dei_dettagli_e_llm_attivo(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)

    risultato = _risultato_quadrato(modo="legge")
    attese = risultato.struttura.pagine_dettagli()
    monkeypatch.setattr(import_snello, "importa", lambda *a, **k: risultato)

    from importers import detail_enrichment as DE
    visti = {}
    def finta_enrich(file_path, current, prior=None, *, fiscal_year=None, ocr_text=None,
                     pagine=None, usa_llm=True):
        visti["pagine"] = pagine
        visti["usa_llm"] = usa_llm
        return current, prior, {"version": "finta", "status": "skipped", "periods": {}}
    monkeypatch.setattr(DE, "enrich_pdf_details", finta_enrich)
    session_factory = _db_in_memoria(monkeypatch)

    pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Modo legge", create_company=True, sector=1,
        user_id="snello-legge", period_months=12,
    )
    assert visti["usa_llm"] is True
    assert visti["pagine"] == attese


def test_ocr_source_non_tenta_il_percorso_snello(tmp_path, monkeypatch):
    """Testo da MinerU OCR (route /import/pdf-ocr): la struttura testuale non e'
    affidabile, il percorso snello non si tenta nemmeno. Fixture route A/B che il
    parser deterministico standard_ivcee_parser legge e quadra da solo (come
    tests/test_provenienza_llm.py: nessuna chiave Anthropic necessaria), cosi' il
    resto dell'import puo' completarsi e il validation_report persistito e' leggibile."""
    import types

    from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _vietata(*a, **k):
        raise AssertionError("import_snello.importa chiamato su una fonte OCR")
    monkeypatch.setattr(import_snello, "importa", _vietata)
    session_factory = _db_in_memoria(monkeypatch)

    pdf = tmp_path / "compatta.pdf"
    _write_compact_infrannual_pdf(pdf)
    import fitz
    with fitz.open(str(pdf)) as _doc:
        _testo_reale = "".join(p.get_text() for p in _doc)
    extraction_context = types.SimpleNamespace(
        full_text=_testo_reale, tables=[], mineru_version="test",
        deterministic_text=None, page_texts=[],
    )
    result = pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), fiscal_year=2026, period_months=6,
        company_name="OCR MinerU", create_company=True, sector=1,
        user_id="snello-ocr", extraction_context=extraction_context,
    )
    assert result["validation_report"]["import_snello"] == {
        "esito": "non_applicabile", "motivo": "ocr",
    }
    persistito = _validation_report_persistito(session_factory, result["company_id"], 2026)
    assert persistito["import_snello"] == {"esito": "non_applicabile", "motivo": "ocr"}


def test_scansione_non_tenta_il_percorso_snello(tmp_path, monkeypatch):
    """PDF scansionato (nessun testo estraibile nativo): il percorso snello non si tenta,
    esattamente come per una fonte OCR MinerU. Il testo OCR di instradamento e l'estrazione
    deterministica sono sostituiti con finte: la scansione reale (RapidOCR) non serve a
    isolare SOLO il comportamento del cancello is_scanned."""
    import fitz

    from importers import situazione_contabile_parser as SC

    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _vietata(*a, **k):
        raise AssertionError("import_snello.importa chiamato su una scansione")
    monkeypatch.setattr(import_snello, "importa", _vietata)

    monkeypatch.setattr(SC, "ocr_bilancio_verifica_segno_sample_text",
                        lambda *a, **k: "\n".join(RIGHE_PAREGGIO))

    bs_ocr = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("1000"),
             "totale_attivo": D("1000"), "totale_passivo": D("1000")}
    monkeypatch.setattr(SC, "extract_situazione_contabile",
                        lambda *a, **k: (dict(bs_ocr), {}, None, None))

    session_factory = _db_in_memoria(monkeypatch)

    pdf_path = tmp_path / "scansione.pdf"
    doc = fitz.open()
    doc.new_page()  # pagina vuota: nessun testo nativo estraibile -> is_scanned=True
    doc.save(str(pdf_path))
    doc.close()

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf_path), fiscal_year=2025,
        company_name="Scansione senza snello", create_company=True, sector=1,
        user_id="snello-scansione", period_months=12,
    )
    assert result["validation_report"]["import_snello"] == {
        "esito": "non_applicabile", "motivo": "scansione",
    }
    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert persistito["import_snello"] == {"esito": "non_applicabile", "motivo": "scansione"}


@pytest.mark.parametrize("valore_motore", [None, "altro", ""])
def test_interruttore_non_snello_e_byte_identico_a_oggi(tmp_path, monkeypatch, valore_motore):
    """IMPORT_MOTORE assente o su un valore diverso da 'snello': l'esito deve essere
    identico, campo per campo (tranne i tempi), a un import che non conosce affatto
    l'interruttore — la garanzia esplicita del controllo (requisito 3)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _vietata(*a, **k):
        raise AssertionError("import_snello.importa chiamato senza IMPORT_MOTORE=snello")
    monkeypatch.setattr(import_snello, "importa", _vietata)

    _CHIAVI_TEMPO = {"extraction_time_seconds", "company_id", "balance_sheet_id",
                     "income_statement_id", "source_sha256"}

    def _esegui():
        _db_in_memoria(monkeypatch)
        return pdf_importer.import_pdf_balance_sheet(
            file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
            company_name="Confronto byte-identico", create_company=True, sector=1,
            user_id="snello-confronto", period_months=12,
        )

    monkeypatch.delenv("IMPORT_MOTORE", raising=False)
    riferimento = _esegui()

    if valore_motore is None:
        monkeypatch.delenv("IMPORT_MOTORE", raising=False)
    else:
        monkeypatch.setenv("IMPORT_MOTORE", valore_motore)
    confronto = _esegui()

    riferimento_confrontabile = {k: v for k, v in riferimento.items() if k not in _CHIAVI_TEMPO}
    confronto_confrontabile = {k: v for k, v in confronto.items() if k not in _CHIAVI_TEMPO}
    assert confronto_confrontabile == riferimento_confrontabile
    assert "import_snello" not in confronto["validation_report"]


def test_successo_snello_non_rilegge_la_fonte_con_ledger_evidence(tmp_path, monkeypatch):
    # Banco del 2026-09-27: dopo un import snello quadrato in 27 s, extract_source_candidates
    # (ledger_evidence su gx10) ne spendeva altri 560 per una prova che il percorso snello ha
    # gia' fatto. Con un risultato snello adottato la lettura delle fonti non parte.
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)
    monkeypatch.setattr(import_snello, "importa", lambda file_path, **_: _risultato_quadrato())
    from importers import source_reconciliation

    chiamate = []
    def contata(*a, **k):
        chiamate.append(a)
        return []
    monkeypatch.setattr(source_reconciliation, "extract_source_candidates", contata)
    _db_in_memoria(monkeypatch)
    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Snello senza fonti", create_company=True, sector=1,
        user_id="snello-fonti", period_months=12,
    )
    assert result["extraction_method"] == "import_snello"
    assert result["validation_report"]["import_snello"]["esito"] == "ok"
    assert chiamate == []


def _risultato_squadrato(scarto=D("300")):
    """Un esito 'squadrato' con un vero sbilancio attivo/passivo persistito (Task 17): nessun
    tappo, la diagnostica dichiara lo scarto misurato dal percorso snello."""
    bs = {"sp09_disponibilita_liquide": D("1000"), "sp11_capitale": D("1000") - scarto,
          "_plug_residual": D("0"), "_unclassified_mass": D("0")}
    ce = {}
    misura = {"attivo": "1000.00", "passivo": str((D("1000") - scarto).quantize(D("0.01"))),
             "utile_ce": "0.00", "sp13": "0.00", "forma": "bilancio",
             "scarto_sp": str(scarto.quantize(D("0.01"))), "scarto_ce": "0.00",
             "scarto_stampati": "0.00"}
    report = {"esito": "squadrato", "modo": "legge", "struttura": {},
             "misura": {"corrente": misura}, "tappo": {"corrente": None},
             "letture": {"sp": 2, "ce": 1}, "diag": {"lato_irrisolti": []},
             "anomalie": [], "secondi": 0.1}
    return Risultato(bs=bs, ce=ce, prior_bs=None, prior_ce=None, report=report,
                     struttura=_struttura())


def _risultato_squadrato_scarto_stampati():
    """Un esito 'squadrato' dove il foglio ricostruito QUADRA da solo (attivo=passivo, CE=sp13):
    lo scarto sta solo nel confronto coi totali STAMPATI dal documento (scarto_stampati). Un
    mapper.validate_balance ordinario passerebbe qui senza dire nulla - e' esattamente il caso
    per cui l'avviso va dichiarato esplicitamente dal percorso snello (Task 17)."""
    bs = {"sp09_disponibilita_liquide": D("1000"), "sp11_capitale": D("1000"),
          "_plug_residual": D("0"), "_unclassified_mass": D("0")}
    ce = {}
    misura = {"attivo": "1000.00", "passivo": "1000.00", "utile_ce": "0.00", "sp13": "0.00",
             "forma": "bilancio", "scarto_sp": "0.00", "scarto_ce": "0.00",
             "scarto_stampati": "150.00"}
    report = {"esito": "squadrato", "modo": "legge", "struttura": {},
             "misura": {"corrente": misura}, "tappo": {"corrente": None},
             "letture": {"sp": 2, "ce": 1}, "diag": {"lato_irrisolti": []},
             "anomalie": [], "secondi": 0.1}
    return Risultato(bs=bs, ce=ce, prior_bs=None, prior_ce=None, report=report,
                     struttura=_struttura())


def test_squadrato_si_salva_con_avviso_e_blocca_il_previsionale(tmp_path, monkeypatch):
    """Task 17 (decisione del proprietario, 2026-09-27): un esito 'squadrato' non ripiega piu'
    sull'estrattore di oggi. Si adotta con un avviso "BILANCIO SBILANCIATO" che rimanda alle
    Rettifiche, uno stato di validazione 'unbalanced' (mai 'verified') e un previsionale
    bloccato dal verdetto ESISTENTE (check_quadratura sul foglio persistito) - nessun nuovo
    cancello."""
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)
    monkeypatch.setattr(import_snello, "importa", lambda file_path, **_: _risultato_squadrato())
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Squadrato con avviso", create_company=True, sector=1,
        user_id="snello-squadrato", period_months=12,
    )
    assert result["success"] is True
    assert result["extraction_method"] == "import_snello"
    assert result["validation_report"]["import_snello"]["esito"] == "squadrato"
    assert result["validation_status"] == "unbalanced"
    assert result["forecastable"] is False
    assert any(w.startswith(pdf_importer._UNBALANCED_WARNING_PREFIX) for w in result["warnings"])
    assert any("Rettifiche" in w for w in result["warnings"])

    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert persistito["import_snello"]["esito"] == "squadrato"

    from database.models import FinancialYear
    with session_factory() as db:
        fy = db.query(FinancialYear).filter_by(
            company_id=result["company_id"], year=2025).one()
        assert fy.validation_status == "unbalanced"
        assert fy.forecastable is False


def test_squadrato_sui_soli_totali_stampati_dichiara_comunque_l_avviso(tmp_path, monkeypatch):
    """Lo scarto puo' venire dai totali stampati dal documento, non dallo sbilancio del foglio
    ricostruito: l'avviso resta dichiarato anche quando mapper.validate_balance da solo
    tacerebbe (Task 17)."""
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)
    monkeypatch.setattr(import_snello, "importa",
                        lambda file_path, **_: _risultato_squadrato_scarto_stampati())
    _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Squadrato solo su stampati", create_company=True, sector=1,
        user_id="snello-squadrato-stampati", period_months=12,
    )
    assert result["success"] is True
    assert result["validation_report"]["import_snello"]["esito"] == "squadrato"
    assert result["validation_status"] == "unbalanced"
    assert any(w.startswith(pdf_importer._UNBALANCED_WARNING_PREFIX) for w in result["warnings"])


def test_avvisi_del_percorso_snello_senza_duplicati(tmp_path, monkeypatch):
    """Task 25 fix round 1, addizione B(b): lo stesso avviso (p.es. BILANCIO NON QUADRATO) arriva
    da piu' fonti (validate_hierarchy e la quadratura unificata): sul percorso snello ogni avviso
    distinto esce una volta sola."""
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)
    from importers.pdf_mapper import IVCEEMapper
    quadratura = "BILANCIO NON QUADRATO: attivo 5.000,00 != passivo 1.000,00 (sbilancio 4.000,00)"
    originale = IVCEEMapper.validate_hierarchy
    monkeypatch.setattr(IVCEEMapper, "validate_hierarchy",
                        lambda self, bs: list(originale(self, bs)) + [
                            quadratura, "GERARCHIA INCOERENTE: x", quadratura, "GERARCHIA INCOERENTE: x"])
    bs = {"sp09_disponibilita_liquide": D("5000"), "sp11_capitale": D("1000"),
          "_plug_residual": D("0"), "_unclassified_mass": D("0")}
    report = {"esito": "squadrato", "modo": "legge", "struttura": {},
              "misura": {"corrente": {"scarto_sp": "4000.00", "scarto_ce": "0", "scarto_stampati": "0"}},
              "tappo": {"corrente": None}, "letture": {"sp": 1, "ce": 1}, "diag": {"lato_irrisolti": []},
              "anomalie": [], "secondi": 0.1}
    monkeypatch.setattr(import_snello, "importa", lambda *a, **k: Risultato(
        bs=bs, ce={}, prior_bs=None, prior_ce=None, report=report, struttura=_struttura()))
    _db_in_memoria(monkeypatch)
    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025, company_name="Avvisi unici",
        create_company=True, sector=1, user_id="snello-avvisi", period_months=12)
    avvisi = result["warnings"]
    assert len(avvisi) == len(set(avvisi))
    assert avvisi.count(quadratura) == 1
