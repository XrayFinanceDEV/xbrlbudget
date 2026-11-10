#!/usr/bin/env bash
# Collega al repo la cartella dei dati locali, che sta fuori da git (PDF e cifre dei clienti,
# aree di lavoro SDD). Da lanciare una volta dopo il clone, o dopo aver spostato la cartella.
#
#   scripts/collega_corpus.sh [cartella]     # default: $BUDGET_CORPUS, altrimenti ../budget-corpus
#
# Crea nel repo quattro collegamenti, tutti ignorati da git:
#   Test         -> <cartella>/corpus        (lotti di PDF, verità, giri di punteggio)
#   .superpowers -> <cartella>/superpowers   (aree di lavoro SDD: rapporti con cifre dei clienti)
#   inbox        -> <cartella>/inbox
#   tests/debug  -> <cartella>/debug-test
# Non sovrascrive mai una cartella vera: se ne trova una, si ferma.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATI="${1:-${BUDGET_CORPUS:-$REPO/../budget-corpus}}"
DATI="$(cd "$DATI" && pwd)"
collega() {  # $1 = percorso nel repo, $2 = sottocartella dei dati
  local dove="$REPO/$1" verso="$DATI/$2"
  [ -d "$verso" ] || { echo "manca $verso: salto $1"; return; }
  if [ -L "$dove" ]; then rm "$dove"
  elif [ -e "$dove" ]; then echo "ERRORE: $dove esiste e non è un collegamento, non lo tocco"; exit 1; fi
  ln -s "$verso" "$dove"
  echo "$1 -> $verso"
}
collega Test corpus
collega .superpowers superpowers
collega inbox inbox
collega tests/debug debug-test
