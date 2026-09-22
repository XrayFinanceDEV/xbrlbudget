# Importazione con macrovoci incomplete

Questa correzione sostituisce la regola bloccante descritta in
[analisi iniziale delle macrovoci](2026-09-21-analisi-iniziale-macrovoci.md).
La lettura incompleta delle macrovoci non deve impedire l'importazione.

Sul «Bilancio di verifica al 30.06.2026.pdf» di Ambienta il lettore restituiva
voci con `cells: []`: la validazione della risposta generava un errore e
l'importazione terminava prima dell'estrazione alternativa.

Ora una risposta strutturata errata può usare il tentativo correttivo già
previsto. Se l'analisi resta incompleta, l'importatore prosegue con il lettore
alternativo e conserva la diagnosi in `macro_analysis`, con `fallback_used`.
La diagnosi incompleta non viene scambiata per una verifica della fonte riuscita.

La chiusura dei dettagli assegna la quota non classificata ai conti residuali
della famiglia: per esempio, debiti totali 50 e debiti bancari identificati 20
producono altri debiti 30. Il totale della famiglia resta invariato. Restano
visibili gli eventuali conflitti fra totali e dettagli, senza impedire il
salvataggio del bilancio solo perché la lettura delle macrovoci è incompleta.

Verifiche: 144 test su lettura macro, chiusura dei residui, arricchimento,
riconciliazione e importazioni sbilanciate, inclusi salvataggio di
corrente/comparativo e fallback verso altri debiti. Prova reale con il
lettore LLM e SQLite in memoria: Ambienta viene importato. La prova evidenzia
ancora uno scarto SP di 1 euro e un conflitto nei dettagli dei crediti a lungo
di 3.825 euro, segnalati per revisione. Il successo dell'importazione non
certifica quindi la correttezza di ogni classificazione. Nessuna modifica ai
bilanci salvati dell'utente durante le prove.
