"""Task 7: il Documento dalle tabelle HTML di MinerU (scansioni senza text layer). La colonna di un importo e' la
posizione della sua cella, mai «gli ultimi due»."""
from decimal import Decimal

from importers.lettore import Documento, leggi_celle


def _tabella(*righe: list[str]) -> str:
    return "<table>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in righe) + "</table>"


def _riga(doc: Documento, etichetta: str, lato: str | None = None):
    trovate = [r for r in doc.righe if r.etichetta == etichetta and (lato is None or r.lato == lato)]
    assert len(trovate) == 1, [(r.etichetta, r.lato) for r in doc.righe]
    return trovate[0]


def _valori(doc: Documento, riga) -> dict[str, Decimal]:
    per_indice = {c.indice: c for c in doc.colonne}
    return {f"{per_indice[i].ruolo}:{per_indice[i].fine}": imp.valore for i, imp in riga.celle.items()}


def test_quattro_colonne_con_differenza():
    html = _tabella(["", "31/12/2024", "31/12/2023", "Differenza", "%"],
                    ["Crediti verso clienti", "1.200,00", "1.000,00", "200,00", "20,000"],
                    ["Altri crediti", "300,00", "400,00", "-100,00", "-25,000"],
                    ["Disponibilita' liquide", "50,00", "40,00", "10,00", "25,000"])
    doc = leggi_celle([html], [1])
    assert [c.ruolo for c in doc.colonne] == ["esercizio", "esercizio", "differenza", "percentuale"]
    corrente = next(c for c in doc.colonne if c.corrente)
    precedente = next(c for c in doc.colonne if c.ruolo == "esercizio" and not c.corrente)
    assert (corrente.fine.year, precedente.fine.year) == (2024, 2023)
    r = _riga(doc, "Crediti verso clienti")
    # C4: con «gli ultimi due» si leggerebbero 200 e 20; la posizione della cella dice 1.200 e 1.000
    assert r.celle[corrente.indice].valore == Decimal("1200.00")
    assert r.celle[precedente.indice].valore == Decimal("1000.00")
    assert r.parte == "prospetto" and r.lato == "U"


def test_tabella_senza_intestazione_eredita():
    prima = _tabella(["", "31/12/2024", "31/12/2023"],
                     ["Crediti verso clienti", "1.200,00", "1.000,00"])
    seguito = _tabella(["Debiti verso fornitori", "700,00", "650,00"],
                       ["Debiti tributari", "", "30,00"])
    doc = leggi_celle([prima, seguito], [1, 2])
    assert len(doc.colonne) == 2
    corrente = next(c for c in doc.colonne if c.corrente)
    r = _riga(doc, "Debiti verso fornitori")
    assert r.pagina == 2
    assert r.celle[corrente.indice].valore == Decimal("700.00")
    tributari = _riga(doc, "Debiti tributari")
    assert corrente.indice not in tributari.celle
    assert list(tributari.celle.values())[0].valore == Decimal("30.00")


def test_grafie_ocr():
    html = _tabella(["", "31/12/2024", "31/12/2023"],
                    ["Crediti verso clienti", "94.086.46", "11 396,02"],
                    ["Altri crediti", "1.234 ,56", "−1.000,00"],
                    ["Ratei e risconti", "2 500,00", "1.000,00 A"])
    doc = leggi_celle([html], [1])
    corrente = next(c for c in doc.colonne if c.corrente)
    precedente = next(c for c in doc.colonne if not c.corrente)
    r = _riga(doc, "Crediti verso clienti")
    assert r.celle[corrente.indice].valore == Decimal("94086.46")
    assert r.celle[precedente.indice].valore == Decimal("11396.02")
    assert r.celle[corrente.indice].testo == "94.086.46"      # il testo resta come stampato
    altri = _riga(doc, "Altri crediti")
    assert altri.celle[corrente.indice].valore == Decimal("1234.56")
    assert altri.celle[precedente.indice].valore == Decimal("-1000.00")
    ratei = _riga(doc, "Ratei e risconti")
    assert ratei.celle[corrente.indice].valore == Decimal("2500.00")
    assert ratei.celle[precedente.indice].valore == Decimal("-1000.00")


def test_codice_non_e_un_importo_ocr():
    """La correzione OCR vale solo nelle colonne: un codice «12.34» nella cella della descrizione resta testo."""
    html = _tabella(["", "", "31/12/2024"],
                    ["12.34", "Cassa", "10,00"])
    doc = leggi_celle([html], [1])
    r = next(r for r in doc.righe if "Cassa" in r.etichetta)
    assert list(r.celle.values())[0].valore == Decimal("10.00")
    assert "12.34" in (r.codice + " " + r.etichetta)


def test_tabella_di_nota_saltata():
    prospetto = _tabella(["", "31/12/2024", "31/12/2023"],
                         ["Crediti verso clienti", "1.200,00", "1.000,00"])
    nota = _tabella(["", "Valore di inizio esercizio", "Incrementi", "Valore di fine esercizio"],
                    ["Impianti", "9.999,00", "1,00", "10.000,00"])
    seguito = _tabella(["Debiti verso fornitori", "700,00", "650,00"])
    doc = leggi_celle([prospetto, nota, seguito], [1, 2, 2])
    assert all("Impianti" not in r.etichetta for r in doc.righe)
    assert len(doc.profilo.tabelle_nota) == 1
    assert doc.profilo.tabelle_nota[0].pagina == 2
    r = _riga(doc, "Debiti verso fornitori")
    corrente = next(c for c in doc.colonne if c.corrente)
    assert r.celle[corrente.indice].valore == Decimal("700.00")
    assert all(r.parte == "prospetto" for r in doc.righe)


def test_sezioni_dai_titoli():
    html = _tabella(["STATO PATRIMONIALE", "31/12/2024", "31/12/2023"],
                    ["Crediti verso clienti", "1.200,00", "1.000,00"],
                    ["CONTO ECONOMICO", "", ""],
                    ["Ricavi delle vendite", "5.000,00", "4.000,00"])
    doc = leggi_celle([html], [1])
    assert _riga(doc, "Crediti verso clienti").sezione == "SP"
    assert _riga(doc, "Ricavi delle vendite").sezione == "CE"
    assert _riga(doc, "CONTO ECONOMICO").intestazione
    assert doc.profilo.sezioni[1] == "SP+CE"


def test_totali_e_padri():
    html = _tabella(["", "31/12/2024", "31/12/2023"],
                    ["Crediti", "", ""],
                    ["Clienti", "100,00", "90,00"],
                    ["Altri", "50,00", "40,00"],
                    ["Totale crediti", "150,00", "130,00"])
    doc = leggi_celle([html], [1])
    totale = _riga(doc, "Totale crediti")
    assert totale.totale
    clienti = _riga(doc, "Clienti")
    assert clienti.padre == totale.id and clienti.padre_verificato
    assert _riga(doc, "Crediti").intestazione


def test_contrapposte_due_lati():
    html = _tabella(["Attivita'", "31/12/2024", "Passivita'", "31/12/2024"],
                    ["Cassa", "100,00", "Debiti", "70,00"],
                    ["Banca", "200,00", "Capitale", "230,00"])
    doc = leggi_celle([html], [1])
    cassa, debiti = _riga(doc, "Cassa"), _riga(doc, "Debiti")
    assert (cassa.lato, debiti.lato) == ("L", "R")
    per_indice = {c.indice: c for c in doc.colonne}
    assert per_indice[next(iter(cassa.celle))].lato == "L"
    assert per_indice[next(iter(debiti.celle))].lato == "R"
    assert debiti.celle[next(iter(debiti.celle))].valore == Decimal("70.00")
    assert doc.contrapposto and doc.profilo.contrapposto
    assert all(c.corrente for c in doc.colonne)       # una colonna di valori per lato


def test_colspan_allinea_le_celle():
    html = ("<table><tr><td></td><td>31/12/2024</td><td>31/12/2023</td></tr>"
            "<tr><td>Crediti</td><td>100,00</td><td>90,00</td></tr>"
            "<tr><td colspan=\"2\">Totale crediti</td><td>90,00</td></tr></table>")
    doc = leggi_celle([html], [1])
    precedente = next(c for c in doc.colonne if not c.corrente)
    totale = _riga(doc, "Totale crediti")
    assert list(totale.celle) == [precedente.indice]


def test_importi_nella_descrizione_si_dichiarano():
    """MinerU che stringe la riga in una cella: gli importi non vanno su una colonna a indovinare."""
    html = _tabella(["", "31/12/2024", "31/12/2023"],
                    ["Altri crediti", "300,00", "400,00"],
                    ["Crediti verso clienti 1.200,00 1.000,00", "", ""])
    doc = leggi_celle([html], [1])
    r = _riga(doc, "Crediti verso clienti 1.200,00 1.000,00")
    assert not r.celle
    assert any("descrizione" in a for a in doc.avvisi)


def test_profilo_minimo():
    html = _tabella(["", "31/12/2024", "31/12/2023"],
                    ["Crediti verso clienti", "1.200,00", "(1.000,00)"],
                    ["Altri crediti", "300,00", "(400,00)"])
    doc = leggi_celle([html], [1])
    p = doc.profilo
    assert p.colonne is doc.colonne and p.confine is None and not p.contrapposto
    assert "parentesi" in p.negativi
    assert set(p.decimali.values()) == {True}
    assert p.parti == {1: "prospetto"}
    assert p.tipo in ("schema", "schema-dettaglio", "contrapposte", "verifica", "ignoto")


def test_nessuna_tabella():
    doc = leggi_celle([], [])
    assert doc.righe == [] and doc.colonne == [] and doc.avvisi


def test_seguito_con_una_cella_in_piu_si_allinea():
    """MinerU aggiunge una cella vuota fra descrizione e importi nella tabella che continua: per posizione pura il
    corrente finirebbe sul precedente."""
    prima = _tabella(["", "31/12/2024", "31/12/2023"],
                     ["Crediti verso clienti", "1.200,00", "1.000,00"])
    seguito = _tabella(["Debiti verso fornitori", "", "700,00", "650,00"],
                       ["Debiti tributari", "", "30,00", "20,00"])
    doc = leggi_celle([prima, seguito], [1, 2])
    corrente = next(c for c in doc.colonne if c.corrente)
    precedente = next(c for c in doc.colonne if not c.corrente)
    r = _riga(doc, "Debiti verso fornitori")
    assert r.celle[corrente.indice].valore == Decimal("700.00")
    assert r.celle[precedente.indice].valore == Decimal("650.00")
    assert any("spostate di 1" in a for a in doc.avvisi)


def test_seguito_di_una_nota_resta_nota():
    prospetto = _tabella(["", "31/12/2024", "31/12/2023"],
                         ["Crediti verso clienti", "1.200,00", "1.000,00"])
    nota = _tabella(["Descrizione", "Esercizio precedente", "Esercizio corrente", "Variazione"],
                    ["Debito IRES", "24.524,00", "29.735,00", "5.211,00"])
    seguito = _tabella(["Erario ritenute", "2.400,00", "3.210,00", "810,00"])
    doc = leggi_celle([prospetto, nota, seguito], [1, 2, 2])
    assert [r.etichetta for r in doc.righe] == ["Crediti verso clienti"]
    assert len(doc.profilo.tabelle_nota) == 2


def test_testo_sopra_le_colonne_ereditate_e_nota():
    prospetto = _tabella(["", "31/12/2024", "31/12/2023"],
                         ["Crediti verso clienti", "1.200,00", "1.000,00"])
    nota = _tabella(["", "Variazioni nell'esercizio"],
                    ["Crediti per versamenti dovuti", "100,00"])
    doc = leggi_celle([prospetto, nota], [1, 2])
    assert [r.etichetta for r in doc.righe] == ["Crediti verso clienti"]


def test_verifica_contrapposta_senza_date():
    """Un bilancio di verifica non data le colonne: «Conto | Descrizione | Importo» due volte, sotto i titoli dei
    lati, e un'anagrafica con una data non e' un'intestazione."""
    anagrafica = _tabella(["Unicarton Srl", "Via S.Antonio 19", "Data", "11/09/2026"])
    html = _tabella(["Attivita'", "", "", "Passivita'", "", ""],
                    ["Conto", "Descrizione", "Importo", "Conto", "Descrizione", "Importo"],
                    ["03", "IMMOBILIZZAZIONI", "2.145,00", "23", "CAPITALE E RISERVE", "1.497,00"],
                    ["05", "CREDITI", "1.000,00", "25", "DEBITI", "1.648,00"],
                    ["", "Totale attivita'", "3.145,00", "", "Totale passivita'", "3.145,00"])
    doc = leggi_celle([anagrafica, html], [1, 1])
    assert {c.lato for c in doc.colonne} == {"L", "R"} and all(c.fine is None for c in doc.colonne)
    assert _riga(doc, "Attivita'", "L").intestazione and _riga(doc, "Passivita'", "R").intestazione
    debiti = next(r for r in doc.righe if "DEBITI" in r.etichetta)
    assert debiti.lato == "R" and list(debiti.celle.values())[0].valore == Decimal("1648.00")
    assert _riga(doc, "Totale attivita'", "L").totale


def test_titoli_dei_lati_come_intestazione():
    html = _tabella(["ATTIVITA'", "", "PASSIVITA'", ""],
                    ["Costi di impianto", "5.555,24", "F.do amm. costi impianto", "1.111,05"],
                    ["Cassa", "100,00", "Debiti", "4.544,19"])
    doc = leggi_celle([html], [1])
    assert _riga(doc, "Cassa", "L").celle and _riga(doc, "Debiti", "R").celle
    assert doc.contrapposto


def test_dal_al_sopra_una_tabella_di_conti_non_e_intestazione():
    periodo = _tabella(["ESERCIZIO", "2026,00"], ["Dal", "al 31/08/2026"])
    html = _tabella(["Costi", "", "", "Ricavi", "", ""],
                    ["Codice", "Descrizione", "Importo", "Codice", "Descrizione", "Importo"],
                    ["75.01", "ONERI FINANZIARI", "7.652,98", "47", "RICAVI", "9.000,00"])
    doc = leggi_celle([periodo, html], [1, 1])
    assert all(c.fine is None for c in doc.colonne)
    assert all("ESERCIZIO" not in r.etichetta for r in doc.righe if r.celle)


def test_intero_nudo_solo_in_colonna_a_interi():
    """Decisione R6: «0» e «673» sono importi solo in una colonna che stampa interi («10.000»)."""
    interi = _tabella(["", "31/12/2024", "31/12/2023"],
                      ["Capitale", "24.500", "24.500"],
                      ["Varie altre riserve", "673", "0"])
    doc = leggi_celle([interi], [1])
    r = _riga(doc, "Varie altre riserve")
    assert sorted(v.valore for v in r.celle.values()) == [Decimal("0"), Decimal("673")]
    decimali = _tabella(["", "31/12/2024", "31/12/2023"],
                        ["Capitale", "24.500,00", "24.500,00"],
                        ["Varie altre riserve", "673", "1,00"])
    doc = leggi_celle([decimali], [1])
    r = next(r for r in doc.righe if r.etichetta.startswith("Varie"))
    assert [v.valore for v in r.celle.values()] == [Decimal("1.00")] and "673" in r.etichetta


def test_pagina_contata_da_uno():
    import pytest
    with pytest.raises(ValueError):
        leggi_celle([_tabella(["", "31/12/2024"], ["Cassa", "1,00"])], [0])


def test_prospetto_che_riprende_dopo_una_nota_in_mezzo():
    """La nota «Varie altre riserve» in mezzo al prospetto, larga come lui: il seguito con le voci di legge e' ancora
    il prospetto (`_grezze_mineru`)."""
    prospetto = _tabella(["", "31/12/2024", "31/12/2023"],
                         ["VI - Altre riserve", "1.200,00", "1.000,00"])
    nota = _tabella(["", "Descrizione", "Importo"],
                    ["", "Riserva straordinaria", "1.200,00"])
    seguito = _tabella(["IX - Utile (perdita) dell'esercizio", "700,00", "650,00"])
    doc = leggi_celle([prospetto, nota, seguito], [1, 1, 2])
    assert [r.etichetta for r in doc.righe] == ["VI - Altre riserve", "IX - Utile (perdita) dell'esercizio"]
