"""Il record della probe deve bastare a dire "questo import e' CAMBIATO".

Non basta la quadratura: un bilancio puo' avere sbilancio 0 ed essere classificato
male (massa nel campo sbagliato, fondi non nettati, debiti tutti in "altri"). La
baseline confronta i CAMPI, quindi la probe deve registrarli tutti — come stringhe
Decimal, perche' i confronti su float producono falsi diff da arrotondamento.

Gated su PROBE_SAMPLE_PDF: il corpus Test/ e' gitignorato.
"""
import os

import pytest

from tests._import_probe import probe, sha256_of

SAMPLE = os.environ.get("PROBE_SAMPLE_PDF")

REQUIRED_KEYS = (
    "file", "sha256", "method", "ok", "macro_area", "macro_subcategory",
    "extraction_method", "validation_status", "totale_attivo", "sbilancio",
    "masked", "warnings", "fields",
)


def test_sha256_e_stabile_e_dipende_dal_contenuto(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"contenuto")
    b.write_bytes(b"contenuto")
    assert sha256_of(str(a)) == sha256_of(str(b))
    b.write_bytes(b"contenuto diverso")
    assert sha256_of(str(a)) != sha256_of(str(b))


@pytest.mark.skipif(not SAMPLE, reason="PROBE_SAMPLE_PDF non impostata (corpus locale assente)")
def test_record_contiene_i_campi_necessari_alla_baseline():
    rec = probe(SAMPLE, "standard")
    for k in REQUIRED_KEYS:
        assert k in rec, f"chiave mancante nel record: {k}"
    assert len(rec["sha256"]) == 64


@pytest.mark.skipif(not SAMPLE, reason="PROBE_SAMPLE_PDF non impostata (corpus locale assente)")
def test_gli_importi_sono_stringhe_decimal_mai_float():
    rec = probe(SAMPLE, "standard")
    if not rec["ok"]:
        pytest.skip(f"import non riuscito in questo ambiente: {rec['error']}")
    assert isinstance(rec["fields"], dict) and rec["fields"], "nessun campo registrato"
    for name, value in rec["fields"].items():
        assert isinstance(value, str), f"{name} non e' una stringa Decimal: {value!r}"
    # i campi devono coprire sia SP sia CE
    assert any(k.startswith("sp") for k in rec["fields"])
    assert any(k.startswith("ce") for k in rec["fields"])


@pytest.mark.skipif(not SAMPLE, reason="PROBE_SAMPLE_PDF non impostata (corpus locale assente)")
def test_il_record_e_serializzabile_in_json_senza_default():
    import json
    rec = probe(SAMPLE, "standard")
    json.dumps(rec)          # niente default=str: se serve, ci sono Decimal/oggetti nascosti
