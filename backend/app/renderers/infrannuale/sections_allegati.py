"""Allegati A–B: conto economico e stato patrimoniale completi, nel catalogo di righe del riferimento.

Il prospetto dettagliato del motore ha più righe di quelle che il committente stampa (intestazioni di sezione,
sotto-righe «entro 12 mesi» uguali al padre, il totale degli ammortamenti in coda). Qui le righe si scelgono per
codice e si rietichettano come nel riferimento; le voci a zero in tutti i periodi finiscono in una nota raggruppata
per categoria. Il catalogo è fisso: una voce che nel motore non esiste stampa «n.d.», non sparisce.
"""
from __future__ import annotations

from typing import Optional

from reportlab.platypus import PageBreak, Paragraph, Spacer, TableStyle

from app.renderers.business_plan import fmt, layout, theme
from app.renderers.business_plan.layout import ST, _ps

from .data import ANNUALIZZATO, INFRANNUALE, PROIEZIONE, STORICO, InfrannualeData

_TITLE = _ps("at", theme.REGULAR, 15, 18, theme.INK)
_SUB = _ps("as", theme.REGULAR, 9.8, 12, theme.INK)


def _head(eyebrow: str, title: str, sub: str) -> list:
    return [Paragraph(eyebrow, ST["eyebrow"]), Spacer(0, 2), Paragraph(title, _TITLE), Spacer(0, 2),
            Paragraph(sub, _SUB), Spacer(0, 6)]


class _Rows:
    """Righe d'allegato di un prospetto, lette per codice."""

    def __init__(self, annex, keys: list, var_col: str):
        self.by_code = {r.code: r.values for r in annex if r.code}
        self.keys, self.var_col = keys, var_col
        self.out: list = []

    def values(self, code: str) -> Optional[tuple]:
        return self.by_code.get(code)

    def nonzero(self, code: str) -> bool:
        vals = self.values(code)
        return vals is not None and any(v is not None and v != 0 for v in vals)

    def _var(self, vals) -> str:
        """Variazione sulla colonna C, ai centesimi come nel corpo; vuota (non «n.d.») se non ha senso."""
        if self.var_col not in self.keys:
            return ""
        b, v = vals[self.keys.index(STORICO)], vals[self.keys.index(self.var_col)]
        if b is None or v is None:
            return ""
        return fmt.pct((v / b - 1) * 100) if b else ""

    def row(self, code: Optional[str], label: str, style: str = "", indent: int = 0, vals: Optional[tuple] = None):
        vals = vals if vals is not None else (self.values(code) if code else None)
        if vals is None:
            vals = (None,) * len(self.keys)
        cells = [fmt.eur(v) for v in vals] + [self._var(vals)]
        self.out.append(("&nbsp;" * 3 * indent + label, cells, style))

    def group(self, label: str):
        self.out.append((label, [], "group"))


def _table(headers, rows, *, compact: bool):
    """Righe da 16,6 pt nel conto economico (intestazione 16,6), da 18,4 nello stato patrimoniale: misure del
    riferimento, pp. 11–13."""
    head = 3.05 if compact else 4.0
    t = layout.fin_table(headers, rows, first="Voce", value_size=9.8, label_size=7.6 if compact else 8.0,
                         pad=2.66 if compact else 3.55)
    t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, 0), head), ("BOTTOMPADDING", (0, 0), (-1, 0), head)]))
    if compact:  # intestazioni di gruppo da 12,8 pt
        for i, (_, _, kind) in enumerate(rows, start=1):
            if kind == "group":
                t.setStyle(TableStyle([("TOPPADDING", (0, i), (-1, i), 2.0), ("BOTTOMPADDING", (0, i), (-1, i), 2.0)]))
    return t


# ------------------------------------------------------------------ Allegato A
_CE_A = (("ce01_ricavi_vendite", "1) Ricavi delle vendite e delle prestazioni"),
         ("ce02_variazioni_rimanenze", "2) Variazioni rimanenze prodotti in corso, semilavorati e finiti"),
         ("ce03_lavori_interni", "3) Variazioni dei lavori in corso su ordinazione"),
         ("ce03a_incrementi_immobilizzazioni", "4) Incrementi di immobilizzazioni per lavori interni"),
         ("ce04_altri_ricavi", "5) Altri ricavi e proventi"))
_CE_B = (("ce05_materie_prime", "6) Materie prime, sussidiarie, di consumo e merci", 0),
         ("ce06_servizi", "7) Servizi", 0), ("ce07_godimento_beni", "8) Godimento di beni di terzi", 0),
         ("ce08_costi_personale", "9) Personale", 0), ("ce08b_salari_stipendi", "a) Salari e stipendi", 1),
         ("ce08c_oneri_sociali", "b) Oneri sociali", 1), ("ce08a_tfr_accrual", "c) Trattamento di fine rapporto", 1),
         ("d_trattamento_di_quiescenza_e_simili", "d) Trattamento di quiescenza e simili", 1),
         ("ce08d_altri_costi_personale", "e) Altri costi del personale", 1),
         ("ce09_ammortamenti", "10) Ammortamenti e svalutazioni", 0),
         ("ce09a_ammort_immateriali", "a) Amm.to immobilizzazioni immateriali", 1),
         ("ce09b_ammort_materiali", "b) Amm.to immobilizzazioni materiali", 1),
         ("ce09c_svalutazioni", "c) Altre svalutazioni delle immobilizzazioni", 1),
         ("ce09d_svalutazione_crediti", "d) Svalutazione crediti e disponibilità liquide", 1),
         ("ce10_var_rimanenze_mat_prime", "11) Variazioni rimanenze materie prime, sussidiarie, di consumo e merci", 0),
         ("ce11_accantonamenti", "12) Accantonamenti per rischi", 0),
         ("ce11b_altri_accantonamenti", "13) Altri accantonamenti", 0),
         ("ce12_oneri_diversi", "14) Oneri diversi di gestione", 0))
_CE_C = (("ce13_proventi_partecipazioni", "15) Proventi da partecipazioni"),
         ("ce14_altri_proventi_finanziari", "16) Altri proventi finanziari"),
         ("ce15_oneri_finanziari", "17) Interessi e altri oneri finanziari"),
         ("ce16_utili_perdite_cambi", "17-bis) Utili e perdite su cambi"))
#: sezioni D ed E: (totale, etichetta, dettaglio, frase della nota quando il dettaglio è tutto a zero)
_CE_DE = (("ce17_rettifiche_attivita_fin", "D) RETTIFICHE DI VALORE DI ATTIVITÀ FINANZIARIE",
           (("ce17a_rivalutazioni", "18) Rivalutazioni"), ("ce17b_svalutazioni", "19) Svalutazioni")),
           "D) voci 18–19"),
          ("extraordinary_result", "E) PROVENTI E ONERI STRAORDINARI",
           (("ce18_proventi_straordinari", "20) Proventi straordinari"),
            ("ce19_oneri_straordinari", "21) Oneri straordinari")), "E) voci 20–21"))


def allegato_a(d: InfrannualeData, pages: dict) -> list:
    keys = [c.key for c in d.ce_cols]
    var_col = ANNUALIZZATO if d.has_annualized else PROIEZIONE
    r = _Rows(d.annex_ce, keys, var_col)
    r.group("A) VALORE DELLA PRODUZIONE")
    for code, label in _CE_A:
        r.row(code, label)
    r.row("production_value", "Totale valore della produzione", "bold")
    r.group("B) COSTI DELLA PRODUZIONE")
    for code, label, level in _CE_B:
        r.row(code, label, indent=level)
    r.row("production_cost", "Totale costi della produzione", "bold")
    r.row("ebitda", "EBITDA (MOL)", "hl")
    r.row("ebit", "EBIT (risultato operativo)")
    r.group("C) PROVENTI E ONERI FINANZIARI")
    for code, label in _CE_C:
        r.row(code, label)
    r.row("financial_result", "Totale proventi/oneri finanziari", "bold")
    zero_sections = []
    for total, label, detail, phrase in _CE_DE:
        r.row(total, label, "bold")
        if any(r.nonzero(code) for code, _ in detail):
            for code, lab in detail:
                r.row(code, lab, indent=1)
        else:
            zero_sections.append(phrase)
    r.row("profit_before_tax", "Risultato prima delle imposte", "bold")
    r.row("ce20_imposte", "22) Imposte sul reddito")
    r.row("net_profit", "23) Utile (perdita) dell'esercizio", "hl")
    sub = "Valori in euro · schema civilistico"
    if zero_sections:
        sub += " · " + " ed ".join(zero_sections) + " pari a zero"
    sub += " · n.d. = non disponibile."
    heads = [c.label for c in d.ce_cols] + [f"{'Ann.' if var_col == ANNUALIZZATO else 'F'} / C"]
    return _head("ALLEGATO A", "Conto economico completo", sub) + [_table(heads, r.out, compact=True)]


# ------------------------------------------------------------------ Allegato B
_IMMOB_FIN = (("sp04a_partecipazioni", "1) Partecipazioni", "partecipazioni"),
              ("sp04b_crediti_immob_breve+sp04c_crediti_immob_lungo", "2) Crediti immobilizzati", "crediti immobilizzati"),
              ("sp04d_altri_titoli", "3) Altri titoli", "altri titoli"),
              ("sp04e_strumenti_derivati_attivi", "4) Strumenti finanziari derivati attivi", "derivati attivi"))
_RIMANENZE = (("sp05a_materie_prime", "materie prime"), ("sp05b_prodotti_in_corso", "prodotti in corso"),
              ("sp05c_lavori_in_corso", "lavori in corso"), ("sp05d_prodotti_finiti", "prodotti finiti"),
              ("sp05e_acconti", "acconti"))
_CREDITI = (("a_crediti_clienti", "Clienti"), ("b_crediti_controllate", "Controllate"),
            ("c_crediti_collegate", "Collegate"), ("d_crediti_controllanti", "Controllanti"),
            ("e_crediti_tributari", "Crediti tributari"), ("f_imposte_anticipate", "Imposte anticipate"),
            ("g_crediti_altri", "Altri"))
_CREDITI_CODES = {k: (f"sp06{k[0]}_{k[2:]}_breve", f"sp07{k[0]}_{k[2:]}_lungo") for k, _ in _CREDITI}
_RISERVE = (("sp12a_riserva_sovrapprezzo", "Sovrapprezzo azioni", "sovrapprezzo"),
            ("sp12b_riserve_rivalutazione", "Rivalutazione", "rivalutazione"),
            ("sp12c_riserva_legale", "Riserva legale", "riserva legale"),
            ("sp12d_riserve_statutarie", "Riserve statutarie", "riserve statutarie"),
            ("sp12e_altre_riserve", "Altre riserve", "altre riserve"),
            ("sp12f_riserva_copertura_flussi", "Copertura flussi", "copertura flussi"),
            ("sp12h_riserva_neg_azioni_proprie", "Riserva negativa azioni proprie", "azioni proprie"))
_FONDI = (("sp14a_fondi_trattamento_quiescenza", "Quiescenza", "fondi di quiescenza"),
          ("sp14b_fondi_imposte", "Imposte, anche differite", "imposte"),
          ("sp14c_strumenti_derivati_passivi", "Derivati passivi", "derivati passivi"),
          ("sp14d_altri_fondi", "Altri fondi", "altri fondi"))
_DEBITI = (("sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo", "Debiti verso banche"),
           ("sp16b_debiti_altri_finanz_breve", "sp17b_debiti_altri_finanz_lungo", "Debiti verso altri finanziatori"),
           ("sp16c_debiti_obbligazioni_breve", "sp17c_debiti_obbligazioni_lungo", "Obbligazioni"),
           ("sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo", "Debiti verso fornitori"),
           ("sp16e_debiti_tributari_breve", "sp17e_debiti_tributari_lungo", "Debiti tributari"),
           ("sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo", "Debiti previdenziali"),
           ("sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo", "Altri debiti"))


def _elenco(nomi: list, e_finale: bool) -> str:
    if len(nomi) > 1 and e_finale:
        return ", ".join(nomi[:-1]) + " e " + nomi[-1]
    return ", ".join(nomi)


def allegato_b(d: InfrannualeData, pages: dict) -> list:
    keys = [c.key for c in d.sp_cols]
    var_col = PROIEZIONE if d.has_forecast else INFRANNUALE
    heads = [c.label for c in d.sp_cols] + [f"{'F' if var_col == PROIEZIONE else '6M'} / C"]
    r = _Rows(d.annex_sp, keys, var_col)
    nota: list = []

    # ---- attivo
    r.group("ATTIVO")
    r.row("sp01_crediti_soci", "A) Crediti verso soci per versamenti ancora dovuti")
    r.row("sp02_immob_immateriali", "I – Immobilizzazioni immateriali")
    r.row("sp03_immob_materiali", "II – Immobilizzazioni materiali")
    r.row("sp04_immob_finanziarie", "III – Immobilizzazioni finanziarie")
    zero = []
    for code, label, nome in _IMMOB_FIN:
        if r.nonzero(code):
            r.row(code, label, indent=1)
        else:
            zero.append(nome)
    if zero:
        nota.append(_elenco(zero, False))
    r.row("fixed_assets", "B) Totale immobilizzazioni", "bold")
    rim_nz = [(c, n) for c, n in _RIMANENZE if r.nonzero(c)]
    if len(rim_nz) == 1:
        r.row("sp05_rimanenze", f"I – Rimanenze ({rim_nz[0][1]})")
    else:
        r.row("sp05_rimanenze", "I – Rimanenze")
        for c, n in rim_nz:
            r.row(c, n.capitalize(), indent=1)
    rim_zero = [n for c, n in _RIMANENZE if not r.nonzero(c)]
    if len(rim_nz) == 1 and rim_nz[0][0] == "sp05a_materie_prime":
        nota.append("rimanenze diverse dalle materie prime")
    elif rim_zero and rim_nz:
        nota.append("rimanenze di " + _elenco(rim_zero, True))
    for side, code, label in ((0, "sp06_crediti_breve", "II – Crediti entro 12 mesi"),
                              (1, "sp07_crediti_lungo", "II – Crediti oltre 12 mesi")):
        r.row(code, label)
        for k, nome in _CREDITI:
            c = _CREDITI_CODES[k][side]
            if r.nonzero(c):
                r.row(c, nome, indent=1)
    gruppo = [nome.lower() for k, nome in _CREDITI[1:4] if not any(r.nonzero(c) for c in _CREDITI_CODES[k])]
    if gruppo:
        nota.append("crediti verso " + _elenco(gruppo, True))
    if not any(r.nonzero(c) for c in _CREDITI_CODES["f_imposte_anticipate"]):
        nota.append("imposte anticipate")
    r.row("sp08_attivita_finanziarie", "III – Attività finanziarie non immobilizzate")
    r.row("sp09_disponibilita_liquide", "IV – Disponibilità liquide")
    r.row("current_assets", "C) Totale attivo circolante", "bold")
    r.row("sp10_ratei_risconti_attivi", "D) Ratei e risconti attivi")
    r.row("total_assets", "TOTALE ATTIVO", "hl")
    attivo, r.out = r.out, []

    # ---- passivo
    r.group("PASSIVO E PATRIMONIO NETTO")
    r.row("sp11_capitale", "I – Capitale")
    zero = []
    for code, label, nome in _RISERVE:
        if r.nonzero(code):
            r.row(code, label)
        else:
            zero.append(nome)
    if zero:
        nota.append(_elenco(zero, False))
    r.row("sp12g_utili_perdite_portati", "Utili/perdite portati a nuovo")
    r.row("sp13_utile_perdita", "IX – Utile (perdita) dell'esercizio")
    r.row("sp11_capitale+sp12_riserve+sp13_utile_perdita", "A) Totale patrimonio netto", "bold")
    r.row("sp14_fondi_rischi", "B) Fondi per rischi e oneri")
    zero = []
    for code, label, nome in _FONDI:
        if r.nonzero(code):
            r.row(code, label, indent=1)
        else:
            zero.append(nome)
    if zero:
        nota.append(_elenco(zero, True))
    r.row("sp15_tfr", "C) Trattamento di fine rapporto")
    for breve, lungo, label in _DEBITI:
        total = f"{breve}+{lungo}"
        b, l = r.nonzero(breve), r.nonzero(lungo)
        if b and l:
            r.row(total, label)
            r.row(breve, "entro 12 mesi", indent=1)
            r.row(lungo, "oltre 12 mesi", indent=1)
        elif b or l:
            r.row(total, f"{label} ({'entro' if b else 'oltre'} 12 mesi)")
        else:
            r.row(total, label)
    r.row("sp16_debiti_breve+sp17_debiti_lungo", "D) Totale debiti", "bold")
    r.row("sp18_ratei_risconti_passivi", "E) Ratei e risconti passivi")
    tot = next((x.values for x in d.annex_sp if x.label.upper().startswith("TOTALE PASSIVO")), None)
    diff = next((x.values for x in d.annex_sp if x.label.upper().startswith("DIFFERENZA")), None)
    r.row(None, "TOTALE PASSIVO E PATRIMONIO NETTO", "hl", vals=tot)
    r.row(None, "Differenza (attivo − passivo)", vals=diff)
    passivo = r.out

    s = _head("ALLEGATO B", "Stato patrimoniale completo",
              "Valori in euro · saldi puntuali · voci a zero in tutti i periodi raggruppate in nota.")
    s += [_table(heads, attivo, compact=False), PageBreak()]
    s += _head("ALLEGATO B", "Stato patrimoniale completo (segue)", "Passivo e patrimonio netto · valori in euro.")
    s += [_table(heads, passivo, compact=False)]
    if nota:
        s += [Spacer(0, 5), layout.note("Voci pari a zero in tutti i periodi: " + "; ".join(nota) + ".")]
    return s
