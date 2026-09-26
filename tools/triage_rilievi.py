"""Verdetto del banco di triage AMBIENTA: stesse suite su 62bfed1 e su HEAD, esito per rilievo nel foglio.

Uso: python tools/triage_rilievi.py   (dal worktree del banco; scrive inbox/Verifica_piano_Ambienta_triage.xlsx)
"""
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

VECCHIO = "62bfed1"
PY = "/home/peter/DEV/budget/backend/venv/bin/python"
NODE_MODULES = "/home/peter/DEV/budget/frontend/node_modules"
BANCO = ["tests/rilievi_kit.py", "tests/test_rilievi_ambienta.py", "tests/fixtures/ambienta_2026.json",
         "frontend/lib/rilievi-ambienta.test.ts"]
_ID = re.compile(r"(?:^|test_|> )([A-E]\d{2})[_ ]")
_PESO = {"fail": 3, "pass": 2, "skip": 1}
_FAILS = re.compile(r"\bit\.fails\s*\(")
VITEST_TEMP = "lib/rilievi-ambienta.triage.test.ts"

# Lettura a mano del verdetto: prevale sullo Stato meccanico, che resta nella nota («— banco: …»).
LETTURE = {
    "A01": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): motore e wizard erano già corretti; il "
            "previsionale vecchio nel PDF (A01-bis) ora blocca il \"finale\" del Business plan con un secondo "
            "avviso, `engine_version_stale` (severità error, come `forecast_stale`) — forma corta in "
            "intestazione, frase intera in copertina"),
    "A02": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): il punto di pareggio degli anni di piano viene da "
            "`ForecastYear.engine_meta['pareggio']` (il motore), non più dalla ripartizione fissa 60/40 costi "
            "fissi/variabili; `None` con `engine_meta_missing`/`pareggio_non_definito` quando il motore stesso "
            "non li ha definiti (colonna base/storica non toccata)"),
    "A03": ("Non riprodotto", "Motore non riprodotto; sintomo spiegato da A01-bis"),
    "A04": ("Risolto nel lotto 1 fix rilievi (2026-09-26), su decisione del proprietario",
            "Risolto nel lotto 1 fix rilievi (2026-09-26), su decisione del proprietario: con un piano "
            "crediti_commerciali l'incasso della massa oltre 12 mesi consuma prima sp07a (clienti), poi le altre "
            "sotto-voci in ordine, mai sotto zero (_consuma_in_ordine) — non più il riparto proporzionale che sul "
            "mix del consulente (sp07a 35.231 + sp07g 9.769) spostava sp07g a 9.551,91 invece di 8.769"),
    "A05": ("Risolto nel lotto 3 fix, 2026-09-26, su decisione del proprietario",
            "Risolto nel lotto 3 fix rilievi (2026-09-26), su decisione del proprietario: passare a Manuale da "
            "«ricavi» scrive il saldo dell'anno base, costante, invece dei valori dell'anteprima cresciuti coi "
            "ricavi (`withSpRule`, `frontend/lib/budget-sp-manuale.ts`)"),
    "A06": ("Risolto nel lotto 3 fix, 2026-09-26, su decisione del proprietario",
            "Risolto nel lotto 3 fix rilievi (2026-09-26), su decisione del proprietario: la casella "
            "previdenza/personale è sparita dal wizard e il motore non legge più "
            "`previdenza_scales_with_personnel` — sp16f/sp17f si agganciano al personale solo dalla tendina "
            "`sp_indexing`, come le altre voci minori; scenari salvati migrati con "
            "`scripts/migra_previdenza_tendina.py`"),
    "B01": ("Risolto nel lotto 1 fix rilievi (2026-09-26)",
            "Risolto nel lotto 1 fix rilievi (2026-09-26): ce10_var_rimanenze_mat_prime segue lo stato "
            "patrimoniale delle sole materie (sp05a), non più i ricavi; il DIO delle materie si deduce dal "
            "consumo (ce05 + ce10), non dal fatturato — details['rimanenze_materie']"),
    "B02": ("Risolto nel lotto 1 fix rilievi (2026-09-26)",
            "Risolto nel lotto 1 fix rilievi (2026-09-26): l'ammortamento dei cespiti esistenti si ferma al "
            "residuo netto invece di continuare alla quota piena; ogni nuovo investimento ammortizza per conto "
            "proprio — details['ammortamenti']"),
    "B03": ("Risolto nel lotto 1 fix rilievi (2026-09-26)",
            "Risolto nel lotto 1 fix rilievi (2026-09-26): ce08a (TFR) è sempre ce08b / 13,5, non più capato al "
            "residuo del personale; un'eccedenza ricompone il totale come somma e lo dichiara "
            "(details['personale_ricomposto'])"),
    "B04": ("Non riprodotto", "Motore non riprodotto; sintomo spiegato da A01-bis"),
    "B05": ("Risolto nel lotto 1 fix rilievi (2026-09-26)",
            "Risolto nel lotto 1 fix rilievi (2026-09-26): nell'ultimo anno di piano un contratto scadenziato a "
            "mano la cui lista non copre l'anno dopo ripete a breve l'ultima rata positiva (rata_ripetuta) "
            "invece di lasciare l'intero residuo a lungo termine oltre l'orizzonte — anche per gli altri "
            "finanziatori"),
    "C01": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): il DSCR è (MOL − imposte) / (oneri finanziari + "
            "quota capitale rimborsata nell'anno), quota capitale dal rendiconto dettagliato "
            "(`financing.third_party_funds.decreases`) — non più un proxy; `None` senza rendiconto per quel "
            "periodo o con `erogazioni_incoerenti`"),
    "C02": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): DSO sui soli crediti commerciali (`sp06a+sp07a`, "
            "non gli aggregati sp06/sp07) e DIO sul consumo di materie (`ce05+ce10`), `None` (mai zero) a "
            "consumo non positivo"),
    "C03": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): ROD divide per `financial_debt_total` (banche + "
            "altri finanziatori + obbligazioni, somma incondizionata), `None` (mai zero) a debito finanziario "
            "zero"),
    "C04": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): la PFN del report usa lo stesso "
            "`financial_debt_total` di C03 — prima un ramo tagliava fuori gli altri finanziatori quando "
            "c'erano già banche"),
    "C05": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): un solo current ratio, quick ratio e CCN in tutto "
            "il documento (`attivo_corrente`/`passivo_corrente`), simmetrici sui ratei — sp07 escluso "
            "dall'attivo corrente, sp18 incluso nel passivo corrente; margine di tesoreria, acid test, Altman "
            "e FGPMI non toccati"),
    "C06": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): l'indice di indebitamento è debiti totali / "
            "patrimonio netto (`leverage_ratio` = `debt_to_equity`), non più immobilizzazioni/PN"),
    "C07": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): la copertura delle immobilizzazioni include il TFR "
            "nel numeratore (patrimonio netto + debiti oltre 12 mesi + TFR)"),
    "C08": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): il rendiconto separa erogazioni e rimborsi quando "
            "`ForecastYear.engine_meta['erogazioni']` è noto; `erogazioni_incoerenti` ripiega sulla riga netta "
            "di sempre quando i dati non tornano"),
    "C09": ("Risolto nel lotto 2 fix rilievi (2026-09-26)",
            "Risolto nel lotto 2 fix rilievi (2026-09-26): la frase sugli oneri finanziari sul MOL parte dalla "
            "colonna base/storica (`of_mol`) quando la dichiara, non più dal primo anno di piano"),
    "E05": ("Risolto nel lotto 1 fix rilievi (2026-09-26), su decisione del proprietario",
            "Risolto nel lotto 1 fix rilievi (2026-09-26), su decisione del proprietario: un nuovo investimento "
            "ammortizza a metà aliquota nell'anno d'ingresso, piena dopo; proventi e oneri straordinari valgono "
            "zero in ogni anno di piano, salvo override esplicito"),
}


def verdetto(vecchio, nuovo) -> str:
    if nuovo is None:
        return "Senza test"
    if vecchio == "skip" or vecchio is None:
        base = "Confermato" if nuovo == "fail" else "Non riprodotto"
        return f"{base} (n/a su {VECCHIO})"
    return {("fail", "fail"): "Confermato", ("fail", "pass"): "Risolto (2026-09-24)",
            ("pass", "pass"): "Non riprodotto", ("pass", "fail"): "Regressione"}.get((vecchio, nuovo), f"{vecchio}/{nuovo}")


def esiti_junit(path) -> dict:
    out = {}
    for tc in ET.parse(path).iter("testcase"):
        m = _ID.search(tc.get("name", ""))
        if not m:
            continue
        esito = _esito(tc)
        rid = m.group(1)
        if _PESO[esito] > _PESO.get(out.get(rid), 0):
            out[rid] = esito
    return out


def _esito(tc) -> str:
    """pass/fail/skip di un testcase JUnit. Un xfail rimasto (banco senza --runxfail) è un rilievo confermato;
    un XPASS(strict) è un test che passa: il marcatore non deve invertire il verdetto."""
    fallito = tc.find("failure")
    if fallito is not None and "XPASS(strict)" in (fallito.get("message") or ""):
        return "pass"
    if fallito is not None or tc.find("error") is not None:
        return "fail"
    saltato = tc.find("skipped")
    if saltato is not None:
        return "fail" if saltato.get("type") == "pytest.xfail" else "skip"
    return "pass"


def senza_fails(testo: str) -> str:
    """Il file Vitest con `it.fails(` riscritto in `it(`: il banco misura l'oracolo, non il marcatore."""
    return _FAILS.sub("it(", testo)


def riga_foglio(rid: str, e_old: dict, e_new: dict, letture=LETTURE) -> tuple:
    """(Stato, Note) da scrivere nel foglio. Una lettura a mano prevale sullo Stato meccanico; la nota tiene
    comunque l'esito del banco sui due commit."""
    banco = f"banco: {VECCHIO}={e_old.get(rid, '-')}, HEAD={e_new.get(rid, '-')}"
    if rid in letture:
        stato, nota = letture[rid]
        return stato, f"{nota} — {banco}"
    return verdetto(e_old.get(rid), e_new.get(rid)), banco


def cartella_uscita(root: Path) -> Path:
    """Crea .superpowers/triage e il suo .gitignore, ritorna il path."""
    out = root / ".superpowers" / "triage"
    out.mkdir(parents=True, exist_ok=True)
    gitignore = out / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")
    return out


def _suite(root: Path, tag: str, out: Path) -> dict:
    py_xml, js_xml = out / f"{tag}-pytest.xml", out / f"{tag}-vitest.xml"
    # --runxfail: i marcatori xfail non devono cambiare l'esito misurato, su nessuno dei due lati.
    subprocess.run([PY, "-m", "pytest", "tests/test_rilievi_ambienta.py", "-q", "-p", "no:warnings",
                    "--runxfail", f"--junitxml={py_xml}"], cwd=root)
    nm = root / "frontend" / "node_modules"
    if not nm.exists():
        nm.symlink_to(NODE_MODULES)
    # Copia temporanea senza `it.fails`: stesso motivo di --runxfail, poi si cancella.
    src, tmp = root / "frontend" / "lib" / "rilievi-ambienta.test.ts", root / "frontend" / VITEST_TEMP
    tmp.write_text(senza_fails(src.read_text()))
    try:
        subprocess.run(["npx", "vitest", "run", VITEST_TEMP, "--reporter=junit",
                        f"--outputFile={js_xml}"], cwd=root / "frontend")
    finally:
        tmp.unlink(missing_ok=True)
    esiti = {}
    for x in (py_xml, js_xml):
        if x.exists():
            for rid, e in esiti_junit(x).items():
                if _PESO[e] > _PESO.get(esiti.get(rid), 0):
                    esiti[rid] = e
    return esiti


def main() -> int:
    qui = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    out = cartella_uscita(qui)
    vecchio = out / f"wt-{VECCHIO}"
    if not vecchio.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(vecchio), VECCHIO], cwd=qui, check=True)
    for f in BANCO:
        (vecchio / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(qui / f, vecchio / f)
    e_old, e_new = _suite(vecchio, "vecchio", out), _suite(qui, "nuovo", out)

    import openpyxl
    src = qui / "inbox" / "Verifica_piano_Ambienta_problemi.xlsx"
    wb = openpyxl.load_workbook(src)
    ws = wb["Elenco problemi"]
    for r in range(5, ws.max_row + 1):
        rid = ws.cell(r, 1).value
        if not rid or ws.cell(r, 10).value != "Softwarista":
            continue
        meccanico = verdetto(e_old.get(rid), e_new.get(rid))
        stato, nota = riga_foglio(rid, e_old, e_new)
        ws.cell(r, 11).value = stato
        ws.cell(r, 12).value = nota
        print(f"{rid:4} {stato}" + (f"   [meccanico: {meccanico}]" if stato != meccanico else ""))
    dst = qui / "inbox" / "Verifica_piano_Ambienta_triage.xlsx"
    wb.save(dst)
    print(f"scritto {dst}")
    subprocess.run(["git", "worktree", "remove", "--force", str(vecchio)], cwd=qui)
    return 0


if __name__ == "__main__":
    sys.exit(main())
