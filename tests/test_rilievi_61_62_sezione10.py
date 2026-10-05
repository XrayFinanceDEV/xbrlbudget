"""Task 14 (#61 S15, #62 S24): sezione 10 del Business plan completa, nota IVA, avvisi del motore."""
from decimal import Decimal as D

from tests.rilievi_kit import genera, generato, righe

_FIN = {"name": "Fin. A", "amount": 0, "opening_residual": 960937.42, "interest_rate": 4,
        "grace_years": 0, "balloon_pct": 0, "duration_years": None, "repayments": [320000, 320000, 320937.42]}


def _sez10(e):
    from reportlab.platypus import Paragraph, Table
    from backend.app.renderers.business_plan import sections_partenza, theme
    theme.register_fonts()

    def testo(f):
        out = []
        for x in f:
            if isinstance(x, Paragraph):
                out.append(x.getPlainText())
            elif isinstance(x, Table):
                out += [testo(c if isinstance(c, list) else [c]) for r in x._cellvalues for c in r]
            elif hasattr(x, "_content"):
                out.append(testo(x._content))
        return " ".join(str(o) for o in out)
    return testo(sections_partenza.ipotesi(e.data, {}))


def test_R2_sezione_10_completa_e_senza_righe_a_zero():
    rows = righe()
    rows[0]["financing_loans"] = [_FIN]
    e = generato(genera(rows, report=True))
    etichette = [r.label for r in e.data.assumptions]
    assert "Proventi finanziari" not in etichette or any(
        r.label == "Proventi finanziari" and any(v for v in r.values) for r in e.data.assumptions)
    for r in e.data.assumptions:
        if r.label in ("Costi operativi / ricavi", "Proventi finanziari", "Ammortamenti", "Rimborso debito"):
            assert any((v or 0) != 0 for v in r.values), r.label
    # i tre anni rimborsano 320k ogni anno: la riga c'e', non e' tutta a zero
    assert "Rimborso debito" in etichette
    (f,) = e.data.finanziamenti_tabella
    assert (f.nome, f.tipo, f.importo, f.tasso) == ("Fin. A", "Pregresso", D("960937.42"), D(4))
    assert "Tasso" in _sez10(e) and "Fin. A" in _sez10(e)


def test_R2_proventi_finanziari_e_righe_calcolate_a_zero_non_escono():
    e = generato(genera(righe(ce14_override=1200), report=True))
    riga = next(r for r in e.data.assumptions if r.label == "Proventi finanziari")
    assert all(v == D(1200) for v in riga.values)
    # senza finanziamenti il rimborso di ogni anno e' zero: la riga non esce
    assert "Rimborso debito" not in [r.label for r in e.data.assumptions]


def test_R2_riga_input_scritta_a_zero_resta_e_default_a_zero_no():
    from backend.app.renderers.business_plan.data import from_report
    e = generato(genera(righe(asset_disposal_proceeds=0), report=True))
    # nel kit la provenienza e' `legacy_unknown` (nessun set di campi forniti): un default a zero non esce
    assert not any("Corrispettivo" in r.label for r in e.data.assumptions)
    # lo stesso zero con provenienza `user` (come lo scrive il bulk di produzione) resta
    for sec in e.rep.assumption_sections:
        for a in sec.assumptions:
            if a.field == "asset_disposal_proceeds":
                object.__setattr__(a, "provenance", "user")
    rid = from_report(e.rep, draft=True)
    assert any("Corrispettivo" in r.label and all(v == 0 for v in r.values) for r in rid.assumptions)


def test_R4_nota_iva_sotto_i_driver():
    e = generato(genera(righe(), report=True))
    t = _sez10(e)
    assert "al netto dell'IVA" in t and "Un DSO/DPO misurato sui saldi storici risulta quindi più alto" in t


def test_R2_avvisi_del_motore_arrivano_al_report():
    e = generato(genera(righe(dio_days=25), report=True))
    assert any("magazzino" in a for a in e.data.avvisi_motore)
    assert len(set(e.data.avvisi_motore)) == len(e.data.avvisi_motore)  # deduplicate fra gli anni
    assert "Avvisi del motore" in _sez10(e)


def test_R2_liquidazioni_tfr_compaiono_con_gli_importi():
    rows = righe()
    for r, v in zip(rows, (1000, 2000, 3000)):
        r["tfr_payments"] = v
    e = generato(genera(rows, report=True))
    riga = next(r for r in e.data.assumptions if r.label == "Liquidazioni TFR")
    assert riga.values == (D(1000), D(2000), D(3000))
    assert "Liquidazioni TFR" in _sez10(e)


def test_R2_durata_finanziamento_non_dedotta_dalle_rate():
    e = generato(genera(_con_prestito(), report=True))
    assert e.data.finanziamenti_tabella[0].durata_anni is None


def _con_prestito():
    rows = righe()
    rows[0]["financing_loans"] = [_FIN]
    return rows
