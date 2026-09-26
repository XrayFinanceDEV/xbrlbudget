"""Testi a regole del report infrannuale. Su AMBIENTA i numeri coincidono col riferimento, quindi le frasi del
committente fanno da specifica: qui se ne fissano le più importanti parola per parola."""
import dataclasses
from pathlib import Path

from app.renderers.infrannuale import narrative
from app.renderers.infrannuale.data import load_json

FIXTURE = Path(__file__).parent / "fixtures/infrannuale/banco_ambienta.json"


def _d():
    return load_json(FIXTURE)


def test_esito():
    assert narrative.esito(0.557) == "attenzione"
    assert narrative.esito(0.691) == "in soglia"
    assert narrative.esito(0.2) == "oltre soglia"
    assert narrative.esito(None) is None


def test_punti_chiave_come_il_riferimento():
    kp = dict(narrative.key_points(_d()))
    assert list(kp) == ["Ricavi in crescita.", "Marginalità stabile ma contenuta.", "Utile in aumento.",
                        "Indebitamento in crescita.", "Circolante assorbe liquidità.", "Classe di rischio."]
    assert kp["Ricavi in crescita."] == (
        "Il semestre chiude con ricavi delle vendite per € 2.104.755; il forecast 2026 è di € 4.109.510, +9,26% "
        "rispetto al consuntivo 2025 (€ 3.761.088).")
    assert kp["Indebitamento in crescita."] == (
        "La PFN sale da € 783.496 (2025 C) a € 960.883 (2026 F) e il rapporto PFN/EBITDA da 5,15× a 5,79×; il DSCR "
        "resta intorno a 2,9–3,0×.")
    assert kp["Classe di rischio."] == (
        "Classe D (Crisi) nel consuntivo 2025 e nel forecast 2026, C2 (Rischio grave) nel semestre; nessuno dei 7 "
        "segnali extracontabili è attivo.")


def test_forza_e_debolezza():
    forza, debolezza = narrative.strengths_weaknesses(_d())
    assert [f.title for f in forza] == ["Crescita dei ricavi", "Risultati in miglioramento",
                                        "Servizio del debito coperto", "Liquidità corrente in miglioramento",
                                        "Nessun segnale extracontabile"]
    assert [f.title for f in debolezza] == ["Classe di rischio D · Crisi", "Leva finanziaria elevata",
                                            "Redditività contenuta", "Sottocapitalizzazione", "Circolante e cassa",
                                            "Debiti previdenziali in aumento"]
    t = {f.title: f.text for f in forza + debolezza}
    assert t["Liquidità corrente in miglioramento"] == (
        "Da 1,162× a 1,283×; il margine di tesoreria passa da −€ 67.803 a +€ 109.797 e la copertura delle "
        "immobilizzazioni dal 106,20% al 154,83%.")
    assert t["Sottocapitalizzazione"] == (
        "Indipendenza finanziaria all'8,79% e margine di struttura negativo (−€ 253.424) nel forecast.")


def test_azioni_nell_ordine_del_riferimento():
    d = _d()
    _, debolezza = narrative.strengths_weaknesses(d)
    az = narrative.actions(d, debolezza)
    assert [a[0] for a in az] == ["Verificare il forecast del secondo semestre", "Accelerare gli incassi",
                                  "Presidiare la tesoreria di fine anno", "Ridurre la leva e riequilibrare le scadenze",
                                  "Rafforzare il patrimonio", "Monitorare i debiti previdenziali e tributari"]
    assert az[0][1] == ("Il forecast ipotizza servizi per € 1.432.482 contro € 1.872.482 annualizzati e personale per "
                        "€ 2.344.742 contro € 2.024.742 annualizzati: confrontare le stime con i dati contabili più "
                        "recenti.")


def test_letture():
    d = _d()
    assert narrative.lettura_circolante(d)[0] == (
        "Il circolante commerciale più che raddoppia rispetto al 2025, trainato dai crediti verso clienti (+55,69% "
        "entro 12 mesi e € 45.000 oltre 12 mesi).")
    assert narrative.lettura_costi(d)[0] == (
        "Nel semestre i servizi pesano il 44,48% dei ricavi (29,48% nel 2025) e il personale il 48,10% (62,38% nel "
        "2025): la composizione dei costi è cambiata rispetto al consuntivo.")


def test_senza_dati_non_si_scrive_nulla():
    d = _d()
    vuoto = dataclasses.replace(d, values={k: {c: None for c in v} for k, v in d.values.items()}, crisi={},
                                segnali=())
    assert narrative.key_points(vuoto) == []
    assert narrative.strengths_weaknesses(vuoto) == ([], [])
    assert narrative.actions(vuoto, []) == []
    assert narrative.lettura_costi(vuoto) == [] and narrative.lettura_circolante(vuoto) == []
