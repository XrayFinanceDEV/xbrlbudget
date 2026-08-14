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


def current_config() -> str:
    """La configurazione in cui stiamo confrontando: "llm" o "no-llm".

    Deve corrispondere a `refresh_import_baseline._config_tag()`. Sulla rotta C il
    risultato DIPENDE dalla chiave: con la chiave gira prima l'estrattore CoGe-LLM e
    la selezione per completezza puo' scegliere un candidato diverso. Un'entry
    registrata senza chiave e confrontata con la chiave (o viceversa) non e' una
    regressione: e' un confronto fra due software diversi.
    """
    from tests._import_probe import _load_env
    _load_env()
    return "llm" if os.environ.get("ANTHROPIC_API_KEY") else "no-llm"


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


# NOTA per chi imposta IMPORT_CORPUS_ROOT per la prima volta (2026-08-14).
#
# Il confronto e' filtrato per CONFIGURAZIONE. Le 17 entry storiche portano
# `config: "no-llm"`: furono registrate senza chiave API, dove sulla rotta C
# l'estrattore CoGe-LLM non esiste affatto e certi file falliscono. Questo progetto
# gira solo CON la chiave, quindi quelle entry non sono un riferimento valido e
# vengono SALTATE, non confrontate — il test stampa quante ne salta. Vanno
# rigenerate sulla macchina che ha il corpus `Test/`:
#     ANTHROPIC_API_KEY=... python scripts/refresh_import_baseline.py <corpus>
# Finche' non succede, quei 17 file non sono coperti da alcuna regressione.
#
# Questo filtro nasce da un caso concreto: `budget_342` risultava "divergente"
# solo perche' la sua attesa era stata registrata senza chiave (import fallito,
# valori null) e veniva confrontata con la chiave (importa, attivo 1.177.498,89).
# Tre prove indipendenti mostrarono che non era una regressione del riscatto
# vision: il riscatto su quel file non logga nulla (non si innesca), stubbando
# `_apply_vision_rescue` l'output e' bit-identico, e il commit 36934ca — anteriore
# a tutto il lavoro vision — produce gia' gli stessi numeri. Era un confronto fra
# due configurazioni, non fra due versioni del software.
#
# CRITERIO DI AMMISSIONE: in baseline ci va solo cio' che si RIPRODUCE. Un valore
# esatto non puo' descrivere un estrattore stocastico, e congelarne una esecuzione
# rende la suite intermittente — cioe' peggio che non coprire quel file, perche'
# un rosso che capita a caso smette di essere letto. Tre file sono stati esclusi di
# proposito dopo averlo misurato, non perche' il confronto desse fastidio:
#   - `budget_623`: la trascrizione vision e' stocastica sulla colonna del passivo
#     (sbilancio misurato 0,00 / 9.079,77 / 139.079,77 su sei esecuzioni);
#   - `budget_402` e `Bilancio_Riclassificato DEF`: rotta A/B, estrazione IV-CEE via
#     LLM. Registrati e ri-eseguiti a distanza di minuti SENZA cambiare una riga di
#     codice, gia' divergevano (ce14 5,83 -> 0,58; sp16g 29.344,22 -> 29.352,22).
#   - `Bilancino 31-5-26`: rotta C con candidato CoGe-LLM. Registrato come import
#     FALLITO, alla riesecuzione importava (attivo 1.821.262,15): non oscilla di
#     qualche centesimo, oscilla fra "si apre" e "non si apre".
# Per questi file il riferimento utile e' la quadratura, non il centesimo: se ne
# occupano `Test/_quadratura_harness.py` e i test mirati, non questa baseline.
#
# Conseguenza da tenere presente prima di fidarsi del verde: in configurazione
# "llm" questa baseline copre SEI file. Tutto cio' che passa da un LLM — rotta A/B
# per intero, e la rotta C quando vince il candidato CoGe — non e' fissabile al
# valore esatto, per costruzione. Questo gate protegge le rotte deterministiche.
@pytest.mark.skipif(not CORPUS, reason="IMPORT_CORPUS_ROOT non impostata (Test/ e' gitignorato)")
def test_nessuna_regressione_sui_file_di_baseline():
    from tests._import_probe import probe
    base = load_baseline()
    by_hash = _index_corpus()

    config = current_config()
    diffs, checked, other_config = [], 0, 0
    for h, entry in base.items():
        path = by_hash.get(h)
        if path is None:
            continue                                  # non presente in locale
        if entry.get("config", "no-llm") != config:
            other_config += 1                         # registrata in un'altra config
            continue
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

    if other_config:
        print(f"\n[baseline] {other_config} entry saltate: registrate in un'altra "
              f"configurazione (qui gira '{config}'). Vanno rigenerate — vedi la NOTA "
              f"in cima a questo test.")
    if not checked:
        pytest.skip(f"nessun file della baseline in config '{config}' presente in locale "
                    f"({other_config} presenti ma registrati in un'altra configurazione)")

    hard = [d for d in diffs if d[4]]
    assert not hard, (
        "REGRESSIONE su valori VERIFICATI SULLA FONTE (non negoziabile):\n  "
        + "\n  ".join(f"{f}: {k} atteso={e!r} ottenuto={g!r}" for f, k, e, g, _ in hard))
    assert not diffs, (
        "differenze rispetto alla baseline osservata. Se sono attese, aggiornarla "
        "esplicitamente (scripts/refresh_import_baseline.py) motivando nel commit:\n  "
        + "\n  ".join(f"{f}: {k} prima={e!r} ora={g!r}" for f, k, e, g, _ in diffs[:40]))
