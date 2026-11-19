"""
Nome dell'azienda letto da un documento importato.

Il nome finisce in `Company.name` (String(255)), che SQLite non controlla: un nome
troppo lungo o vuoto si salva senza errore e poi fa rispondere 500 a
`GET /companies`, dove lo schema di risposta lo rifiuta — l'intera lista
dell'utente sparisce per una riga sola. Ogni importer che crea un'azienda passa
da qui.

La ragione sociale di un XBRL si cerca per nome di tag **esatto**. La vecchia
ricerca per sottostringa (`'name' in tag`) prendeva il primo tag che conteneva
quelle lettere: «AccantoNAMEnti...», «...DirezioneCoordiNAMEnto», cioè un
importo o un paragrafo HTML della nota integrativa al posto del nome.
"""
from __future__ import annotations

import html
import re
from typing import Iterable, Optional

from lxml import etree

NOME_AZIENDA_MAX = 255  # come Company.name e lo schema CompanyBase

# Tag della tassonomia itcc-ci che portano la ragione sociale, in ordine di preferenza.
TAG_DENOMINAZIONE = (
    "DatiAnagraficiDenominazione",
    "DatiAnagraficiRagioneSociale",
)

_TAG_HTML = re.compile(r"<[^>]+>")
_SPAZI = re.compile(r"\s+")


def nome_azienda_pulito(testo: Optional[str]) -> Optional[str]:
    """Il nome come si può salvare: senza HTML, spazi compattati, al massimo
    `NOME_AZIENDA_MAX` caratteri. `None` se non resta nulla."""
    if not testo:
        return None
    pulito = _TAG_HTML.sub(" ", testo)
    pulito = html.unescape(pulito)
    pulito = _SPAZI.sub(" ", pulito).strip()
    if not pulito:
        return None
    if len(pulito) > NOME_AZIENDA_MAX:
        pulito = pulito[:NOME_AZIENDA_MAX].rstrip()
    return pulito


def denominazione_xbrl(root: etree._Element, tag: Iterable[str] = TAG_DENOMINAZIONE) -> Optional[str]:
    """La ragione sociale di un XBRL, cercata per nome di tag esatto.

    `None` se il documento non la dichiara: il chiamante usa il proprio nome di
    ripiego, mai il testo di un altro tag."""
    trovati: dict[str, str] = {}
    preferiti = tuple(tag)
    for elem in root.iter():
        if not isinstance(elem.tag, str):
            continue  # commenti, processing instruction
        nome_tag = etree.QName(elem).localname
        if nome_tag in preferiti and nome_tag not in trovati:
            nome = nome_azienda_pulito(elem.text)
            if nome:
                trovati[nome_tag] = nome
                if nome_tag == preferiti[0]:
                    break
    for nome_tag in preferiti:
        if nome_tag in trovati:
            return trovati[nome_tag]
    return None


TAX_ID_MAX = 20  # come Company.tax_id e lo schema CompanyBase


def tax_id_pulito(testo: Optional[str]) -> Optional[str]:
    """Il codice fiscale / partita IVA come si può salvare, o `None`.

    Un identificativo oltre i 20 caratteri non è un codice fiscale (l'identifier
    del context XBRL può essere un codice del gestionale): si scarta, non si
    tronca — un codice troncato sembrerebbe vero e collegherebbe aziende diverse."""
    if not testo:
        return None
    pulito = testo.strip()
    if not pulito or len(pulito) > TAX_ID_MAX:
        return None
    return pulito
