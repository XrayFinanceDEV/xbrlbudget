# Deployment Summary — NON CORRENTE

> **NON CORRENTE.** Questa pagina riassumeva il deploy **Netlify** (frontend su Netlify,
> backend su un host dedicato con porta non standard). Quel percorso non esiste più:
> l'host e la porta che indicava non rispondono, e chi seguiva questa pagina configurava
> un frontend puntato su un backend morto.
>
> Il deploy reale è **Jenkins + Docker + nginx**, e in produzione `NEXT_PUBLIC_API_URL`
> è vuota di proposito (URL relativi dietro nginx):
> → **[DEPLOY-JENKINS-DOCKER.md](DEPLOY-JENKINS-DOCKER.md)**.

Il testo originale non è stato corretto ma rimosso, perché era sbagliato su ogni punto che
contava: l'URL del backend, la porta, la posizione di `netlify.toml` (sta nella radice del
repository, non in `frontend/`) e la lista CORS del backend, che non contiene il wildcard
`https://*.netlify.app` che questa pagina dichiarava aggiunto. La versione integrale resta
in git.

Se cerchi la procedura Netlify come tale, sta ancora in
[README_DEPLOYMENT.md](README_DEPLOYMENT.md) e [NETLIFY_CHECKLIST.md](NETLIFY_CHECKLIST.md),
anch'esse marcate non correnti.
