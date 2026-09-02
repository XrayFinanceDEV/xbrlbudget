"""La configurazione e le guide di deployment devono descrivere il deploy che c'è davvero.

Il deploy reale è Jenkins + Docker + nginx (`Jenkinsfile`, `docker-compose.yml`,
`nginx/default.conf`): il frontend è servito dietro nginx e parla col backend per
**URL relativi**, perché `Dockerfile.frontend` costruisce l'immagine con
`NEXT_PUBLIC_API_URL=""` e `frontend/lib/api.ts` cade sul ramo `/api/v1`.

Il vecchio percorso Netlify — frontend su Netlify, backend su
`kpsfinanciallab.w3pro.it:8001` — non esiste più: quell'host e quella porta non
rispondono. Chi copiava `.env.example` o seguiva le guide configurava un backend
morto. Questo test è la rete che impedisce a quelle stringhe di rientrare, e tiene
le affermazioni della guida corrente ancorate ai file che descrive (issue #20).
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_DOCS = ROOT / "docs" / "deployment"
ENV_FILES = (
    ROOT / "frontend" / ".env.production",
    ROOT / "frontend" / ".env.example",
)

DEAD_HOST = "kpsfinanciallab.w3pro.it"
DEAD_PORT = ":8001"
NOT_CURRENT_MARKER = "NON CORRENTE"


def _cluster_files() -> list[Path]:
    return [path for path in ENV_FILES if path.exists()] + sorted(DEPLOY_DOCS.glob("*.md"))


@pytest.mark.parametrize("path", _cluster_files(), ids=lambda p: p.name)
def test_nessun_riferimento_al_backend_dismesso(path: Path) -> None:
    """Né l'host `*.w3pro.it` né la porta 8001 sopravvivono in configurazione o guide."""
    text = path.read_text(encoding="utf-8")
    assert DEAD_HOST not in text, f"{path.relative_to(ROOT)} cita ancora l'host dismesso"
    assert DEAD_PORT not in text, f"{path.relative_to(ROOT)} cita ancora la porta 8001"


def _assignments(path: Path, key: str) -> list[str]:
    values = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            values.append(value.strip())
    return values


def test_env_example_non_impone_un_backend_assoluto() -> None:
    """`.env.example` si copia partendo da zero: non può battezzare un host di produzione."""
    values = _assignments(ROOT / "frontend" / ".env.example", "NEXT_PUBLIC_API_URL")
    assert values, "l'esempio deve comunque mostrare la variabile"
    for value in values:
        assert value == "" or value.startswith("http://localhost"), (
            f"NEXT_PUBLIC_API_URL={value!r}: in produzione la variabile è vuota "
            "(URL relativi dietro nginx), in sviluppo punta a localhost"
        )


def test_env_production_lascia_la_variabile_vuota() -> None:
    """In produzione la variabile è vuota di proposito: l'app usa `/api/v1` dietro nginx."""
    values = _assignments(ROOT / "frontend" / ".env.production", "NEXT_PUBLIC_API_URL")
    assert values == [""], f"atteso NEXT_PUBLIC_API_URL vuoto, trovato {values!r}"


def test_i_file_env_restano_crlf() -> None:
    """I due `.env` sono CRLF: una conversione gonfia il diff e nasconde la modifica vera."""
    for path in ENV_FILES:
        data = path.read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n"), f"{path.name} ha righe LF"


CURRENT_GUIDE = DEPLOY_DOCS / "DEPLOY-JENKINS-DOCKER.md"


def test_esiste_una_guida_al_deploy_reale() -> None:
    """Qualcuno deve descrivere Jenkins + Docker + nginx, e la variabile vuota."""
    assert CURRENT_GUIDE.exists(), "serve una guida corrente che spieghi il deploy reale"
    text = CURRENT_GUIDE.read_text(encoding="utf-8")
    lowered = text.lower()
    for atteso in ("jenkinsfile", "docker compose", "nginx"):
        assert atteso in lowered, f"la guida corrente non nomina {atteso}"
    assert "NEXT_PUBLIC_API_URL" in text
    assert "/api/v1" in text


def test_le_guide_netlify_sono_marcate_non_correnti() -> None:
    """Netlify non è il deploy: chi apre quelle pagine lo deve leggere subito."""
    for doc in sorted(DEPLOY_DOCS.glob("*.md")):
        text = doc.read_text(encoding="utf-8")
        if "netlify" not in text.lower() or doc == CURRENT_GUIDE:
            continue
        head = "\n".join(text.splitlines()[:12])
        assert NOT_CURRENT_MARKER in head, f"{doc.name} parla di Netlify senza dirsi non corrente"


def test_la_guida_corrente_regge_al_confronto_col_codice() -> None:
    """Le tre affermazioni portanti della guida sono verificabili nel repository."""
    assert 'ENV NEXT_PUBLIC_API_URL=""' in (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    api_ts = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "process.env.NEXT_PUBLIC_API_URL || " in api_ts and "'/api/v1'" in api_ts
    assert "location /api/" in (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
