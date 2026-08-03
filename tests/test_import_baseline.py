"""Gate di regressione degli import, versionato e riproducibile.

Perche' esiste: `Test/` e' gitignorato, quindi i valori pre-fix non erano
versionati e il "gate di regressione" dei piani era una checklist manuale, non
riproducibile da un secondo sviluppatore. Qui i NUMERI (non i PDF) entrano nel
repo, indicizzati per sha256 del documento.

Due livelli, deliberatamente distinti:
  verified=False -> "questo e' cio' che il software produce OGGI". Intercetta i
                    CAMBI (regressioni o miglioramenti). Non afferma che sia giusto.
  verified=True  -> "questo e' il numero LETTO SULLA FONTE da un umano".
                    E' un'asserzione di correttezza: un cambio e' SEMPRE un errore.

Il test skippa i file non presenti in locale, quindi non rompe la CI.
"""
import glob
import json
import os

import pytest

BASELINE = os.path.join(os.path.dirname(__file__), "fixtures", "import_baseline.json")
CORPUS = os.environ.get("IMPORT_CORPUS_ROOT")

# Confronti che valgono per ogni entry, oltre ai singoli campi contabili.
TOP_LEVEL_KEYS = ("ok", "macro_area", "macro_subcategory", "totale_attivo",
                  "sbilancio", "masked", "validation_status")


def load_baseline() -> dict:
    if not os.path.exists(BASELINE):
        return {}
    with open(BASELINE, encoding="utf-8") as fh:
        return json.load(fh)


def test_la_baseline_e_ben_formata():
    base = load_baseline()
    assert base, "baseline vuota: generarla con scripts/refresh_import_baseline.py"
    for h, entry in base.items():
        assert len(h) == 64, f"chiave non e' uno sha256: {h!r}"
        assert "file" in entry and "expected" in entry and "verified" in entry, h
        assert isinstance(entry["verified"], bool), h
        if entry["verified"]:
            assert entry.get("verified_note"), (
                f"{entry['file']}: verified=True richiede verified_note "
                f"(dove hai letto il numero sulla fonte)")


def test_la_baseline_non_congela_errori_di_ambiente():
    """Un fallimento per crediti esauriti / chiave assente / MinerU spento e' un
    fatto dell'ambiente, non un comportamento atteso del software."""
    from scripts.refresh_import_baseline import is_environmental
    for entry in load_baseline().values():
        err = (entry["expected"] or {}).get("error") or ""
        assert not is_environmental(err), f"{entry['file']}: errore d'ambiente in baseline: {err[:80]}"


def _index_corpus():
    from tests._import_probe import sha256_of
    out = {}
    for p in glob.glob(os.path.join(CORPUS, "**", "*.pdf"), recursive=True):
        out.setdefault(sha256_of(p), p)
    return out


@pytest.mark.skipif(not CORPUS, reason="IMPORT_CORPUS_ROOT non impostata (Test/ e' gitignorato)")
def test_nessuna_regressione_sui_file_di_baseline():
    from tests._import_probe import probe
    base = load_baseline()
    by_hash = _index_corpus()

    diffs, checked = [], 0
    for h, entry in base.items():
        path = by_hash.get(h)
        if path is None:
            continue                                  # non presente in locale
        checked += 1
        got = probe(path, entry["expected"].get("method", "standard"))
        exp = entry["expected"]
        for k in TOP_LEVEL_KEYS:
            if str(got.get(k)) != str(exp.get(k)):
                diffs.append((entry["file"], k, exp.get(k), got.get(k), entry["verified"]))
        exp_fields = exp.get("fields") or {}
        got_fields = got.get("fields") or {}
        for name in sorted(set(exp_fields) | set(got_fields)):
            if exp_fields.get(name) != got_fields.get(name):
                diffs.append((entry["file"], name, exp_fields.get(name),
                              got_fields.get(name), entry["verified"]))

    if not checked:
        pytest.skip("nessun file della baseline presente in locale")

    hard = [d for d in diffs if d[4]]
    assert not hard, (
        "REGRESSIONE su valori VERIFICATI SULLA FONTE (non negoziabile):\n  "
        + "\n  ".join(f"{f}: {k} atteso={e!r} ottenuto={g!r}" for f, k, e, g, _ in hard))
    assert not diffs, (
        "differenze rispetto alla baseline osservata. Se sono attese, aggiornarla "
        "esplicitamente (scripts/refresh_import_baseline.py) motivando nel commit:\n  "
        + "\n  ".join(f"{f}: {k} prima={e!r} ora={g!r}" for f, k, e, g, _ in diffs[:40]))
