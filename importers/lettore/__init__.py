"""Lettore di righe unico (Fase 1): costruito accanto all'importatore, non ancora collegato."""
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.righe import Documento, Riga, leggi_pdf

__all__ = ["Documento", "Importo", "Riga", "leggi_importo", "leggi_pdf"]
