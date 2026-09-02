# Production Configuration — NON CORRENTE

> **NON CORRENTE.** Questa pagina diceva che il backend di produzione sta su un host e una
> porta propri, e che il frontend va puntato lì con `NEXT_PUBLIC_API_URL`. Non è più vero
> in nessuna delle due metà: quell'host non risponde, e in produzione la variabile è
> **vuota di proposito** — frontend e backend stanno dietro lo stesso nginx e l'app usa
> l'URL relativo `/api/v1`.
>
> La configurazione di produzione reale è descritta in
> → **[DEPLOY-JENKINS-DOCKER.md](DEPLOY-JENKINS-DOCKER.md)**.

Il testo originale è stato rimosso invece che corretto perché la sua premessa — un backend
raggiungibile a un indirizzo pubblico diverso da quello del frontend, con CORS da aprire
verso il dominio Netlify — non descrive più nulla di esistente. La versione integrale resta
in git.

Le variabili che oggi contano davvero (`SUPABASE_JWT_SECRET`, `ANTHROPIC_API_KEY`,
`ADMIN_API_KEY`, `PARENT_ORIGIN`, `ALLOWED_ORIGINS`, `MAX_COMPANIES_PER_USER`, `PORT`) sono
generate da Jenkins in `.env.docker`: vedi la guida corrente e
[IFRAME_INTEGRATION.md](IFRAME_INTEGRATION.md).
