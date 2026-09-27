"""Import PDF snello: struttura, macroconti per percorso di legge, verifica con tappo dichiarato."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal

_IMMOBILIZZAZIONI_CAMPI = ("sp02_immob_immateriali", "sp03_immob_materiali", "sp04_immob_finanziarie")


class SnelloNonRiuscito(Exception):
    """Il percorso snello non e' arrivato a un risultato utilizzabile: ``report`` dichiara fase ed
    errore, mai un dato inventato al loro posto."""

    def __init__(self, report: dict):
        super().__init__(report.get("errore") or report.get("fase") or "ripiego")
        self.report = report


@dataclass
class Risultato:
    bs: dict
    ce: dict
    prior_bs: dict | None
    prior_ce: dict | None
    report: dict
    struttura: object


def _unisci_totali(a: dict, b: dict) -> dict:
    """Unione dei totali stampati dalle due chiamate (SP e CE): tiene il primo valore non nullo,
    ripiegando sul secondo quando il primo manca."""
    out = dict(a)
    for k, v in b.items():
        if out.get(k) is None:
            out[k] = v
    return out


def _anomalie(bs: dict) -> list:
    return [[campo, str(bs[campo])] for campo in _IMMOBILIZZAZIONI_CAMPI if campo in bs and bs[campo] < 0]


def _unclassified_mass(diag: dict) -> Decimal:
    return sum((Decimal(v) for _, _, v in diag.get("lato_irrisolti", [])), Decimal(0))


def importa(file_path: str, *, ocr_text: str | None = None, analizza=None, leggi_conti=None,
            leggi_voci=None, trascrivi=None) -> Risultato:
    t0 = time.monotonic()

    from importers.struttura_documento.analisi import analizza_struttura
    analizza_fn = analizza or analizza_struttura
    try:
        struttura = analizza_fn(file_path)
    except Exception as e:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "struttura", "errore": type(e).__name__}) from e

    pagine_sp, pagine_ce = struttura.pagine_sp, struttura.pagine_ce
    if not pagine_sp and not pagine_ce:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "struttura", "errore": "nessun prospetto"})

    modo = struttura.modo
    forma = "bilancio" if modo == "legge" else None

    from importers.import_snello.verifica import misura, normalizza_forma, soglia, tappa

    def _verifica(bs: dict, ce: dict, stampati: dict | None):
        m = misura(bs, ce, stampati, forma=forma)
        s = soglia(m["attivo"])
        bs = normalizza_forma(bs, ce, m)
        # normalizza_forma ha gia' commesso il foglio alla semantica bilancio (no-op se lo
        # era gia'): riautorilevare qui (forma=forma, che per modo="conti" e' None) puo'
        # tornare su "verifica" e sottrarre l'utile una seconda volta, mascherando un vero
        # sbilancio (budget_330).
        m = misura(bs, ce, stampati, forma="bilancio")
        bs, ce, tappo, esito = tappa(bs, ce, m, s)
        return bs, ce, tappo, esito, m, s

    fase = "lettura"
    try:
        if modo == "conti":
            from importers.import_snello.righe import foglie, righe_da_pdf
            from importers.import_snello.lettura import percorsi_dei_conti
            from importers.import_snello.conti import da_foglie

            leggi_conti_fn = leggi_conti or percorsi_dei_conti
            ruoli = struttura.colonne_sp or struttura.colonne_ce
            righe = righe_da_pdf(file_path, set(pagine_sp) | set(pagine_ce), ruoli, ocr_text)
            fo = foglie(righe)
            letture = leggi_conti_fn(righe, fo)

            fase = "conti"
            bs, ce, diag = da_foglie(fo)
            prior, stampati = None, None
        else:
            from importers.detail_enrichment import collect_source_rows
            from importers.import_snello.lettura import trascrivi_pagine, voci_di_legge
            from importers.import_snello.conti import da_coppie

            leggi_voci_fn = leggi_voci or voci_di_legge
            trascrivi_fn = trascrivi or trascrivi_pagine
            righe_documento = collect_source_rows(file_path, ocr_text=ocr_text)
            letture = {"sp": 1, "ce": 1}

            def _leggi_sezione(pagine: list[int], intestazioni: list[str], nota: str = "") -> dict:
                pagine_insieme = set(pagine)
                if any(p in struttura.pagine_senza_testo for p in pagine):
                    testo = trascrivi_fn(file_path, pagine)
                else:
                    testo = "\n".join(f"{r.id}|{r.text}" for r in righe_documento if r.page in pagine_insieme)
                if nota:
                    return leggi_voci_fn(testo, intestazioni, nota=nota)
                return leggi_voci_fn(testo, intestazioni)

            def _combina(sp_res: dict, ce_res: dict):
                coppie_corrente = sp_res["corrente"] + ce_res["corrente"]
                coppie_precedente = sp_res["precedente"] + ce_res["precedente"]
                stampati = _unisci_totali(sp_res["totali"], ce_res["totali"])
                bs, ce, diag = da_coppie(coppie_corrente)
                prior = da_coppie(coppie_precedente) if coppie_precedente else None
                return bs, ce, diag, prior, stampati

            with ThreadPoolExecutor(2) as ex:
                fut_sp = ex.submit(_leggi_sezione, pagine_sp, struttura.intestazioni_sp)
                fut_ce = ex.submit(_leggi_sezione, pagine_ce, struttura.intestazioni_ce)
                sp_res, ce_res = fut_sp.result(), fut_ce.result()

            fase = "conti"
            bs, ce, diag, prior, stampati = _combina(sp_res, ce_res)

        fase = "verifica"
        bs, ce, tappo, esito, m, s = _verifica(bs, ce, stampati)

        if modo == "legge" and esito in ("oltre_soglia", "vuoto"):
            fase = "lettura"
            if abs(m["scarto_sp"]) > s or m["scarto_stampati"] > s:
                sezione = "sp"
            else:
                sezione = "ce"
            if esito == "vuoto":
                nota = ("Una lettura precedente non ha dato alcuna voce: attivo e passivo sono "
                        "risultati entrambi zero. Controlla se il prospetto e' stato individuato "
                        "correttamente.")
            else:
                scarto = max(abs(m["scarto_sp"]), m["scarto_stampati"])
                nota = (f"Una lettura precedente dava uno scarto di {scarto} euro fra attivo e "
                        f"passivo (o fra risultato CE e SP): controlla voci mancanti, doppie o "
                        f"totali presi come voci.")
            letture[sezione] = letture.get(sezione, 1) + 1
            if sezione == "sp":
                sp_res = _leggi_sezione(pagine_sp, struttura.intestazioni_sp, nota=nota)
            else:
                ce_res = _leggi_sezione(pagine_ce, struttura.intestazioni_ce, nota=nota)

            fase = "conti"
            bs, ce, diag, prior, stampati = _combina(sp_res, ce_res)

            fase = "verifica"
            bs, ce, tappo, esito, m, s = _verifica(bs, ce, stampati)

        if esito in ("oltre_soglia", "vuoto"):
            report = {
                "esito": "ripiego", "fase": "verifica", "errore": esito, "modo": modo,
                "struttura": struttura.report(),
                "misura": {"corrente": {k: str(v) for k, v in m.items()}},
                "tappo": {"corrente": tappo}, "letture": letture, "diag": diag,
                "anomalie": _anomalie(bs), "secondi": round(time.monotonic() - t0, 1),
            }
            raise SnelloNonRiuscito(report)

        prior_bs = prior_ce = prior_diag = None
        m_prec = tappo_prec = None
        precedente_stato = None
        if modo == "legge" and prior is not None:
            pbs, pce, pdiag = prior
            pbs, pce, tappo_prec, esito_prec, m_prec, _ = _verifica(pbs, pce, None)
            if esito_prec in ("oltre_soglia", "vuoto"):
                precedente_stato = "escluso_oltre_soglia"
                m_prec = tappo_prec = None
            else:
                precedente_stato = "incluso"
                prior_bs, prior_ce, prior_diag = pbs, pce, pdiag
    except SnelloNonRiuscito:
        raise
    except Exception as e:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": fase, "errore": type(e).__name__}) from e

    bs["_plug_residual"] = Decimal(tappo["importo"]) if tappo and "importo" in tappo else Decimal(0)
    bs["_unclassified_mass"] = _unclassified_mass(diag)

    misura_report = {"corrente": {k: str(v) for k, v in m.items()}}
    tappo_report = {"corrente": tappo}
    if modo == "legge" and m_prec is not None:
        misura_report["precedente"] = {k: str(v) for k, v in m_prec.items()}
        tappo_report["precedente"] = tappo_prec

    report = {
        "esito": esito, "modo": modo, "struttura": struttura.report(),
        "misura": misura_report, "tappo": tappo_report, "letture": letture, "diag": diag,
        "anomalie": _anomalie(bs), "secondi": round(time.monotonic() - t0, 1),
    }
    if modo == "legge" and precedente_stato is not None:
        report["precedente"] = precedente_stato

    return Risultato(bs=bs, ce=ce, prior_bs=prior_bs, prior_ce=prior_ce, report=report, struttura=struttura)
