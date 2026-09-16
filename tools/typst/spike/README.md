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
il controllo delle licenze e la decisione tecnica sono registrati nel
[verbale M2-00](../../../docs/testing/M2-00-TYPST-SPIKE.md).

## Ripetere il confronto

Da Linux x86_64, con Python 3.12 e dipendenze backend, Bash, `unshare`,
`/usr/bin/time` e Poppler (`pdftotext`, `pdffonts`):

```bash
bash tools/typst/install.sh
python3 -m tools.typst.spike.packages --download
python3 -m tools.typst.spike.run
python3 -m tools.typst.spike.probes
python3 -m tools.typst.spike.preview
python3 -m tools.typst.spike.comparison
```

Solo i primi due comandi richiedono rete. `run` e `probes` ricontrollano gli
SHA-256 degli archivi e li estraggono nuovamente nella cache ignorata, prima
di compilare in namespace Linux senza rete. Se gli user/network namespace
non sono disponibili, il confronto si ferma; non esegue una prova online.

`packages.json` fissa CeTZ-Plot, CeTZ, oxifmt e Primaviz. I digest sono misurati
sugli archivi del registry ufficiale e non sono firme del produttore. La cache
include il WASM upstream di CeTZ, coperto dal digest dell'archivio; non viene
aggiunto a git. Il report native non usa alcun pacchetto. I font Libertinus
Serif sono quelli incorporati nel compilatore pinato; `--ignore-system-fonts`
evita dipendenze dalla macchina. L'HTML usa font di sistema e non scarica asset.

Output rigenerabili in `tools/typst/spike/output/` (ignorata da git):

- `results.json`: 36 compilazioni report (3 candidati × 3 percorsi × 2 stati ×
  2 palette), sei ripetizioni, due prove PDF/A-2u e un controllo negativo di rete;
- `probes.json`, `probes/`: otto grafici isolati per candidato, relativi PDF e SVG;
- `report-finale-anteprima.html`: anteprima editoriale con 12 PDF native incorporati;
- `confronto-renderer.html`: risultati e grafici reali del confronto.

Il tempo comprende avvio del namespace e processo. “Prima/ripetuta” distingue
processi nuovi, non una cache OS realmente fredda. JSON, template e timestamp PDF
sono fissati per rendere ripetibile l'artefatto. Il renderer dello spike non è il
runtime di produzione M2-01 né il template definitivo M2-02.

Test semantici (offline, installare prima toolchain e Poppler):

```bash
python3 -m pytest tests/test_m2_00_spike.py tests/test_m2_00_spike_fixtures.py -q
```

Il test rimuove davvero un titolo dal corpo PDF: la presenza dello stesso titolo
nell'indice non basta. Altri controlli verificano valori, watermark, firma, A4,
font incorporati, assenza di raster e rifiuto di archivi dei pacchetti alterati.
