"""Import PDF snello: struttura, macroconti per percorso di legge, verifica con tappo dichiarato."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal

_IMMOBILIZZAZIONI_CAMPI = ("sp02_immob_immateriali", "sp03_immob_materiali", "sp04_immob_finanziarie")

# Nota aggiunta alla chiamata combinata di una pagina "prospetto_sp_e_ce" (Task lotto-b, fix 8):
# una pagina cosi' entra in pagine_sp E pagine_ce (TIPI_SP/TIPI_CE di analisi.py), e leggerla con
# due chiamate indipendenti manda la STESSA riga stampata a due letture separate, che possono
# risolverla con due percorsi legali diversi (es. SPP.D.O da una, SPP.D.E dall'altra) — da_coppie
# deduplica solo per percorso esatto, quindi la stessa massa finirebbe contata due volte
# (diagnosi budget_397). Una pagina cosi' si legge una volta sola, con una nota che chiede
# esplicitamente sia le voci SP sia le voci CE.
_NOTA_PAGINA_CONDIVISA = ("Questa pagina contiene sia voci di Stato Patrimoniale sia di Conto "
                         "Economico: leggi entrambe, ogni riga stampata una volta sola, mai due.")


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


def _anomalie(bs: dict, diag: dict) -> list:
    # Un'immobilizzazione negativa non sopravvive oltre conti.py (_clamp_immobilizzazioni_negative
    # la azzera sempre): il controllo diretto su bs resta solo come rete di sicurezza, mai la
    # fonte primaria - l'eccedenza tagliata la dichiara diag.
    dirette = [[campo, str(bs[campo])] for campo in _IMMOBILIZZAZIONI_CAMPI if campo in bs and bs[campo] < 0]
    return dirette + diag.get("immobilizzazioni_negative_tagliate", [])


def _unclassified_mass(diag: dict) -> Decimal:
    return sum((Decimal(v) for _, _, v in diag.get("lato_irrisolti", [])), Decimal(0))


def importa(file_path: str, *, ocr_text: str | None = None, analizza=None, leggi_conti=None,
            leggi_voci=None, trascrivi=None, route_hint: str | None = None) -> Risultato:
    t0 = time.monotonic()

    from importers.struttura_documento.analisi import analizza_struttura
    analizza_fn = analizza or analizza_struttura
    try:
        # route_hint si inoltra solo quando il chiamante lo passa: di default resta None e la
        # chiamata e' quella di sempre, posizionale sola — una `analizza` finta dei test che non
        # accetta affatto questo parametro (`lambda p: ...`) non deve rompersi (Task lotto-b, fix 9).
        struttura = analizza_fn(file_path, route_hint=route_hint) if route_hint is not None else analizza_fn(file_path)
    except Exception as e:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "struttura", "errore": type(e).__name__}) from e

    pagine_sp, pagine_ce = struttura.pagine_sp, struttura.pagine_ce
    if not pagine_sp and not pagine_ce:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "struttura", "errore": "nessun prospetto"})

    modo = struttura.modo
    forma = "bilancio" if modo == "legge" else None

    from importers.import_snello.verifica import misura, normalizza_forma, soglia, tappa, totali_stampati

    # Ancora indipendente dall'estrattore, letta una sola volta (nessuna chiamata modello):
    # in modo "conti" e' l'unico contraddittorio possibile (oggi None sempre); in modo "legge"
    # vince sui totali riportati dall'LLM quando esiste (li' sotto, in _combina).
    deterministici = totali_stampati(file_path)

    def _verifica(bs: dict, ce: dict, stampati: dict | None):
        if modo == "conti":
            # Task 14 (2026-09-26): in modo "conti" il costruttore (da_foglie) ha gia' portato
            # sp13 all'utile del CE per costruzione - non c'e' piu' un'euristica bilancio/
            # verifica da rilevare, ne' un normalizza_forma da applicare (sarebbe un no-op:
            # m["forma"] e' sempre "bilancio"). Rilevarla comunque (forma=None) rischierebbe di
            # tornare su "verifica" e sottrarre l'utile una seconda volta, mascherando un vero
            # sbilancio (budget_330) - lo stesso guasto che il doppio passaggio sotto evita per
            # modo "legge".
            m = misura(bs, ce, stampati, forma="bilancio")
            s = soglia(m["attivo"])
            bs, ce, tappo, esito = tappa(bs, ce, m, s)
            return bs, ce, tappo, esito, m, s
        m = misura(bs, ce, stampati, forma=forma)
        s = soglia(m["attivo"])
        bs = normalizza_forma(bs, ce, m)
        # normalizza_forma ha gia' commesso il foglio alla semantica bilancio (no-op se lo
        # era gia'): riautorilevare qui (forma=forma) puo' tornare su "verifica" e sottrarre
        # l'utile una seconda volta, mascherando un vero sbilancio (budget_330).
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
            prior, stampati = None, deterministici
        else:
            from importers.detail_enrichment import collect_source_rows
            from importers.import_snello.lettura import trascrivi_pagine, voci_di_legge
            from importers.import_snello.conti import da_coppie

            leggi_voci_fn = leggi_voci or voci_di_legge
            trascrivi_fn = trascrivi or trascrivi_pagine
            righe_documento = collect_source_rows(file_path, ocr_text=ocr_text)
            letture = {"sp": 1, "ce": 1}

            # Le pagine "prospetto_sp_e_ce" (SP e CE sulla stessa pagina fisica) entrano in
            # ENTRAMBE pagine_sp e pagine_ce: se ce ne sono, non le leggiamo due volte (fix 8).
            pagine_condivise = {m["pagina"] for m in struttura.mappe if m.get("tipo_pagina") == "prospetto_sp_e_ce"}

            def _leggi_sezione(pagine: list[int], intestazioni: list[str], nota: str = "") -> dict:
                pagine_insieme = set(pagine)
                if any(p in struttura.pagine_senza_testo for p in pagine):
                    testo = trascrivi_fn(file_path, pagine)
                else:
                    testo = "\n".join(f"{r.id}|{r.text}" for r in righe_documento if r.page in pagine_insieme)
                if nota:
                    return leggi_voci_fn(testo, intestazioni, nota=nota)
                return leggi_voci_fn(testo, intestazioni)

            def _leggi_sp_e_ce(nota_sp: str = "", nota_ce: str = ""):
                if pagine_condivise:
                    pagine_unione = sorted(set(pagine_sp) | set(pagine_ce))
                    intestazioni_unione = list(dict.fromkeys(list(struttura.intestazioni_sp)
                                                             + list(struttura.intestazioni_ce)))
                    nota = " ".join(n for n in (nota_sp, nota_ce) if n)
                    nota_unione = f"{_NOTA_PAGINA_CONDIVISA} {nota}" if nota else _NOTA_PAGINA_CONDIVISA
                    combinato = _leggi_sezione(pagine_unione, intestazioni_unione, nota=nota_unione)
                    return combinato, combinato
                with ThreadPoolExecutor(2) as ex:
                    fut_sp = ex.submit(_leggi_sezione, pagine_sp, struttura.intestazioni_sp, nota_sp)
                    fut_ce = ex.submit(_leggi_sezione, pagine_ce, struttura.intestazioni_ce, nota_ce)
                    return fut_sp.result(), fut_ce.result()

            def _combina(sp_res: dict, ce_res: dict):
                if sp_res is ce_res:
                    coppie_corrente = sp_res["corrente"]
                    coppie_precedente = sp_res["precedente"]
                    stampati = sp_res["totali"]
                else:
                    coppie_corrente = sp_res["corrente"] + ce_res["corrente"]
                    coppie_precedente = sp_res["precedente"] + ce_res["precedente"]
                    stampati = _unisci_totali(sp_res["totali"], ce_res["totali"])
                # I totali dichiarati dal documento (lettura deterministica, nessuna chiamata
                # modello) vincono su quelli riportati dall'LLM quando esistono entrambi: quelli
                # dell'LLM vengono dalla STESSA chiamata che ha letto le voci, quindi una
                # sotto-estrazione sistematica non troverebbe mai un contraddittorio reale.
                for chiave in ("totale_attivo", "totale_passivo"):
                    if deterministici.get(chiave) is not None:
                        stampati[chiave] = deterministici[chiave]
                bs, ce, diag = da_coppie(coppie_corrente)
                prior = da_coppie(coppie_precedente) if coppie_precedente else None
                return bs, ce, diag, prior, stampati

            sp_res, ce_res = _leggi_sp_e_ce()

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
            if pagine_condivise:
                # La pagina condivisa si rilegge tutta insieme (SP e CE): entrambe le sezioni
                # dichiarano la rilettura, non solo quella scelta dall'euristica (minor 4, fix
                # round 1) — altrimenti la diagnostica mentirebbe su quale sezione e' stata
                # riletta davvero.
                letture["sp"] = letture.get("sp", 1) + 1
                letture["ce"] = letture.get("ce", 1) + 1
                sp_res, ce_res = _leggi_sp_e_ce(nota_sp=nota, nota_ce=nota)
            elif sezione == "sp":
                letture[sezione] = letture.get(sezione, 1) + 1
                sp_res = _leggi_sezione(pagine_sp, struttura.intestazioni_sp, nota=nota)
            else:
                letture[sezione] = letture.get(sezione, 1) + 1
                ce_res = _leggi_sezione(pagine_ce, struttura.intestazioni_ce, nota=nota)

            fase = "conti"
            bs, ce, diag, prior, stampati = _combina(sp_res, ce_res)

            fase = "verifica"
            bs, ce, tappo, esito, m, s = _verifica(bs, ce, stampati)

        if esito == "vuoto":
            # Un'estrazione vuota non ha nulla di sensato da salvare: resta un ripiego,
            # sempre (anche dopo l'unica rilettura in modo "legge").
            report = {
                "esito": "ripiego", "fase": "verifica", "errore": esito, "modo": modo,
                "struttura": struttura.report(),
                "misura": {"corrente": {k: str(v) for k, v in m.items()}},
                "tappo": {"corrente": tappo}, "letture": letture, "diag": diag,
                "anomalie": _anomalie(bs, diag), "secondi": round(time.monotonic() - t0, 1),
            }
            raise SnelloNonRiuscito(report)

        if esito == "oltre_soglia":
            # Task 17 (decisione del proprietario, 2026-09-27): «se il bilancio non e'
            # quadrato deve essere comunque importato con avviso, l'utente lo correggera'
            # nella tab rettifiche». Oltre soglia dopo l'unica rilettura (modo "legge") o
            # direttamente (modo "conti", che non rilegge) non e' piu' un ripiego: si
            # adotta il risultato con lo sbilancio dichiarato. Nessun tappo si applica -
            # bs/ce restano quelli restituiti da tappa() (invariati), e gli scarti
            # misurati (scarto_sp/scarto_ce/scarto_stampati) restano in "misura", letti
            # da pdf_importer per costruire l'avviso mostrato all'utente.
            esito = "squadrato"

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
        "anomalie": _anomalie(bs, diag), "secondi": round(time.monotonic() - t0, 1),
    }
    if modo == "legge" and precedente_stato is not None:
        report["precedente"] = precedente_stato

    return Risultato(bs=bs, ce=ce, prior_bs=prior_bs, prior_ce=prior_ce, report=report, struttura=struttura)
