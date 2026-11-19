"""Un nome d'azienda fuori schema non deve mai più far sparire la lista aziende.

Il difetto (2026-11-19, produzione): l'import XBRL prendeva come ragione sociale il
primo tag il cui nome conteneva «name» — «AccantoNAMEnti...», «...CoordiNAMEnto» — e
salvava un paragrafo HTML della nota integrativa di quasi 600 caratteri in
`Company.name`. SQLite non controlla `String(255)`, lo schema di risposta sì: da quel
giorno `GET /companies` rispondeva 500 e l'utente non vedeva più nessuna azienda; le
ricreava e riceveva 400 per partita IVA già usata.

Tutti i dati qui sono inventati.
"""
import pytest
from fastapi.testclient import TestClient
from lxml import etree

from importers.nome_azienda import (
    NOME_AZIENDA_MAX,
    denominazione_xbrl,
    nome_azienda_pulito,
    tax_id_pulito,
)

PARAGRAFO_HTML = (
    '<h3 style="text-align: justify;"><span style="font-family: arial;">'
    "<strong>Informazioni sulla societa che esercita l&rsquo;attivita di direzione e "
    "coordinamento</strong></span></h3><p>La societa non e soggetta a direzione o "
    "coordinamento.&nbsp;</p>" * 3
)

XBRL = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:itcc-ci="http://www.infocamere.it/itnn/fr/itcc/ci/2018-11-04">
  <xbrli:context id="c1">
    <xbrli:entity><xbrli:identifier scheme="http://www.infocamere.it">99999999999</xbrli:identifier></xbrli:entity>
  </xbrli:context>
  <itcc-ci:AccantonamentiRischi contextRef="c1">1</itcc-ci:AccantonamentiRischi>
  <itcc-ci:IntroduzioneBilancioSocietaEsercitaAttivitaDirezioneCoordinamento contextRef="c1"><![CDATA[{PARAGRAFO_HTML}]]></itcc-ci:IntroduzioneBilancioSocietaEsercitaAttivitaDirezioneCoordinamento>
  <itcc-ci:DatiAnagraficiDenominazione contextRef="c1">  Azienda   di Prova &amp; C. SRL </itcc-ci:DatiAnagraficiDenominazione>
</xbrli:xbrl>"""


def _root(testo):
    return etree.fromstring(testo.encode())


# --- estrazione dal documento ------------------------------------------------

def test_la_ragione_sociale_si_legge_dal_tag_esatto_non_dal_primo_che_contiene_name():
    assert denominazione_xbrl(_root(XBRL)) == "Azienda di Prova & C. SRL"


def test_senza_tag_di_denominazione_nessun_nome_mai_il_testo_di_un_altro_tag():
    senza = XBRL.replace("DatiAnagraficiDenominazione", "DatiAnagraficiSede")
    assert denominazione_xbrl(_root(senza)) is None


@pytest.mark.parametrize("modulo", ["importers.xbrl_parser_enhanced", "importers.xbrl_parser"])
def test_i_due_parser_xbrl_usano_la_ragione_sociale(modulo, tmp_path):
    import importlib

    mod = importlib.import_module(modulo)
    classe = mod.EnhancedXBRLParser if modulo.endswith("enhanced") else mod.XBRLParser
    parser = classe.__new__(classe)  # extract_entity_info non usa lo stato dell'istanza
    info = parser.extract_entity_info(_root(XBRL))
    assert info["name"] == "Azienda di Prova & C. SRL"
    assert info["tax_id"] == "99999999999"


# --- pulizia ---------------------------------------------------------------------

def test_un_nome_html_esce_senza_tag_e_entro_i_255_caratteri():
    nome = nome_azienda_pulito(PARAGRAFO_HTML)
    assert "<" not in nome and "&rsquo;" not in nome
    assert len(nome) <= NOME_AZIENDA_MAX


@pytest.mark.parametrize("vuoto", [None, "", "   ", "<p>&nbsp;</p>"])
def test_un_nome_vuoto_diventa_none(vuoto):
    assert nome_azienda_pulito(vuoto) is None


@pytest.mark.parametrize("valore, atteso", [
    (" 01234567890 ", "01234567890"),
    ("RSSMRA80A01H501U", "RSSMRA80A01H501U"),
    ("CODICE-DEL-GESTIONALE-0001", None),  # oltre 20: scartato, mai troncato
    ("", None),
    (None, None),
])
def test_tax_id(valore, atteso):
    assert tax_id_pulito(valore) == atteso


# --- la lista aziende regge una riga già salvata fuori schema ---------------------

@pytest.fixture()
def client_e_sessione(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.app.main import app
    from app.core import database as core_db
    from app.core.config import settings
    from database.db import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[core_db.get_db] = override_get_db
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(settings, "DEV_USER_ID", "utente-prova")
    with TestClient(app, raise_server_exceptions=False) as c:
        try:
            yield c, sessions
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize("url", ["/api/v1/companies", "/api/v1/companies?include=scenarios"])
def test_una_riga_fuori_schema_non_fa_sparire_la_lista(client_e_sessione, url):
    from database.models import Company

    c, sessions = client_e_sessione
    db = sessions()
    db.add_all([
        Company(user_id="utente-prova", name="Azienda Buona SRL", tax_id="01234567890", sector=1),
        Company(user_id="utente-prova", name=PARAGRAFO_HTML, tax_id="CODICE-DEL-GESTIONALE-0001", sector=1),
    ])
    db.commit()
    db.close()

    r = c.get(url)
    assert r.status_code == 200, r.text
    assert {a["name"] for a in r.json()} >= {"Azienda Buona SRL"}
    assert len(r.json()) == 2  # anche la riga anomala resta visibile, per rinominarla


def test_la_creazione_continua_a_rifiutare_un_nome_troppo_lungo(client_e_sessione):
    c, _ = client_e_sessione
    r = c.post("/api/v1/companies", json={"name": "x" * 256, "sector": 1})
    assert r.status_code == 422
