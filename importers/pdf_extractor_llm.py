"""
PDF Balance Sheet Extractor using PyMuPDF + Claude Haiku 4.5.

Fast alternative to Docling: PyMuPDF extracts text from relevant pages (~100ms),
then Claude Haiku parses IV CEE fields via structured output (~3-5s).
Total: ~5s at ~$0.01/PDF vs Docling's ~133s.

Dal 2026-11-24 il codice sta nel pacchetto importers/estrazione_llm, un modulo per responsabilita';
questo modulo e' la facciata: ri-esporta ogni nome, privati compresi, cosi' chi importa da qui non
cambia. Chi sostituisce una funzione in un test (monkeypatch) la sostituisce nel modulo dove il
chiamante la cerca, non qui.
"""

from importlib import import_module

_MODULI = (
    "modelli",
    "colonne",
    "formati",
    "pagine",
    "celle_vuote",
    "voci_stampate",
    "chiamate",
    "riconciliazioni",
    "totali_dichiarati",
    "coge",
    "ivcee",
)

for _nome in _MODULI:
    _modulo = import_module(f"importers.estrazione_llm.{_nome}")
    globals().update({_k: _v for _k, _v in vars(_modulo).items() if not _k.startswith("__")})
del _nome, _modulo
