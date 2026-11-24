"""Regole a parole chiave: dalla descrizione di un conto alla voce IV CEE, tipi di debito e credito, ripieghi.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from decimal import Decimal
from typing import List, Optional
from importers.rimanenze_ce import e_conto_rimanenze, natura_rimanenze
from importers.situazione_contabile.fondi import (
    _fondo_is_immat, _is_fondo_amm,
)


# ---------------------------------------------------------------------------
# Keyword-based classification rules
# ---------------------------------------------------------------------------
# Each rule is (keywords_to_match, iv_cee_field_or_action)
# Keywords are matched against uppercased description text.
# Rules are tried in order; first match wins.

def _kw_match(desc_upper: str, keywords: List[str]) -> bool:
    """Check if ALL keywords appear in the description."""
    return all(kw in desc_upper for kw in keywords)

def _kw_any(desc_upper: str, keywords: List[str]) -> bool:
    """Check if ANY keyword appears in the description."""
    return any(kw in desc_upper for kw in keywords)

# SP ATTIVO keyword rules: (keywords, field)
# Matched against sub2/sub3 descriptions in the ATTIVO section
_SP_ATTIVO_RULES = [
    # Fixed assets (gross — will be netted against depreciation)
    (['IMMOBILIZZAZIONI IMMATERIALI'], 'gross_sp02'),
    (['IMMOBILIZZAZIONI MATERIALI'], 'gross_sp03'),
    (['IMMOBILIZZAZIONI FINANZIARIE'], 'gross_sp04'),
    # "IMMOBILIZZI FINANZIARI" (budget_680): senza questa regola vinceva MOBILI, che e'
    # sottostringa di IMMOBILIZZI, e i depositi cauzionali diventavano arredi
    (['IMMOBILIZZI', 'FINANZ'], 'gross_sp04'),
    # Immobilizzazioni in corso e acconti (B.II.5 / B.I.6) — a LEGITIMATE fixed
    # asset. Must precede the ANTICIP rule below so a real immob. acconto is not
    # demoted to a credit.
    (['IMMOBILIZZAZIONI', 'CORSO'], 'gross_sp03'),
    (['IMMOBILIZZAZIONI', 'ACCONT'], 'gross_sp03'),
    # Credits explicitly labelled as immobilised belong to B.III even when the
    # account number is gestionale-specific (AGO: "Crediti v/altri (EE-immob.)").
    # non 'IMMOB' da solo: "Crediti vs. Ad Immobiliare" e' un credito (M.C.T. 30/06/2026)
    (['CREDITI', 'IMMOBILIZZ'], 'gross_sp04'),
    (['CREDITI', 'IMMOB.'], 'gross_sp04'),
    (['CREDITI', 'IMMOBILE'], 'gross_sp04'),          # "Crediti per acquisto immobile" (AITEC)
    # An advance on a CANONE / lease ("ANTICIPO X CANONI MACCHINARI") is a credit,
    # not the machine — must precede the MACCHINAR category rule. Narrow to CANON on
    # purpose: a blanket ANTICIP rule would (a) demote a genuine acconto to PURCHASE
    # a cespite ("ANTICIPI SU MACCHINARI" = B.II.5 immobilizzazione) to crediti, and
    # (b) leak into _semantic_section_from_desc, mis-guessing customer advances
    # ("CLIENTI C/ANTICIPI" = a liability) onto the asset side. Generic supplier
    # advances ("ANTICIPI A FORNITORI") already fall to the sp06 default below.
    (['ANTICIP', 'CANON'], 'sp06'),
    # AGO-style single-category descriptions (trial balance parent level)
    (['ONERI', 'PLURIENN'], 'gross_sp02'),
    (['COSTI', 'PLURIENN'], 'gross_sp02'),
    (['COSTI', 'IMPIANTO'], 'gross_sp02'),
    (['COSTI', 'AMPLIAMENT'], 'gross_sp02'),   # B.I.1 e' "costi di impianto E DI AMPLIAMENTO"
    (['SOFTWARE'], 'gross_sp02'),
    (['BREVETT'], 'gross_sp02'),
    (['MARCHI'], 'gross_sp02'),
    (['AVVIAMENTO'], 'gross_sp02'),
    (['LICENZ'], 'gross_sp02'),
    # B.I.7 "costi su beni di terzi" (migliorie/lavori su beni non di proprieta').
    # Il repo lo tratta gia' come IMMATERIALE sul lato fondo (regola F.DO+AMM+MANUT
    # "spese di manut.beni di ter(zi)"); senza la regola simmetrica qui il cespite
    # finiva nei crediti mentre il suo fondo nettava le immobilizzazioni MATERIALI
    # (budget_281: 4.500,00 in sp06 e 2.471,86 sottratti a sp03).
    (['BENI DI TERZ'], 'gross_sp02'),
    # Oneri pluriennali scritti per esteso (budget_367: "Altre spese ad utilita'
    # pluriennale", "Manutenzioni e riparazioni da ammortizzare", "Disaggi su
    # prestiti" — quest'ultimo gia' immateriale lato fondo, _FONDO_IMMAT_KW):
    # finivano nel default crediti.
    (['SPESE', 'PLURIENN'], 'gross_sp02'),
    (['DA AMMORTIZZ'], 'gross_sp02'),
    (['DISAGG'], 'gross_sp02'),
    (['CONTENITOR'], 'gross_sp03'),
    (['FABBRICAT'], 'gross_sp03'),
    (['TERREN'], 'gross_sp03'),
    (['MACCHINAR'], 'gross_sp03'),
    (['MACCHINE'], 'gross_sp03'),
    (['IMPIANT'], 'gross_sp03'),
    # 'ATTREZ' e non 'ATTREZZ': "ATTREZ." compare troncato nelle stampe a colonna
    # stretta. Allargamento per PREFISSO, quindi additivo (ogni ATTREZZ contiene ATTREZ).
    (['ATTREZ'], 'gross_sp03'),
    (['ATTR', 'MINUT'], 'gross_sp03'),   # "ATTR.VARIE E MINUTE (<516,46 E.)"
    # Categorie di cespite gia' riconosciute lato FONDO (_FONDO_CATEGORY_KW) ma
    # assenti qui: il fondo nettava sp03 mentre il suo cespite finiva nei crediti.
    (['TELEFON'], 'gross_sp03'),
    (['AUTOMEZZ'], 'gross_sp03'),
    (['AUTOVEICOL'], 'gross_sp03'),
    (['AUTOVETTUR'], 'gross_sp03'),
    (['AUTOCARR'], 'gross_sp03'),                 # budget_238: finiva nei crediti
    # budget_680: sigle e categorie che nessuna regola riconosceva
    (['MACCHIN/'], 'gross_sp03'),
    (['MACC.', 'IMP'], 'gross_sp03'),
    (['HARDWARE'], 'gross_sp03'),
    (['CELLULAR'], 'gross_sp03'),
    (['CENTRALINO'], 'gross_sp03'),
    (['COSTRUZIONI', 'LEGGER'], 'gross_sp03'),
    (['CERTIFICAZION'], 'gross_sp02'),
    # beni strumentali sotto 516,46 euro ("BENI DI VALORE UNITARIO INFERIORE")
    (['BENI', 'VALORE', 'INFERIOR'], 'gross_sp03'),
    (['CESPITI'], 'gross_sp03'),                 # "CESPITI INFERIORI A € 516,45" (Santini)
    (['MEZZI', 'TRASP'], 'gross_sp03'),
    (['AUTO', 'MOTO'], 'gross_sp03'),
    (['ARREDAMENT'], 'gross_sp03'),
    (['MOBILI'], 'gross_sp03'),
    (['ALTRI', 'BENI', 'MATERIAL'], 'gross_sp03'),
    (['PARTECIPAZ'], 'gross_sp04'),
    # Current assets
    (['RIMANENZE'], 'sp05'),
    (['MAGAZZIN'], 'sp05'),
    # Common trial-balance abbreviation: "Rim. mat. prime, sussid. e consumo".
    (['RIM', 'MAT', 'PRIM'], 'sp05'),
    (['GIACENZ'], 'sp05'),                       # "COLORANTI/GIACENZE" (budget_680)
    (['RATEI', 'RISCONTI', 'ATTIV'], 'sp10'),
    (['RATEI', 'ATTIV'], 'sp10'),
    (['RISCONTI', 'ATTIV'], 'sp10'),
    (['DISPONIBILIT'], 'sp09'),  # Disponibilità liquide (banks + cash)
    (['DEPOSIT', 'BANCAR'], 'sp09'),
    (['DEPOSIT', 'POSTAL'], 'sp09'),
    (['DENARO'], 'sp09'),
    (['CASSA'], 'sp09'),
    # conto corrente bancario a saldo dare (budget_680: "BANCA DI ASTI C/C...", mastro
    # "BANCHE"); a saldo avere sta nel passivo e lo leggono le regole di debito. Prima i
    # crediti che nominano una banca ("CREDITI V/BANCHE PER RIMBORSO CARTA", AIC) e
    # l'erario ("ritenute su C/C bancari", MBS): restano crediti, come prima.
    (['CREDIT'], 'sp06'),
    (['ERARIO'], 'sp06'),
    (['DEBIT'], 'sp06'),        # "DEBITI V/BANCHE" stampato all'attivo (AIC): come prima
    (['BANCA ', 'C/C'], 'sp09'),
    (['BANCHE'], 'sp09'),
    # Everything else in attivo = crediti (sp06)
]
# SP PASSIVO keyword rules
_SP_PASSIVO_RULES = [
    # B.1 funds are not depreciation contra-accounts.  Keep these before every
    # AMM rule: "amministratori" contains the substring "AMM" and previously
    # made a fondo fine-mandato look like a tangible depreciation fund.
    (['QUIESCENZA'], 'sp14'),
    (['INDENNIT', 'MANDATO'], 'sp14'),
    (['FINE', 'MANDATO'], 'sp14'),               # "F.DO TRATT.FINE MANDATO(TFM)"
    (['T.F.M'], 'sp14'),                          # "F.DO T.F.M. AMMINISTRATORE" (Santini)
    # "F.DO INDENNITA' ANZIANITA' DIPEND." e' il TFR col nome di prima del 1982
    (['INDENNIT', 'ANZIANIT'], 'sp15'),
    # Depreciation funds (will be netted against gross assets)
    # Specific rules first (pluriennali/macchine disambiguate immat vs mat)
    (['F.DO', 'AMM', 'PLURIENN'], 'depr_sp02'),
    (['F.DO', 'AMM', 'IMMAT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'SOFTWARE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'BREVETT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'MARCHI'], 'depr_sp02'),
    (['F.DO', 'AMM', 'AVVIAMENTO'], 'depr_sp02'),
    # Truncated gestionale captions (budget_343/348, Bilancino 31-5-26): the
    # column clips the description, so the canonical keywords above never fire
    # and the fondo fell through to the tangible fallback.
    (['F.DO', 'AMM', 'SW'], 'depr_sp02'),                  # "F.do amm.sw in concessione capitalizz"
    (['F.DO', 'AMM', 'COSTI DI IMPIANTO'], 'depr_sp02'),   # B.I.1, before the IMPIANT→sp03 rule
    (['F.DO', 'AMM', "COSTI D'IMPIANTO"], 'depr_sp02'),
    (['F.DO', 'AMM', 'AMPLIAMENT'], 'depr_sp02'),          # idem B.I.1 (budget_158 CONA)
    (['F.DO', 'AMM', 'MANUT'], 'depr_sp02'),               # "spese di manut.beni di ter(zi)" B.I.7
    (['F.DO', 'AMM', 'BENI DI TERZ'], 'depr_sp02'),        # idem, grafia "lav. str. su beni di terzi"
    (['F.DO', 'AMM', 'LICENZE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'OPERE INGE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'CERTIFICAZ'], 'depr_sp02'),           # budget_680, B.I immateriale          # "F.do amm.dir.brev.e utilizz.opere inge"
    (['F.DO', 'AMM', 'DIR.BREV'], 'depr_sp02'),
    (['F.DO', 'AMM', 'RICERCA'], 'depr_sp02'),             # B.I.2 sviluppo (Santini)
    (['F.DO', 'AMM', 'DIRITTI'], 'depr_sp02'),             # "F.DO AMM.TO DIRITTI UTILIZZO" (budget_1343)
    (['F.DO', 'AMM', 'SVILUPPO'], 'depr_sp02'),
    (['FOND', 'AMM', 'IMMOBILIZZAZ. IMM'], 'depr_sp02'),   # mastro "FONDI AMMORT. IMMOBILIZZAZ. IMM"
    (['F.DO', 'AMM', 'MACCHINE'], 'depr_sp03'),
    (['F.DO', 'AMM', 'MACCHINAR'], 'depr_sp03'),
    (['F.DO', 'AMM', 'IMPIANT'], 'depr_sp03'),
    (['F.DO', 'AMM', 'ATTREZZ'], 'depr_sp03'),
    (['F.DO', 'AMM', 'AUTO'], 'depr_sp03'),
    (['F.DO', 'AMM', 'FABBRICAT'], 'depr_sp03'),
    (['F.DO', 'AMM', 'MATER'], 'depr_sp03'),
    (['F/AMM', 'IMMAT'], 'depr_sp02'),
    (['F/AMM', 'MATER'], 'depr_sp03'),
    (['AMMORTAM', 'IMMAT'], 'depr_sp02'),
    (['AMMORTAM', 'MATER'], 'depr_sp03'),
    # "FONDI/FONDO AMM.TO IMMOB. (IM)MATERIALI" — no 'F.DO' token, 'AMM.TO' not 'AMMORTAM'
    # (BILAGRA "BILANCIO DI VERIFICA", e.g. AITEC). IMMAT must precede MATER because
    # "IMMATERIALI" also contains the "MATER" substring.
    (['FOND', 'AMM', 'IMMAT'], 'depr_sp02'),
    (['FOND', 'AMM', 'MATER'], 'depr_sp03'),
    # Safe tangible fallback.  Do not use bare "AMM": it also matches words
    # such as AMMINISTRATORI.  Real depreciation captions use AMM. / AMM.TO or
    # the full AMMORT... stem; asset-specific cases were handled above.
    (['F.DO', 'AMM.'], 'depr_sp03'),
    (['F.DO', 'AMMORT'], 'depr_sp03'),
    # Crediti deduction
    (['F.DO', 'SVAL', 'CREDITI'], 'deduct_crediti'),
    (['RISCHI', 'CREDITI'], 'deduct_crediti'),
    (['SVALUT', 'CREDITI'], 'deduct_crediti'),
    # Banks avere = overdrafts
    (['DISPONIBILIT'], 'bank_avere'),
    # Equity (sub2 total and sub3 components)
    (['PATRIMONIO NETTO'], 'equity_total'),
    (['UTILI', 'DESTINAZ'], 'equity_total'),      # "Utili in attesa di destinaz." (Napolitano)
    (['CAPITALE'], 'equity_total'),
    (['RISERVA'], 'equity_total'),
    (['RISERVE'], 'equity_total'),
    (['UTILE', 'ESERCIZ'], 'equity_total'),
    (['PERDITA', 'ESERCIZ'], 'equity_total'),
    (['UTILI', 'PORTATI'], 'equity_total'),
    (['UTILI', 'NUOVO'], 'equity_total'),
    (['PERDITE', 'PORTATE'], 'equity_total'),
    (['SOVRAPPREZZO'], 'equity_total'),
    (['CAP.', 'SOC'], 'equity_total'),
    # Fondi
    (['FONDI', 'RISCHI'], 'sp14'),
    (['FONDI', 'ONERI'], 'sp14'),
    (['FONDO', 'RISCHI'], 'sp14'),
    (['FONDO', 'ONERI'], 'sp14'),
    # TFR. L'imposta sostitutiva sul TFR e' un debito tributario, non il fondo: dentro un mastro
    # tributari-previdenza (budget_210, 1757) "ERARIO C/IMP.SOST.TFR" finiva in sp15.
    (['ERARI', 'TFR'], 'sp16'),
    (['SOST', 'TFR'], 'sp16'),
    (['TFR'], 'sp15'),
    (['T.F.R'], 'sp15'),
    (['TRATTAMENTO', 'FINE', 'RAPPORTO'], 'sp15'),
    (['TRATT', 'FINE', 'RAPPORTO'], 'sp15'),
    # Debiti v/banche (need entro/oltre split — from details OR from "(EE)"/"(OE)" suffix)
    (['DEBITI', 'BANCH'], 'debt_bank'),
    (['DEBITI', 'FINANZIAT'], 'debt_bank'),
    (['DEBITI', 'V/FINANZ'], 'debt_bank'),      # "DEBITI V/FINANZ.ESIG.ENTRO 12M" (budget_1401): anticipi factoring compresi
    (['MUTUI'], 'debt_bank'),
    # Santini: "FINANZIAMENTO 07797790 BANCO BPM", "ANTICIPI ESTERO BPER" sotto
    # "ANTICIPI BANCARI", un conto bancario a saldo avere sotto "BANCHE"
    (['FINANZIAMENT', 'SOCI'], 'sp16'),          # un socio non e' una banca: resta sp16b
    (['FINANZIAMENT', 'TERZI'], 'sp16'),         # "FINANZIAMENTI DI TERZI" (AITEC): idem
    (['FINANZIAMENT'], 'debt_bank'),
    (['ANTICIP', 'BANC'], 'debt_bank'),
    (['BANCHE'], 'debt_bank'),
    (['OBBLIGAZION'], 'debt_bank'),
    # Ratei e risconti passivi
    (['RATEI', 'RISCONTI', 'PASSIV'], 'sp18'),
    (['RATEI', 'PASSIV'], 'sp18'),
    (['RISCONTI', 'PASSIV'], 'sp18'),
    # Debiti tributari
    (['DEBITI', 'TRIBUTAR'], 'sp16'),
    (['DEBITI', 'TRIBUTARI'], 'sp16'),
    # Debiti previdenziali
    (['DEBITI', 'PREV'], 'sp16'),
    (['DEBITI', 'SICUR'], 'sp16'),
    (['DEBITI', 'INPS'], 'sp16'),
    (['ISTIT', 'PREV'], 'sp16'),
    # Specific debt categories → sp16 (breve by default)
    (['DEBITI', 'FORNITOR'], 'sp16'),
    (['ACCONTI'], 'sp16'),
    (['ALTRI DEBITI'], 'sp16'),
    (['ALTRI', 'DEBITI'], 'sp16'),
    # SBF / crediti ceduti in passivo → sp16 (only when explicitly labeled as ceded)
    (['CREDITI', 'CEDUT'], 'sp16'),
    (['CREDITI', 'SMOBIL'], 'sp16'),
]
# CE keyword rules for COSTI section
_CE_COSTI_RULES = [
    (['RIM.INIZ'], 'ce10'),
    (['RIMAN', 'INIZ'], 'ce10'),                 # "RIMAN. INIZIALI MAT. PRIME/MER" (budget_1343)
    (['ESISTENZE', 'INIZIAL'], 'ce10'),
    (['RIMANENZE', 'INIZIAL'], 'ce10'),
    (['RICAVI'], 'ce01_return'),  # Returns/discounts in cost section
    # Variazioni rimanenze MUST be before materie prime (descriptions often contain "MERCI")
    (['VARIAZ', 'RIMANENZ'], 'ce10'),
    (['VAR.RIM'], 'ce10'),
    # Materie prime / merci
    (['MATERIE PRIME'], 'ce05'),
    (['MATERIE', 'CONSUMO'], 'ce05'),
    (['COSTI', 'MAT'], 'ce05'),  # "COSTI P/MAT.PRI,SUSS.,CON.E MER."
    # "COSTI COMMERCIALI", "CONSULENZE COMMERCIALI": MERCI e' una sottostringa di
    # COMMERCIALI, e provvigioni e trasporti finivano fra le materie (Santini)
    (['COMMERCIAL'], 'ce06'),
    (['MERCI'], 'ce05'),
    (['MAT.PRI'], 'ce05'),
    (['ACQUISTI', 'DI BENI'], 'ce05'),           # B.6 (mastro "55 ACQUISTI DI BENI", Nicole)
    (['SERVIZI'], 'ce06'),
    # compensi e contributi degli amministratori: B.7 servizi, non personale
    (['AMMINISTRATOR'], 'ce06'),
    (['GODIMENTO', 'BENI'], 'ce07'),
    # Personale sub-fields (more specific than the generic 'PERSONALE' bucket)
    (['QUOTE', 'FINE', 'RAPPORTO'], 'ce08a_tfr'),
    (['QUOTE', 'TRATTAMENTO'], 'ce08a_tfr'),
    (['QUOTE', 'TFR'], 'ce08a_tfr'),
    (['QUOTA', 'TFR'], 'ce08a_tfr'),
    (['QUOTA', 'T.F.R'], 'ce08a_tfr'),
    # compensi e contributi del consiglio di amministrazione: B.7 come gli amministratori
    ([' CDA'], 'ce06'),
    (['ACCANTON', 'TFR'], 'ce08a_tfr'),
    (['TRATT', 'FINE', 'RAPPORTO'], 'ce08a_tfr'),
    (['SALARI'], 'ce08b'),
    (['STIPENDI'], 'ce08b'),
    (['ONERI', 'SOCIAL'], 'ce08c'),
    (['ONERI', 'PREVIDENZ'], 'ce08c'),
    (['ALTRI', 'COSTI', 'PERSONALE'], 'ce08d'),
    (['PERSONALE'], 'ce08'),
    # Ammortamenti (more specific keywords first)
    (['AMMORTAM', 'IMMAT'], 'ce09a'),
    (['AMM.TO', 'IMMAT'], 'ce09a'),
    (['AMM.T', 'IMM. IMMAT'], 'ce09a'),
    (['AMM.TI', 'IMMAT'], 'ce09a'),
    (['AMMORTAM', 'MATER'], 'ce09b'),
    (['AMM.TO', 'MATER'], 'ce09b'),
    (['AMM.T', 'IMM. MAT'], 'ce09b'),
    (['AMM.TO', 'MAT'], 'ce09b'),
    (['SVALUT'], 'ce09d'),  # Svalutazioni
    (['ACCANTONAM', 'RISCHI'], 'ce11'),
    (['ALTRI ACCANTONAM'], 'ce11b'),
    (['ONERI DIVERSI'], 'ce12'),
    (['ONERI', 'DIVERSI', 'GESTIONE'], 'ce12'),
    (['INTERESSI'], 'ce15'),
    (['ONERI', 'FINANZ'], 'ce15'),
    (['ON.FIN'], 'ce15'),
    (['INT. PASS'], 'ce15'),
    (['INT.PASS'], 'ce15'),                      # "INT.PASS.FINANZ.CREDEM" (budget_680)
    (['IMPOSTE', 'REDDITO'], 'ce20'),
    (['IMPOSTE', 'ESERC'], 'ce20'),
    (['IMPOSTE', 'ANTICIP'], 'ce20'),
    (['IMPOSTE', 'DIFFER'], 'ce20'),
    (['IRES'], 'ce20'),
    (['IRAP'], 'ce20'),
    # "DIFF.CAMBIO PASSIVO": C.17-bis. Mai CAMBI da solo: e' dentro "SCAMBIO SUL POSTO"
    (['DIFF', 'CAMBI'], 'ce16_cost'),
    (['SU CAMBI'], 'ce16_cost'),
    # Proventi/oneri straordinari in costs
    (['ONERI STRAORD'], 'ce19'),
    (['PROVENTI', 'PARTECIP'], 'ce13_cost'),
    # Ultime, solo se nient'altro riconosce la voce: mastri B.7 di quel gestionale
    # ("PRESTAZIONI DI LAVORO NON DIPEN(DENTE)", "GESTIONE VEICOLI AZIENDALI", "SPESE
    # AMMIN.,COMM. E DI RAPPRES.", Nicole). Prima di ONERI DIVERSI avrebbero preso il
    # mastro AGO "Oneri diversi di gestione" che porta "spese amministrative varie".
    (['LAVORO', 'NON DIPEN'], 'ce06'),
    (['GESTIONE', 'VEICOLI'], 'ce06'),
    (['SPESE', 'AMMIN'], 'ce06'),
    # mastri di Santini: acquisti B.6, lavorazioni di terzi e costi industriali/generali B.7
    (['ACQUISTI'], 'ce05'),
    (['LAV.', 'TERZI'], 'ce06'),
    (['LAVORAZION'], 'ce06'),
    (['COSTI', 'INDUSTRIAL'], 'ce06'),
    (['SPESE', 'GENERALI'], 'ce06'),
]
# CE keyword rules for RICAVI section
_CE_RICAVI_RULES = [
    (['RIM.FIN'], 'ce10_close'),
    (['RIMAN', 'FINAL'], 'ce10_close'),
    (['RIMANENZE', 'FINAL'], 'ce10_close'),
    (['PROV.FIN'], 'ce14'),
    # More specific rules first
    (['VARIAZ', 'RIMANENZ'], 'ce10_close'),
    (['VAR.RIM'], 'ce10_close'),
    (['ALTRI RICAVI'], 'ce04'),
    (['ALTRI', 'PROVENTI'], 'ce04'),
    (['PROVENTI', 'PARTECIP'], 'ce13'),
    (['PROVENTI', 'FINANZ'], 'ce14'),
    (['PROVENTI STRAORD'], 'ce18'),
    # Santini, mastro "RICAVI DIVERSI": interessi, cambi, consolidato fiscale, incrementi
    (['INTERESSI', 'ATTIV'], 'ce14'),
    (['OPERAZIONI', 'FINANZ'], 'ce14'),
    (['DIFF', 'CAMBI'], 'ce16'),
    (['SU CAMBI'], 'ce16'),
    (['CONSOLIDATO', 'FISCALE'], 'ce20_provento'),   # riduce le imposte
    (['INCREM', 'IMMOB'], 'ce03a'),
    (['RICAVI', 'DIVERSI'], 'ce04'),
    # Generic ricavi last (catches "RICAVI DELLE VENDITE" etc.)
    (['RICAVI'], 'ce01'),
]
# Equity sub3 keyword rules
_EQUITY_RULES = [
    (['CAPITALE'], 'capitale'),
    # Everything else in equity = riserve (includes utile esercizio precedente)
]

def _classify_sp_attivo(desc_upper: str) -> str:
    """Classify an attivo entry by description keywords. Returns field or 'sp06' default."""
    # RIM. is a ledger abbreviation, not an unknown asset to put in receivables.
    desc_upper = re.sub(r'\bRIM\.(?=\s|$|[A-Z])', 'RIMANENZE ', desc_upper)
    desc_upper = re.sub(r'\bRIMAN\.', 'RIMANENZE ', desc_upper)     # "RIMAN.FINALI SEMILAVORATI"
    for keywords, field in _SP_ATTIVO_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return 'sp06'  # default: crediti

# Testa della dicitura "fondo ammortamento" in TUTTE le grafie reali dei gestionali:
# `F.DO AMM.TO`, `F/AMM.`, `FDO AMM`, `FONDO AMMORTAMENTO`, `F.DI AMMOR.TO`...
# Ancorata a inizio riga perche' i conti di fondo esordiscono sempre con la dicitura.
_FONDO_AMM_HEAD_RE = re.compile(
    r"^\s*(?:F\s*[./]\s*D[OI]|FD[OI]|FOND[OI]|F)\s*[./]?\s*"
    r"AMM(?:ORT\w*|\.?\s*TO|\.?\s*NTO)?\s*[./]?\s*"
)
# Forma canonica contro cui e' scritta l'intera tabella `_SP_PASSIVO_RULES`.
_FONDO_AMM_CANON = 'F.DO AMM. '

def _canon_fondo_amm(desc_upper: str) -> str:
    """Collassa ogni grafia di "fondo ammortamento" sulla forma canonica `F.DO AMM.`.

    `_SP_PASSIVO_RULES` copre la categoria del cespite (MACCHINAR, ATTREZZ, AUTO,
    IMMAT...) SOLO in coppia con il token `F.DO`; la grafia con slash e' coperta
    solo insieme a IMMAT/MATER, parole che compaiono nei mastri aggregati ma MAI
    nei conti di dettaglio per categoria. Cosi' `F/AMM.MACCHINARI` non matcha
    nessuna regola, cade nel default `sp16` e diventa un DEBITO: l'attivo resta
    lordo, il passivo si gonfia della stessa massa, il bilancio pareggia lo stesso
    e nessun gate protesta (budget_281: 5 fondi su 6, 124.893,64 di 124.936,25).

    Normalizzare la TESTA una volta sola, invece di duplicare le 15 regole di
    categoria per ogni grafia, e' cio' che tiene allineati i due riconoscitori di
    fondo (`_is_fondo_amm` e questa tabella) — la loro divergenza E' il bug.

    La riscrittura tocca SOLO le stringhe che `_is_fondo_amm` ha gia' dichiarato
    fondi, quindi e' additiva per costruzione: si nettano piu' fondi, mai meno,
    e "AMMINISTRATORI C/COMPENSI" non e' raggiungibile.
    """
    if not _is_fondo_amm(desc_upper):
        return desc_upper
    canon = _FONDO_AMM_HEAD_RE.sub(_FONDO_AMM_CANON, desc_upper, count=1)
    # Nessuna testa riconosciuta (dicitura non a inizio riga): meglio la stringa
    # originale che una riscrittura a caso.
    return canon if canon != desc_upper else desc_upper

def _classify_sp_passivo(desc_upper: str) -> str:
    """Classify a passivo entry by description keywords. Returns field or 'sp16' default."""
    desc_upper = _canon_fondo_amm(desc_upper)
    for keywords, field in _SP_PASSIVO_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return 'sp16'  # default: debiti breve

def _sp02_detail_field(desc_upper: str) -> Optional[str]:
    """Return the B.I detail supported by the source description, if explicit."""
    if _kw_any(desc_upper, ['COSTI DI IMPIANTO', "COSTI D'IMPIANTO"]):
        return 'sp02a_costi_impianto'
    if _kw_any(desc_upper, ['SVILUPP', 'RICERCA']):
        return 'sp02b_costi_sviluppo'
    if _kw_any(desc_upper, ['BREVETT', 'SOFTWARE', 'OPERE INGEGNO', 'PROCEDURE ELABOR']):
        return 'sp02c_brevetti'
    if _kw_match(desc_upper, ['DIRITTI', 'UTILIZZ']):   # "F.DO AMM.TO DIRITTI UTILIZZO" (1343)
        return 'sp02c_brevetti'
    if _kw_any(desc_upper, ['CONCESS', 'LICENZ', 'MARCHI']):
        return 'sp02d_concessioni'
    if 'AVVIAMENTO' in desc_upper:
        return 'sp02e_avviamento'
    if _kw_any(desc_upper, ['IN CORSO', 'ACCONT']):
        return 'sp02f_immob_in_corso'
    # migliorie su beni di terzi ("MAN. E RIPARAZ. SU BENI DI TERZI", Santini): B.I.7
    if _kw_any(desc_upper, ['PLURIENN', 'IMMATERIAL', 'BENI DI TERZ', 'BENI TERZI', 'MANUT',
                            'RIPARAZ', 'MAN.E RIP', 'MIGLIORIE']):
        return 'sp02g_altre_immob_imm'
    return None

def _sp03_detail_field(desc_upper: str) -> Optional[str]:
    """Return the B.II detail from semantics, independently of account codes."""
    if _kw_any(desc_upper, ['IN CORSO', 'ACCONT']):
        return 'sp03e_immob_in_corso'
    if (_kw_any(desc_upper, ['TERREN', 'FABBRICAT', 'COSTRUZIONI LEGGER'])
            or _kw_match(desc_upper, ['COSTR', 'LEGGER'])):     # "F.DO AMM.COSTR.LEGGERE"
        return 'sp03a_terreni_fabbricati'
    if 'ATTREZ' in desc_upper:                 # anche "ATTREZ./REPARTO OFFIC" (budget_680)
        return 'sp03c_attrezzature'
    # "MOBIL" ma non dentro IMMOBIL...: "IMMOBILIZZI TECNICI" non e' un mobile
    # "MACCH. ORD. UFFICI", "MACCH. UFF. ELETTRON", "AUTOV. DA TRASPORT" (budget_1343)
    if re.search(r'(?<!IM)MOBIL|MACC\w*\.?\s*(?:ORD|UFF)|\bAUTOV', desc_upper) or _kw_any(desc_upper, [
        "MACCHINE D'UFFICIO", 'MACCHINE UFFICIO', 'MACCHINE UFF', 'ARRED',
        'AUTOMEZZ', 'AUTOVEICOL', 'AUTOVETTUR', 'AUTO.', 'AUTO,', 'AUTOCARR',
        'BENI VALORE', 'BENI DI VALORE', 'HARDWARE', 'CELLULAR', 'CENTRALINO',
        'TELEFON', 'MEZZI TRASP', 'ALTRI BENI MATERIAL',
    ]):
        return 'sp03d_altri_beni'
    # "MACCHIN/IMP", "MACC./IMP.", "IMP.DEPURAZIONE" (budget_680)
    # "F.DO AMMTO IMP AUDIO-VIDEO SORV" (Santini)
    if (_kw_any(desc_upper, ['IMPIANT', 'MACCHINAR', 'MACCHIN/', 'MACCHIN.', 'MACC.', 'IMP.', 'IMP/'])
            or re.search(r'\bIMP\b', desc_upper)):
        return 'sp03b_impianti_macchinari'
    return None

def _sp04_detail_field(desc_upper: str) -> Optional[str]:
    if 'PARTECIPAZ' in desc_upper:
        return 'sp04a_partecipazioni'
    if 'CREDITI' in desc_upper:
        if _kw_any(desc_upper, ['(OE', 'OLTRE']):
            return 'sp04c_crediti_immob_lungo'
        if _kw_any(desc_upper, ['(EE', 'ENTRO']):
            return 'sp04b_crediti_immob_breve'
    if 'TITOL' in desc_upper:
        return 'sp04d_altri_titoli'
    if 'DERIVAT' in desc_upper:
        return 'sp04e_strumenti_derivati_attivi'
    return None

def _sp05_detail_field(desc_upper: str) -> Optional[str]:
    if _kw_match(desc_upper, ['LAVOR', 'CORSO']):
        return 'sp05c_lavori_in_corso'
    if _kw_any(desc_upper, ['SEMILAVOR', 'PRODOTT IN CORSO', 'PRODOTTI IN CORSO']):
        return 'sp05b_prodotti_in_corso'
    if _kw_match(desc_upper, ['MAT', 'PRIM']):
        return 'sp05a_materie_prime'
    if _kw_any(desc_upper, ['PRODOTT FINIT', 'PRODOTTI FINIT', 'MERCI']):
        return 'sp05d_prodotti_finiti'
    if 'ACCONT' in desc_upper:
        return 'sp05e_acconti'
    return None

def _sp14_detail_field(desc_upper: str) -> Optional[str]:
    if _kw_any(desc_upper, ['QUIESCENZA', 'INDENNIT', 'FINE MANDATO', 'T.F.M']):
        return 'sp14a_fondi_trattamento_quiescenza'
    if 'IMPOST' in desc_upper:
        return 'sp14b_fondi_imposte'
    if 'DERIVAT' in desc_upper:
        return 'sp14c_strumenti_derivati_passivi'
    if _kw_any(desc_upper, ['FOND', 'RISCHI', 'ONERI']):
        return 'sp14d_altri_fondi'
    return None

_CE_AMMORTAMENTO_RE = re.compile(r'^AMM(?:ORTAMENT[OI]|\.?\s?TO\b|/TO\b|\.(?!NE\b))\s*')

# La stessa testa, ma senza l'"AMM." nudo (e' anche "AMM.NE", amministrazione): un conto
# che comincia cosi' e nomina un cespite e' un ammortamento PRIMA di ogni altra parola -
# "AMM/TO ATTREZZ.COMMERCIALI" (Napolitano) finiva nei servizi per COMMERCIAL, oltre il
# confine dell'EBITDA.
_CE_AMMORTAMENTO_PRIMA_RE = re.compile(
    r'^AMM(?:ORTAMENT[OI]|\.?\s?TO\b|/TO\b|\.TI\b|\.(?=ORD|CIVIL))\.?\s*')
# Conti foglia di un piano dei conti senza mastri (budget_435, sezioni contrapposte di
# soli conti): ultima risorsa, solo dove oggi scatta il ripiego (ce12 fra i costi). Mai
# dentro _classify_ce_costi: un conto sotto un mastro che lo dice prende il mastro
# ("MATERIALE RIPAR/MANUTENZ." sotto i materiali di consumo resta materia, budget_680).
_CE_COSTI_FOGLIE = [
    (['TFR'], 'ce08a_tfr'),                       # "ACCAN.TFR FORMAZIONE LAVORO" (AITEC)
    (['T.F.R'], 'ce08a_tfr'),
    (['PREMI', 'PRODUZION'], 'ce08b'),            # retribuzione, non un premio assicurativo
    (['CONTRIBUTI', 'SANITAR'], 'ce08c'),         # assistenza sanitaria integrativa
    (['PREMI', 'ELEMENTI'], 'ce08b'),             # "PREMI E ALTRI ELEMENTI SIMILI"
    (['ASSISTENZA'], 'ce06'),                     # "CANONI DI ASSISTENZA TECNICA": servizio
    (['CONSUL'], 'ce06'),                         # "COMP.PROF.CONSUL.AMM.VA/FISC." (Napolitano)
    (['COMP', 'PROF'], 'ce06'),                   # compensi professionali
    (['VIAGG'], 'ce06'),
    (['RISTORANT'], 'ce06'),
    (['PERNOTT'], 'ce06'),
    (['TELEMATIC'], 'ce06'),
    (['CARBURANT'], 'ce05'),
    (['LUBRIFICANT'], 'ce05'),
    (['CANCELLERIA'], 'ce05'),
    (['IMBALLAGG'], 'ce05'),
    (['INDUMENTI'], 'ce05'),
    (['MATERIALI', 'DI '], 'ce05'),               # "MATERIALI DI PULIZIA/OFFICINA"
    (['CANONI'], 'ce07'),                         # locazione, leasing, noleggio
    (['NOLEGG'], 'ce07'),
    (['LOCAZION'], 'ce07'),
    (['AFFITT'], 'ce07'),
    (['LEASING'], 'ce07'),
    (['CONTRIBUTI', 'PREVIDENZ'], 'ce08c'),
    (['INFORTUNI'], 'ce08c'),
    (['INAIL'], 'ce08c'),
    (['MANUTENZ'], 'ce06'),
    (['RIPARAZ'], 'ce06'),
    (['TRASPORT'], 'ce06'),
    (['CONSULENZ'], 'ce06'),
    (['ENERGIA'], 'ce06'),
    (['TELEFON'], 'ce06'),
    (['ASSICURAZ'], 'ce06'),
    (['PREMI'], 'ce06'),                          # "PREMI RCA", "PREMI RCT"
    (['PROVVIGION'], 'ce06'),
    (['PEDAGG'], 'ce06'),
    (['PARCHEGG'], 'ce06'),
    (['COLLAUD'], 'ce06'),
    (['SOCCORSO'], 'ce06'),
    (['FORMAZIONE'], 'ce06'),
    (['VISITE', 'MEDICHE'], 'ce06'),
    (['INDENNIT', 'CHILOMETR'], 'ce06'),
    (['ONERI', 'BANCARI'], 'ce06'),
    (['SPESE', 'BANCARIE'], 'ce06'),
    (['SOFTWARE'], 'ce06'),
    (['SPESE', 'DI '], 'ce06'),                   # "SPESE DI TRASPORTO/INCASSO/VENDITA"
]

def _rimanenze_per_natura(tag: str, *testi: str, ripiego: Optional[str] = None) -> str:
    """Le rimanenze di PRODOTTI vanno in A.2 (ce02), non in B.11 (ce10): il tag di
    rimanenze che le tabelle a parole danno sempre come materie ('ce10' fra i costi,
    'ce10_close' fra i ricavi) diventa 'ce02_open' (iniziali: riducono ce02) o 'ce02'
    (finali) quando la descrizione, o quella di un padre, dice prodotti. Natura non
    detta o mista: decide ``ripiego`` (la natura del lato opposto, _natura_unanime),
    poi il tag di sempre. Regola in importers/rimanenze_ce.py."""
    if tag in ('ce10', 'ce10_close') and (natura_rimanenze(*testi) or ripiego) == 'ce02':
        return 'ce02_open' if tag == 'ce10' else 'ce02'
    return tag

def _rimanenze_dal_dettaglio(tag, codice, desc, importo, figli, classify=None, ripiego=None):
    """Un mastro di rimanenze si legge dai suoi conti: prodotti in ce02, materie e merci
    in ce10 (_rimanenze_per_natura). Quando i figli sommano al centesimo il totale
    stampato decidono loro, anche contro il nome del mastro (AITEC: "RIM.INIZ.SEMILAVORATI
    PROD-FINITI" porta sotto anche le materie prime) - la profondita' propone, il totale
    decide. Senza figli che quadrano decide la descrizione del conto, poi quella dei padri,
    poi il tag di sempre. Un figlio che non e' un conto di rimanenze ("Incrementi per
    lavori interni" sotto lo stesso mastro) prende la propria voce da ``classify``. Un
    conto che la natura non la dice prende ``ripiego``, la natura unanime delle rimanenze
    dell'altro lato (_natura_unanime): iniziali e finali sono lo stesso magazzino, e
    mandarne un capo in ce02 e l'altro in ce10 gonfierebbe valore e costi della
    produzione di entrambi gli importi (COLOMBO: "RIMANENZE INIZIALI" accanto a
    "Prodotti finiti rimanenze finali").

    ``tag`` e' quello del classificatore: 'ce10'/'ce02_open' fra i costi, 'ce10_close'/
    'ce02' fra i ricavi (un altro tag passa intatto). ``figli(codice)`` -> [(codice,
    descrizione, importo)] i figli diretti. Ritorna [(tag, importo)]."""
    if tag in ('ce10', 'ce02_open'):
        base = 'ce10'
    elif tag == 'ce10_close' or (tag == 'ce02' and e_conto_rimanenze(desc)):
        base = 'ce10_close'
    else:
        return [(tag, importo)]

    def scendi(c, d, a, padri):
        if padri and not e_conto_rimanenze(d) and natura_rimanenze(d) is None \
                and classify is not None:
            proprio = classify(d)
            if proprio and proprio not in ('ce10', 'ce10_close', 'ce02_open', 'ce02'):
                return [(proprio, a)]
        ch = figli(c)
        if ch and abs(sum((x[2] for x in ch), Decimal('0')) - a) <= Decimal('0.01'):
            out = []
            for x in ch:
                out.extend(scendi(x[0], x[1], x[2], (d,) + padri))
            return out
        return [(_rimanenze_per_natura(base, d, *padri, ripiego=ripiego), a)]

    return scendi(codice, desc, importo, ())

def _natura_unanime(descrizioni) -> Optional[str]:
    """La natura (ce02/ce10) dei conti di rimanenze di un lato, quando tutti quelli che la
    dicono dicono la stessa; altrimenti None."""
    nature = {natura_rimanenze(d) for d in descrizioni if e_conto_rimanenze(d)}
    nature.discard(None)
    return nature.pop() if len(nature) == 1 else None

_CE09_SOTTO = ('ce09a', 'ce09b', 'ce09c', 'ce09d')

def _ce09_sotto(desc_upper: str) -> Optional[str]:
    """La sotto-voce di B.10 che la descrizione DICHIARA: ammortamento immateriali (ce09a)
    o materiali (ce09b), altre svalutazioni delle immobilizzazioni (ce09c), svalutazione
    crediti (ce09d). None per un "AMMORTAMENTI"/"SVALUTAZIONI" nudo e per una descrizione
    troncata ("AMM.TI CIVILISTICI IMMOBILIZZ", budget_588): li' decidono i conti sotto,
    non il ripiego "materiali" di _classify_ce_costi."""
    if 'SVAL' in desc_upper:
        if _kw_any(desc_upper, ['CREDIT', 'CLIENT']):
            return 'ce09d'
        if _kw_any(desc_upper, ['IMMOB', 'CESPIT']):
            return 'ce09c'
        return None
    if _CE_AMMORTAMENTO_RE.match(desc_upper) or 'AMM.TI' in desc_upper:
        if 'IMMAT' in desc_upper:
            return 'ce09a'
        if 'MATERIAL' in desc_upper:
            return 'ce09b'
    return None

def _ce09_dal_dettaglio(codice, desc, importo, figli):
    """Un mastro di ammortamenti e svalutazioni si ripartisce sulle sotto-voci di B.10:
    al primo livello che la dice (_ce09_sotto), scendendo nei conti solo quando sommano
    al centesimo il totale stampato. Ammortamenti non ripartiti restano 'ce09' (li
    attribuisce residual_finalization, dichiarandolo); il motore del previsionale e
    quello dell'infrannuale ammortizzano sp02/sp03 dai soli ce09a/ce09b.

    ``figli(codice)`` -> [(codice, descrizione, importo)]. Ritorna [(tag, importo)] con
    tag in 'ce09', 'ce09a'..'ce09d'."""
    def scendi(c, d, a):
        t = _ce09_sotto(d)
        if t:
            return [(t, a)]
        ch = figli(c)
        if ch and abs(sum((x[2] for x in ch), Decimal('0')) - a) <= Decimal('0.01'):
            out = []
            for x in ch:
                out.extend(scendi(x[0], x[1], x[2]))
            return out
        f = _classify_ce_costi(d)
        if f == 'ce09d' and 'AMMORT' in d:
            f = 'ce09'          # "AMMORTAMENTI E SVALUTAZIONI": SVALUT non dice crediti
        return [(f if f in _CE09_SOTTO else 'ce09', a)]

    return scendi(codice, desc, importo)

def _albero_da_dettagliare(aggregato, codice, desc, importo, figli):
    """Un mastro che il lettore non sa ripartire sulle sotto-voci di legge, con i suoi
    conti foglia: lo ripartisce il modello (importers/dettaglio_dal_modello.py)."""
    from importers.dettaglio_dal_modello import albero
    return albero(aggregato, codice, desc, importo, figli)

def _figli_puntati(righe):
    """figli(codice) per i codici a punti ("49" -> "49.01" -> "49.01.01")."""
    def figli(c):
        pref = c + '.'
        return [r for r in righe if r[0].startswith(pref) and '.' not in r[0][len(pref):]]
    return figli

def _classify_ce_costi(desc_upper: str) -> Optional[str]:
    """Classify a CE cost entry by description keywords."""
    m = _CE_AMMORTAMENTO_PRIMA_RE.match(desc_upper)
    if m and desc_upper[m.end():].strip() and 'SVAL' not in desc_upper \
            and 'FONDO' not in desc_upper and 'F.DO' not in desc_upper:
        resto = desc_upper[m.end():]
        immat = _classify_sp_attivo(resto) == 'gross_sp02' or _fondo_is_immat(resto)
        return 'ce09a' if immat else 'ce09b'
    for keywords, field in _CE_COSTI_RULES:
        if _kw_match(desc_upper, keywords):
            return _rimanenze_per_natura(field, desc_upper)
    # "AMM.IMPIANTI E MACCHINARI", "AMMORTAMENTO SOFTWARE", "AMMTO TELEFONIA" (Santini): la
    # quota di un cespite nominato. Immateriale se il cespite lo e', altrimenti materiale
    # (ce09a/ce09b stanno entrambi dentro ce09, l'errore resta dentro l'aggregato).
    m = _CE_AMMORTAMENTO_RE.match(desc_upper)
    if m and desc_upper[m.end():].strip():
        resto = desc_upper[m.end():]
        cespite = _classify_sp_attivo(resto)
        # i segni d'immateriale dei fondi: manutenzioni da ammortizzare, spese
        # pluriennali, disaggi (budget_435)
        immat = cespite == 'gross_sp02' or _fondo_is_immat(resto)
        return 'ce09a' if immat else 'ce09b'
    return None

def _classify_ce_costi_foglia(desc_upper: str) -> Optional[str]:
    """Ultima risorsa per un conto di costo che nessuna regola ne' il suo mastro
    riconoscono: la parola del conto foglia, prima del ripiego."""
    for keywords, field in _CE_COSTI_FOGLIE:
        if _kw_match(desc_upper, keywords):
            return field
    return None

def _classify_ce_ricavi_foglia(desc_upper: str) -> Optional[str]:
    """Conti foglia di ricavo senza la parola RICAVI ("CORRISPETTIVI DA TRASPORTO DI
    MERCI SU STRADA", budget_435): il fatturato, non altri ricavi."""
    if _kw_any(desc_upper, ['CORRISPETTIV', 'PRESTAZIONI DI SERVIZ', 'FATTURATO']):
        return 'ce01'
    return None

# Sinonimi di NATURA per mastri di conto economico che non usano le parole IV-CEE.
# Valgono per qualunque gestionale, ma si consultano solo come ULTIMA risorsa prima
# del secchio generico (massa non classificata): non spostano nulla che una regola
# gia' riconosca.
_CE_COSTI_SINONIMI = [
    (['LAVORO NON'], 'ce06'),          # "PRESTAZIONI DI LAVORO NON (DIPENDENTE)" troncato
    (['OPERA', 'TERZI'], 'ce06'),      # manodopera di terzi/esterna: un servizio B.7
    (['OPERA', 'ESTERN'], 'ce06'),
    (["MANO D'OPERA"], 'ce08'),        # manodopera: personale B.9
    (['MANO D OPERA'], 'ce08'),
    (['MANODOPERA'], 'ce08'),
    (['COSTI', 'FABBRICA'], 'ce06'),   # come COSTI INDUSTRIALI
    (['PROMOZIONAL'], 'ce06'),         # spese promozionali / pubblicita': B.7
    (['PUBBLICIT'], 'ce06'),
    (['ELABORAZ', 'DATI'], 'ce06'),    # CED / centro elettronico: servizio B.7
    (['CENTRO', 'ELETTRONIC'], 'ce06'),
    (['PERDITE', 'VARIE'], 'ce12'),    # oneri diversi di gestione B.14
    (['ALTRI ONERI'], 'ce12'),         # idem (i finanziari li prende prima ONERI+FINANZ)
]

_CE_RICAVI_SINONIMI = [
    (['VENDITE'], 'ce01'),             # mastro "VENDITE" (Italia/estero): fatturato A.1
    (['PROFITTI', 'VARI'], 'ce04'),    # altri ricavi e proventi A.5
    (['PROFITTI', 'DIVERS'], 'ce04'),
]

def _classify_ce_sinonimo(desc_upper: str, direction: str) -> Optional[str]:
    """Ultima risorsa prima del secchio generico: il sinonimo di natura del mastro."""
    rules = _CE_COSTI_SINONIMI if direction == 'costi' else _CE_RICAVI_SINONIMI
    for keywords, field in rules:
        if _kw_match(desc_upper, keywords):
            return field
    return None

def _classify_ce_ricavi(desc_upper: str) -> Optional[str]:
    """Classify a CE ricavi entry by description keywords."""
    for keywords, field in _CE_RICAVI_RULES:
        if _kw_match(desc_upper, keywords):
            return _rimanenze_per_natura(field, desc_upper)
    return None

def _resolve_field(desc: str, side: Optional[str] = None,
                   statement: Optional[str] = None) -> Optional[str]:
    """Shared-tree classification, returned as a SHORT route-C key.

    `iv_cee_hierarchy.resolve` reasons in DB column names ('ce09_ammortamenti')
    while the route-C parsers work in short keys ('ce09') until _map_sc_keys.
    The short key is the db_field prefix up to the first underscore
    ('sp04a_partecipazioni' -> 'sp04a'). That split is a mechanical string
    operation, not a guarantee of routability on its own: every short key the
    tree can actually produce must also be in `pdf_importer._SC_KEY_MAP` (or
    already contain an underscore, in which case `_map_sc_keys` passes it
    through unchanged) — otherwise `_map_sc_keys` silently drops the amount.
    See `tests/test_classification_fallback.py` for the guard that checks
    this holds for every node in `data/iv_cee_tree.json`.

    Returns None when the tree does not know the description, or when it
    resolves to the OTHER statement — a balance-sheet caption must never be
    booked as a cost.
    """
    try:
        from importers.iv_cee_hierarchy import resolve as _tree_resolve
        node = _tree_resolve(desc, side, statement)
    except Exception:
        return None
    if node is None or not node.db_field:
        return None
    if statement and node.statement and node.statement != statement:
        return None
    return node.db_field.split('_', 1)[0]

# The income-statement leaves of data/iv_cee_tree.json, split by the SIGN they
# carry in calculations/ce_result.py: a positive amount in a COST field lowers
# the result (production_cost, ce15 oneri finanziari, ce19 oneri straordinari,
# ce20 imposte), a positive amount in a REVENUE field raises it.
#
# The split has to be written down here because the tree cannot express it:
# Node.side is None for EVERY income-statement node (side is a balance-sheet
# concept), so _resolve_field's 'costi'/'ricavi' argument enforces nothing and
# statement='ce' only bounds the lookup to the income statement. Without the
# allowlists a cost mastro reaches a gain voce -- 'DIFFERENZE CAMBIO PASSIVE'
# -> ce16 -- and since _hier_reconstruct adds every mastro POSITIVELY, the
# amount moves gestione finanziaria (ce13+ce14-ce15+ce16) by TWICE its value.
#
# The genuinely SIGNED (net) voci -- ce02 variazioni rimanenze prodotti, ce16
# utili e perdite su cambi, ce17 rettifiche di valore di attivita finanziarie,
# and their mirror ce10 variazioni rimanenze materie prime -- legitimately
# appear on either side of a trial balance. Each is listed ONLY under the
# direction in which a POSITIVE amount is CORRECT: ce02/ce16/ce17 raise the
# result, so they accept a revenue-column mastro only; ce10 is a cost, so it
# accepts a cost-column mastro only. A wrong-direction mastro is not guessed at
# with a sign flip -- it falls through to the KPI-neutral catch-all, which is
# what it did before the tree fallback existed.
_CE_COST_FIELDS = frozenset({
    'ce05', 'ce06', 'ce07', 'ce08', 'ce09', 'ce10', 'ce11', 'ce11b', 'ce12',
    'ce15',                      # C.17 interessi e altri oneri finanziari
    'ce19',                      # E.21 oneri straordinari
    'ce20',                      # imposte sul reddito
})

_CE_REVENUE_FIELDS = frozenset({
    'ce01', 'ce02', 'ce03', 'ce03a', 'ce04',   # A) valore della produzione (ce03a = A.4, ce03 = A.3)
    'ce13', 'ce14', 'ce16',           # C) proventi finanziari (ce16 netto)
    'ce17',                           # D) rettifiche di valore (netto)
    'ce18',                           # E.20 proventi straordinari
})

def _resolve_ce_field(desc: str, direction: str) -> Optional[str]:
    """Shared-tree CE classification constrained to `direction`.

    `direction` is 'costi' or 'ricavi'. Returns None when the tree does not
    know the description OR when it resolves to a voce of the OPPOSITE sign, so
    the caller falls through to its catch-all exactly as it did before the tree
    fallback was added. See _CE_COST_FIELDS / _CE_REVENUE_FIELDS for why the
    tree cannot enforce this on its own.
    """
    field = _resolve_field(desc, direction, statement='ce')
    if field is None:
        return None
    allowed = _CE_COST_FIELDS if direction == 'costi' else _CE_REVENUE_FIELDS
    return field if field in allowed else None

# Accounts that decide every KPI. A fallback may NEVER write these: an error
# here changes a TOTAL (a fondo ammortamento booked as a debt inflates assets
# and debts together), which breaks PFN, ROI, indipendenza finanziaria and
# both rating models at once. ce09 is included because EBITDA = EBIT + ce09.
TIER0_FIELDS = frozenset({
    'sp02', 'sp03', 'sp04',      # immobilizzazioni nette
    'sp11', 'sp12', 'sp13',      # patrimonio netto
    'sp16a', 'sp17a',            # debiti verso banche
    'ce09',                      # ammortamenti (EBITDA boundary)
})
# KPI-neutral destinations: moving mass between these changes neither EBIT nor
# EBITDA (they are all inside 'costi della produzione'), nor any debt/credit
# total. Always an explicit SUB-field: projection_common.base_bank_debt treats
# an aggregate/detail gap as BANK debt, so a residual left on an aggregate
# would silently become phantom bank debt - a tier-0 corruption.
FALLBACK_FIELDS = {'ce': 'ce06', 'bs': 'sp16g'}

# Canonical definition lives in the dependency-free reliability module so the
# import pipeline has exactly one materiality rule.
from importers.reliability import materiality_threshold  # noqa: E402,F401

def fallback_field(statement: str) -> str:
    """KPI-neutral destination for unrecognised mass in `statement`.

    Separate from fallback_bucket because a classification loop knows the
    amount long before the sheet total exists: it needs the destination now
    and the materiality verdict later.
    """
    return FALLBACK_FIELDS.get(statement, 'ce06')

def fallback_bucket(desc: str, statement: str, amount: Decimal,
                    total: Decimal, target: Optional[str] = None):
    """Destination for mass that was READ but not recognised.

    Returns (short_field, severity). severity is 'silent' below the
    materiality threshold and 'recorded' above it, so the caller can surface
    material guesswork instead of hiding it.

    Raises ValueError when `target` names a tier-0 field: uncertainty about a
    critical account must become an UNRELIABLE verdict, never a guess.
    """
    if target and target in TIER0_FIELDS:
        raise ValueError(
            f"fallback vietato verso un conto critico ({target}): "
            f"'{desc}' deve essere segnalato, non indovinato")
    severity = ('recorded'
                if abs(amount or Decimal('0')) > materiality_threshold(total)
                else 'silent')
    return fallback_field(statement), severity

# ---------------------------------------------------------------------------
# Typed sub-field classification (depth preservation)
# ---------------------------------------------------------------------------
# When the source distinguishes account TYPES (banche vs fornitori vs tributari,
# clienti vs altri crediti, riserve per natura), preserve that depth into the
# IV-CEE typed sub-fields instead of collapsing everything into the aggregate.
# These return a single OIC sub-letter; the aggregate is computed unchanged, so
# sub-fields are purely additive (no balance/quadratura impact). The DB field
# name maps below translate (letter -> full column) for emission.

# OIC art. 2424 D) Debiti — full DB column names per maturity bucket
_DEBT_FIELD = {
    'breve': {
        'a': 'sp16a_debiti_banche_breve',
        'b': 'sp16b_debiti_altri_finanz_breve',
        'c': 'sp16c_debiti_obbligazioni_breve',
        'd': 'sp16d_debiti_fornitori_breve',
        'e': 'sp16e_debiti_tributari_breve',
        'f': 'sp16f_debiti_previdenza_breve',
        'g': 'sp16g_altri_debiti_breve',
    },
    'lungo': {
        'a': 'sp17a_debiti_banche_lungo',
        'b': 'sp17b_debiti_altri_finanz_lungo',
        'c': 'sp17c_debiti_obbligazioni_lungo',
        'd': 'sp17d_debiti_fornitori_lungo',
        'e': 'sp17e_debiti_tributari_lungo',
        'f': 'sp17f_debiti_previdenza_lungo',
        'g': 'sp17g_altri_debiti_lungo',
    },
}

# OIC art. 2424 C.II) Crediti — full DB column names per maturity bucket
_CREDIT_FIELD = {
    'breve': {
        'a': 'sp06a_crediti_clienti_breve',
        'e': 'sp06e_crediti_tributari_breve',
        'f': 'sp06f_imposte_anticipate_breve',
        'g': 'sp06g_crediti_altri_breve',
    },
    'lungo': {
        'a': 'sp07a_crediti_clienti_lungo',
        'e': 'sp07e_crediti_tributari_lungo',
        'f': 'sp07f_imposte_anticipate_lungo',
        'g': 'sp07g_crediti_altri_lungo',
    },
}

# OIC art. 2424 A) Patrimonio netto — riserve breakdown
_RISERVA_FIELD = {
    'a': 'sp12a_riserva_sovrapprezzo',
    'b': 'sp12b_riserve_rivalutazione',
    'c': 'sp12c_riserva_legale',
    'd': 'sp12d_riserve_statutarie',
    'e': 'sp12e_altre_riserve',
    'g': 'sp12g_utili_perdite_portati',
}

def _debt_type(desc_upper: str) -> str:
    """Typed-debt OIC sub-letter for a passivo debt line (a..g)."""
    if any(w in desc_upper for w in ('C/COMPENS', 'SINDAC', 'CLIENTI C/ANTICIP')):
        return 'g'
    if re.search(r'\bSOC[IO]+\b.*FINAN|FINAN.*\bSOC[IO]+\b', desc_upper):
        return 'b'
    if any(w in desc_upper for w in ('ERARI', 'TRIBUTAR', 'REGIONI C/')):
        return 'e'
    if any(w in desc_upper for w in ('FSBA', 'EBNA', 'SAN.ART', 'SANART')):
        return 'f'
    if _kw_any(desc_upper, ['OBBLIGAZION']):
        return 'c'
    # Altri finanziatori / soci FIRST, so the generic FINANZ→banche rule below does not
    # steal "FINANZIATORI" or "SOCI C/FINANZIAMENTO" (D.5, not D.4).
    if _kw_any(desc_upper, ['ALTRI FINANZIAT', 'FINANZIAT', 'SOCI C/FINANZ', 'SOCI C/C',
                            'V/SOCI', 'FACTOR']):
        return 'b'
    # "DEBITI VARI/DIVERSI DI FINANZIAMENTO" non nomina una banca (Napolitano 30/09/2026:
    # sotto ci sono i debiti v/dipendenti, il CEE dello stesso gestionale li mette in D.5).
    if _kw_any(desc_upper, ['VARI DI FINANZ', 'DIVERSI DI FINANZ']) and 'BANC' not in desc_upper:
        return 'b'
    # Banks (D.4): 'BANC' covers BANCA/BANCO/BANCHE/BANCARIO and bank names ending in
    # -BANCA (EMILBANCA); incl. bank financings ("FINANZIAMENTO <banca>"), salvo-buon-fine
    # (SBF), and bank advances against invoices/credits ("ANTICIPO FATTURE", "ANTICIPI SU
    # CREDITI") which are short-term bank debt even when the bank name carries no 'BANC'.
    if re.search(r'\bC[/.]C(?:\.|\b)', desc_upper) or _kw_any(desc_upper, ['BANC', 'MUTU', 'SCOPERT',
                            'FINANZIAM', 'FINANZ', 'S.B.F', 'SBF',
                            'ANTICIPO FATTUR', 'ANTICIPI SU FATTUR', 'ANTICIPI SU CRED']):
        return 'a'
    # Fornitori (D.7): incl. trade payables ("DEBITI COMMERCIALI") and supplier accruals
    # ("FATTURE DA RICEVERE").
    if _kw_any(desc_upper, ['FORNITOR', 'COMMERCIAL', 'FATTURE DA RICEV']):
        return 'd'
    # Tributari (D.12): 'ERARI' covers ERARIO/ERARIALI/ERARIALE.
    if _kw_any(desc_upper, ['TRIBUTAR', 'ERARI', 'IVA', 'IMPOST', 'F24', 'RITENUT']) \
            or re.search(r'\bIR(?:ES|AP|PEF)\b', desc_upper):
        return 'e'
    if _kw_any(desc_upper, ['PREV', 'INPS', 'INAIL', 'SICUR', 'ENPALS', 'INARCASSA']):
        return 'f'
    return 'g'  # altri debiti (acconti, clienti c/, movimentazioni c/terzi, ...)

# Creditor-type sub-field groups (entro / oltre), aligned to _debt_type letters a..g.
_DEBT_GROUPS_BREVE = ['sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                      'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                      'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                      'sp16g_altri_debiti_breve']

_DEBT_GROUPS_LUNGO = ['sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                      'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                      'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                      'sp17g_altri_debiti_lungo']

def overlay_debt_typing(winner_bs: dict, donor_bs: dict,
                        degenerate_frac: Decimal = Decimal('0.60'),
                        donor_margin: Decimal = Decimal('0.20')) -> dict:
    """Route-C post-pass: graft the donor's creditor-type breakdown onto the winner.

    Both route-C extractors run (CoGe LLM + deterministic). The LLM is strong on TOTALS
    but can dump the whole debt mass into 'altri' (sp16g/sp17g); the deterministic parser
    types each line via _debt_type (banche/fornitori/tributari/...). When the winning
    candidate's debt is DEGENERATE (mostly 'altri') and the donor has a meaningfully
    richer split, redistribute the winner's debt AGGREGATE across a..g using the donor's
    proportions — the winner's total is preserved, only the split changes.

    Conservative by design (no-op unless clearly beneficial):
      - skip a group whose aggregate is ~0
      - skip when the winner is already well-typed (altri share <= degenerate_frac)
      - skip when the donor is itself degenerate or not at least `donor_margin` better
    Mutates and returns winner_bs.
    """
    for agg, groups, altri_key in (
        ('sp16_debiti_breve', _DEBT_GROUPS_BREVE, 'sp16g_altri_debiti_breve'),
        ('sp17_debiti_lungo', _DEBT_GROUPS_LUNGO, 'sp17g_altri_debiti_lungo'),
    ):
        w_total = Decimal(str(winner_bs.get(agg, 0) or 0))
        if w_total <= Decimal('1'):
            continue
        w_altri = Decimal(str(winner_bs.get(altri_key, 0) or 0))
        w_altri_frac = w_altri / w_total
        if w_altri_frac <= degenerate_frac:
            continue  # winner already meaningfully typed → leave it
        d_total = sum((Decimal(str(donor_bs.get(g, 0) or 0)) for g in groups), Decimal('0'))
        if d_total <= Decimal('1'):
            continue  # donor has no debt typing to offer
        d_altri = Decimal(str(donor_bs.get(altri_key, 0) or 0))
        d_altri_frac = d_altri / d_total
        if d_altri_frac >= w_altri_frac - donor_margin:
            continue  # donor not meaningfully richer than the winner
        # Redistribute the winner's aggregate by the donor's proportions.
        new_vals = {}
        for g in groups:
            share = Decimal(str(donor_bs.get(g, 0) or 0)) / d_total
            new_vals[g] = (w_total * share).quantize(Decimal('0.01'))
        # Absorb rounding drift into 'altri' so the split sums back to the aggregate.
        drift = w_total - sum(new_vals.values(), Decimal('0'))
        new_vals[altri_key] = new_vals.get(altri_key, Decimal('0')) + drift
        winner_bs.update(new_vals)
    return winner_bs

def _credit_type(desc_upper: str) -> str:
    """Typed-credit OIC sub-letter for an attivo credit line (a/e/f/g)."""
    if _kw_any(desc_upper, ['IMPOSTE ANTICIP', 'IMPOSTA ANTICIP']):
        return 'f'
    if _kw_any(desc_upper, ['CLIENT']):
        return 'a'
    if _kw_any(desc_upper, ['TRIBUTAR', 'ERARIO', 'IVA', 'IMPOST', 'RITENUT', "CRED. D'IMPOST",
                            'CREDITO IMPOST', 'F24']):
        return 'e'
    return 'g'  # altri crediti

def _riserva_type(desc_upper: str) -> str:
    """Riserve OIC sub-letter for a PN reserve line (a/b/c/d/e/g)."""
    if _kw_any(desc_upper, ['SOVRAPPREZZO']):
        return 'a'
    if _kw_any(desc_upper, ['RIVALUTAZ']):
        return 'b'
    if _kw_any(desc_upper, ['LEGALE']):
        return 'c'
    if _kw_any(desc_upper, ['STATUTAR']):
        return 'd'
    if _kw_any(desc_upper, ['PORTATI', 'PORTATE', 'NUOVO', 'PRECEDENT', 'ESERCIZI PREC']):
        return 'g'  # utili/(perdite) portati a nuovo
    return 'e'  # altre riserve (straordinaria, riserva utili, ...)

def _spesa_capitalizzata_orfana(desc_upper: str) -> bool:
    """Un conto d'ATTIVO che nessuna regola riconosce (default sp06) ma che si
    descrive come spesa di manutenzione/riparazione/ammodernamento: all'attivo una
    spesa sta solo se capitalizzata (B.I.7), mai come credito. Usato SOLO quando un
    fondo ammortamento immateriale resta senza lordo su cui nettarsi."""
    if _kw_any(desc_upper, ['CREDIT', 'ERARIO', 'DEBIT', 'ANTICIP', 'ACCONT', 'CLIENT']):
        return False
    return 'SPESE' in desc_upper and _kw_any(desc_upper, ['MANUT', 'RIPARAZ', 'AMMODERN'])

# CE sub-field → parent aggregate (the EBIT/profit formula reads the parent). Mirrors
# the mapping in extract_contrapposte_best_effort so a personale/ammortamenti detail
# rolls into ce08/ce09 instead of being lost.
_CE_HIER_SUBPARENT = {
    'ce08a_tfr': 'ce08', 'ce08b': 'ce08', 'ce08c': 'ce08', 'ce08d': 'ce08',
    'ce09a': 'ce09', 'ce09b': 'ce09', 'ce09c': 'ce09', 'ce09d': 'ce09',
}

# CE sub-field -> (full DB detail key, parent aggregate). Personale (ce08a-d) and
# ammortamenti (ce09a-d) are detail ("di cui") lines: the EBIT/profit formula reads
# only the aggregates ce08/ce09, so each sub-field is rolled into its parent
# aggregate AND stored under its full DB key (mirrors build_iv_cee). Promoted to
# module level (was a local dict inside extract_contrapposte_best_effort) so
# build_ce_from_vision reads the same single definition.
_CE_SUBFIELD_PARENT = {
    'ce08a_tfr': ('ce08a_tfr_accrual', 'ce08'),
    'ce08b': ('ce08b_salari_stipendi', 'ce08'),
    'ce08c': ('ce08c_oneri_sociali', 'ce08'),
    'ce08d': ('ce08d_altri_costi_personale', 'ce08'),
    'ce09a': ('ce09a_ammort_immateriali', 'ce09'),
    'ce09b': ('ce09b_ammort_materiali', 'ce09'),
    'ce09c': ('ce09c_svalutazioni', 'ce09'),
    'ce09d': ('ce09d_svalutazione_crediti', 'ce09'),
}

_ATTIVO_KEYS = ['sp01', 'sp02', 'sp03', 'sp04', 'sp05', 'sp06', 'sp07', 'sp08', 'sp09', 'sp10']

_PASSIVO_KEYS = ['sp11', 'sp12', 'sp13', 'sp14', 'sp15', 'sp16', 'sp17', 'sp18']

def _attivo_key(k: str) -> bool:
    return k in _ATTIVO_KEYS
