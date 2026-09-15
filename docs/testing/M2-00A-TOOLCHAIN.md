# M2-00A — verifica toolchain Typst

Verifica locale del 2026-09-15 sulla base M1 `12ecfb7`.
Implementazione pronta per review; questo verbale non costituisce approvazione
del gate M2-00 o una review indipendente Pi-B.

La toolchain pinata è Typst `0.15.1`, asset Linux x86_64 musl, SHA-256
`a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c`.
Il digest è stato confrontato con il campo `digest` dell'asset nella
[release ufficiale](https://github.com/typst/typst/releases/tag/v0.15.1),
consultabile anche via API GitHub `/repos/typst/typst/releases/tags/v0.15.1`.

Verifiche eseguite:

- Gate backend mirato: **71 passed**, un warning preesistente
  `python_multipart`, nei test toolchain, fixture spike e contratto M1.
- Installazione reale da rete in una directory temporanea vuota con
  `TYPST_TOOL_ROOT`, usando manifesto e script di produzione.
- Verifica offline della provenienza, checksum e versione installata:
  `typst 0.15.1 (9dfd3a08)`.
- SHA-256 del binario ricreato identica a quella dell'installazione esistente:
  `29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237`.
- Compilazione minima A4 in italiano con un importo negativo: PDF di 11.128 byte,
  firma `%PDF-` verificata. Il campione temporaneo è stato eliminato.
- Test di checksum alterato, versione errata, membri tar non sicuri, provenienza
  mancante o malformata, URL divergente, chiavi duplicate o sconosciute e binario
  modificato. Il marker del binario finto verifica il rifiuto prima di eseguirlo.
- Reinstallazione con archivio alterato: binario e provenienza precedenti
  conservati, directory scratch ripulita, verifica successiva riuscita.

Comando ripetibile del gate mirato:

```bash
GATE_PYTHON=/percorso/al/python/backend bash scripts/verify_report_gate.sh backend \
  tests/test_typst_toolchain.py \
  tests/test_m2_00_spike_fixtures.py \
  tests/test_final_report_contract.py
```

Installazione e verifica sono documentate in
[`tools/typst/README.md`](../../tools/typst/README.md).
Le fixture sintetiche 1/3/5 anni sono documentate in
[`tools/typst/spike/README.md`](../../tools/typst/spike/README.md).
La prova minima conferma la toolchain; le misure e il confronto grafico del gate
M2-00 richiedono lo spike completo prima di introdurre il renderer di produzione.
