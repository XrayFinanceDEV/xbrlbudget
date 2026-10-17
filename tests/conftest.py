"""Impostazioni comuni della suite.

Dal 2026-10-16 i default di produzione sono il percorso snello (``IMPORT_MOTORE`` assente =
snello) e nessun servizio Anthropic (``ANTHROPIC_CONSENTITO`` assente = vietato, tutto su gx10).
La suite e' stata scritta sui default di prima e simula il client Anthropic e l'importatore
classico: qui li si richiama esplicitamente, test per test, cosi' ogni test continua a
descrivere il comportamento che verifica. Un test che vuole i default nuovi toglie le due
variabili con ``monkeypatch.delenv`` (tests/test_default_snello_senza_anthropic.py).
"""
import pytest


@pytest.fixture(autouse=True)
def _default_della_suite(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_CONSENTITO", "1")
    monkeypatch.setenv("IMPORT_MOTORE", "classico")
