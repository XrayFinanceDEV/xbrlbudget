# Fixture dello spike M2-00

`fixtures.py` prepara tre `FinalReportModel` sintetici per confrontare primitive
native, CeTZ-Plot e Primaviz con la toolchain fissata da M2-00A.
I JSON canonici M1 vengono letti senza modificarli. Ogni modello restituito
passa la validazione ordinaria del contratto, inclusi hash del modello e fonti.

| Fixture | Percorso | Anni previsionali |
|---|---|---|
| `bilancio` | annuale | 1 |
| `infrannuale` | infrannuale | 3 |
| `startup` | startup | 5 |

Le fixture includono sei grafici, importi decimali, valori negativi, zeri e null,
denominazioni lunghe, 18 rettifiche, sei prestiti e otto differenze temporanee.
Sono dati di stress tipografico e non esempi di coerenza contabile. La soglia DSCR
di `1.00` resta nel metadata del harness, fuori dal contratto API.

Per esportare gli snapshot in una directory temporanea, dalla radice del repo:

```bash
python3 - <<'PY'
import json
import tempfile
from pathlib import Path
from tools.typst.spike.fixtures import (
    SPIKE_FIXTURE_MANIFEST, build_all_spike_fixtures,
)

output = Path(tempfile.mkdtemp(prefix="typst-spike-fixtures-"))
for name, model in build_all_spike_fixtures().items():
    (output / f"{name}.json").write_text(
        model.model_dump_json(indent=2), encoding="utf-8",
    )
(output / "manifest.json").write_text(
    json.dumps(SPIKE_FIXTURE_MANIFEST, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(output)
PY
```

Usare un Python con le dipendenze backend installate. I test offline sono in
`tests/test_m2_00_spike_fixtures.py`. Il confronto dei renderer, le misure,
il controllo delle licenze e la decisione del gate M2-00 restano da eseguire.
