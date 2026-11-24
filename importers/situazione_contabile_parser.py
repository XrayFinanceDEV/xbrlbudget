"""
Deterministic parser for "Situazione Contabile" (trial balance) PDFs.

These PDFs use XX/YY/ZZZ account codes with a *** subtotal hierarchy,
unlike IV CEE formatted PDFs. This parser maps trial balance accounts
to IV CEE sp01-sp18 and ce01-ce20 fields without using an LLM.

Classification is keyword-based (account descriptions), NOT prefix-based,
so it works across different Italian accounting software numbering systems.

Account hierarchy (DEPI format):
  XX/YY/ZZZ  = detail line
  XX/YY/***  = 3rd-level subtotal
  XX/**/***  = 2nd-level subtotal (maps to IV CEE categories)
  ***        = section total (TOTALE ATTIVITA`, TOTALE PASSIVITA`, etc.)
  ****       = UTILE DI ESERCIZIO
  *****      = TOTALE A PAREGGIO

CONGELATO dal 2026-11: i parser per singolo layout di gestionale elencati in
PARSER_DI_LAYOUT accettano solo correzioni di errori; un layout nuovo va nel lettore
(importers/lettore), non qui. tests/test_parser_layout_congelati.py lo fa rispettare.

Dal 2026-11-24 il codice sta nel pacchetto importers/situazione_contabile, un modulo per formato o per
responsabilita'; questo modulo e' la facciata: ri-esporta ogni nome, privati compresi, cosi' chi importa
da qui non cambia. Chi sostituisce una funzione in un test (monkeypatch) la sostituisce nel modulo dove
il chiamante la cerca, non qui.
"""

from importlib import import_module
from typing import Tuple

# Parser di layout congelati (vedi l'intestazione del modulo). Il test ne ricava l'elenco
# dalle funzioni `parse_*`/`extract_*` pubbliche di livello modulo, dispatcher escluso.
PARSER_DI_LAYOUT: Tuple[str, ...] = (
    "parse_entries",
    "parse_entries_ago",
    "parse_entries_single_column",
    "parse_entries_contrapposte_depi",
    "parse_entries_contrapposte_8digit",
    "parse_entries_verifica_ie",
    "parse_entries_verifica_mastri",
    "parse_entries_verifica_sub_mastro",
    "parse_entries_verifica_sezbil",
    "parse_entries_teamsystem",
    "parse_bilancio_verifica_segno",
    "extract_contrapposte_best_effort",
)

_MODULI = (
    "fondi",
    "comune",
    "depi",
    "regole",
    "iv_cee",
    "ago",
    "colonna_unica",
    "contrapposte_8cifre",
    "verifica_ie",
    "verifica_mastri",
    "verifica_sub_mastro",
    "verifica_sezbil",
    "teamsystem",
    "best_effort",
    "mastri_gerarchici",
    "contra",
    "ricostruzione",
    "classificatori",
    "best_effort_estrazione",
    "vision",
    "verifica_segno",
    "dispatcher",
)

for _nome in _MODULI:
    _modulo = import_module(f"importers.situazione_contabile.{_nome}")
    globals().update({_k: _v for _k, _v in vars(_modulo).items() if not _k.startswith("__")})
del _nome, _modulo
