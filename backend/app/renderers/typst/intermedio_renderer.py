"""PDF del report intermedio, sullo stesso compilatore, sandbox e bundle del
dossier finale.

Il bundle `intermedio` porta solo il proprio punto d'ingresso; tutto il resto
(caratteri, `base.typ`, `pagine/comuni.typ`, grafici) e' letto da
`dossier-base` con la sua verifica sha256. Il bundle del finale non cambia di
un byte: il suo hash lega i piani editoriali gia' misurati, e aggiungervi un
file li avrebbe dichiarati tutti non attuali.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.schemas.intermedio_report import IntermediateReportModel

from .intermedio_catalog import build_inventory, documento_titolo
from .runtime import (
    Compiler, RendererBusy, RendererCompileError, RendererError, RendererInputError, RendererInvalidPdf,
    RendererLimits, RendererTimeout, RendererUnavailable, TemplateBundle, TypstRenderer, _regular, log,
    validate_pdf,
)

_TEMPLATES = Path(__file__).parent / "templates"
_INVENTORY = "editorial-inventory.json"


@dataclass(frozen=True)
class IntermedioTemplateBundle:
    base: Path = _TEMPLATES / "dossier-base"
    own: Path = _TEMPLATES / "intermedio"

    def read(self, limits: RendererLimits) -> tuple[str, str, dict[str, bytes]]:
        base_version, _, files = TemplateBundle(self.base).read(limits)
        own_version, entry, own = TemplateBundle(self.own).read(limits)
        if set(files) & set(own) or _INVENTORY in files or _INVENTORY in own:
            raise RendererUnavailable()
        return f"{base_version}+{own_version}", entry, {**files, **own}


@dataclass(frozen=True)
class IntermedioPdf:
    data: bytes
    sha256: str
    pages: int
    template_version: str
    compiler_version: str


def _contesto(model: IntermediateReportModel) -> str:
    proiezione = "proiezione a 12 mesi" if model.crisi.proiezione is not None else "senza proiezione"
    return (f"Bilancio infrannuale · {model.period_months} mesi {model.partial_year} · "
            f"riferimento {model.reference_year} · {proiezione}")


def typst_model(model: IntermediateReportModel) -> dict[str, Any]:
    """Cio' che il template legge dal modello: solo testata e frontespizio.
    I numeri arrivano gia' composti nell'inventario delle pagine."""
    return {
        "document": {"title": documento_titolo(model), "context": _contesto(model),
                     "commenti_stantii": model.commenti_stantii},
        "company": {"name": model.company_name},
        "indicator_catalog": [],
    }


class IntermedioRenderer(TypstRenderer):
    @classmethod
    def from_project(cls, root: Path, **kwargs):
        return cls(Compiler.from_manifest(root / "tools/typst/manifest.json", root / "tools/typst/bin/typst"),
                   IntermedioTemplateBundle(), **kwargs)

    def render_intermedio(self, model: IntermediateReportModel, *,
                          document_state: Literal["draft", "final"] = "draft",
                          grayscale: bool = False, conta_pagine: bool = True) -> IntermedioPdf:
        """`conta_pagine=False` serve solo alla diagnosi di un trabocco: il PDF
        esce anche se una voce del catalogo occupa piu' di una pagina."""
        started = time.monotonic()
        if document_state not in ("draft", "final") or type(grayscale) is not bool:
            raise RendererInputError()
        if not self._slots.acquire(blocking=False):
            raise RendererBusy()
        try:
            if platform.system() != "Linux" or platform.machine() != "x86_64":
                raise RendererUnavailable()
            inventory = build_inventory(model)
            serialized = json.dumps(typst_model(model), ensure_ascii=False).encode("utf-8")
            staged = json.dumps(inventory, ensure_ascii=False, allow_nan=False,
                                separators=(",", ":")).encode("utf-8")
            if len(serialized) > self.limits.max_input_bytes or len(staged) > self.limits.max_input_bytes:
                raise RendererInputError()
            version, entry, files = self.bundle.read(self.limits)
            binary = self.compiler.verified_bytes()
            if not self.sandbox.is_file() or self.sandbox.is_symlink() or not os.access(self.sandbox, os.X_OK):
                raise RendererUnavailable()
            options = json.dumps({"document_state": document_state, "grayscale": grayscale}).encode("utf-8")
            try:
                with self._private_job(serialized, {**files, _INVENTORY: staged}, binary, options) as job:
                    deadline = started + self.limits.timeout_seconds
                    self._run(self._sandbox_command(job, ["/report/compiler", "--version"]), job,
                              unavailable=True, deadline=deadline)
                    compiler = ["/report/compiler", "compile", "--root", "/report", "--format", "pdf",
                                "--jobs", "1", "--ignore-system-fonts", "--package-path", "/report/packages",
                                "--package-cache-path", "/report/cache", "--font-path", "/report/fonts",
                                "--creation-timestamp", str(int(model.generated_at.timestamp())),
                                "--diagnostic-format", "short", f"/report/{entry}", "/report/output/report.pdf"]
                    self._run(self._sandbox_command(job, compiler), job, deadline=deadline)
                    try:
                        data = _regular(job / "output/report.pdf", self.limits.max_output_bytes)
                    except RendererUnavailable:
                        raise RendererInvalidPdf() from None
                    pages = validate_pdf(data, title=documento_titolo(model),
                                         draft=document_state == "draft", limits=self.limits)
                    if time.monotonic() > deadline:
                        raise RendererTimeout()
            except RendererError:
                raise
            except OSError:
                raise RendererUnavailable() from None
            # Una voce del catalogo = una pagina fisica, come nel dossier finale:
            # l'indice di copertina conta su questo. Una pagina che trabocca
            # (un commento troppo lungo, una tabella in piu') si rifiuta.
            if conta_pagine and pages != len(inventory):
                raise RendererCompileError(("intermedio-page-overflow",))
            log.info("typst_intermedio_success pages=%d bytes=%d elapsed_ms=%d",
                     pages, len(data), int((time.monotonic() - started) * 1000))
            return IntermedioPdf(data, hashlib.sha256(data).hexdigest(), pages, version, self.compiler.version)
        except RendererError as error:
            log.warning("typst_intermedio_failed category=%s", error.category)
            raise
        finally:
            self._slots.release()
