"""#60: un comparato stampato nel PDF che l'import non salva si dichiara, non sparisce."""
from importers.pdf_importer import _avviso_comparato_non_letto


def _avviso(**kw):
    base = dict(stampa_comparato=True, prior_imported=False, gia_avvisato=False, has_existing=False)
    base.update(kw)
    return _avviso_comparato_non_letto(2025, **base)


def test_comparato_stampato_e_non_importato_si_dichiara_con_l_anno():
    avviso = _avviso()
    assert avviso.startswith("ANNO PRECEDENTE NON IMPORTATO [2025]")
    assert "importa il bilancio 2025 a parte" in avviso


def test_con_un_anno_precedente_gia_presente_dice_che_resta_quello():
    avviso = _avviso(has_existing=True)
    assert "resta quello gia' presente per il 2025" in avviso
    assert "importa il bilancio" not in avviso


def test_nessun_avviso_se_il_documento_non_stampa_un_comparato():
    # un infrannuale monocolonna non ha un anno precedente da perdere
    assert _avviso(stampa_comparato=False) is None


def test_nessun_avviso_se_l_anno_precedente_e_stato_importato():
    assert _avviso(prior_imported=True) is None


def test_nessun_doppio_avviso_quando_il_precedente_e_gia_stato_scartato_con_motivo():
    assert _avviso(gia_avvisato=True) is None


def test_nessun_avviso_senza_anno_di_esercizio():
    assert _avviso_comparato_non_letto(
        None, stampa_comparato=True, prior_imported=False, gia_avvisato=False, has_existing=False
    ) is None
