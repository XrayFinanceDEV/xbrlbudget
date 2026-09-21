"""Exact source cells from explicitly qualified IV-CEE paths and dated columns.

Handles row-number / legal-path / current / prior / difference / percentage
tables. Neither row numbers nor variance columns can become monetary evidence.
"""
from collections import defaultdict
from decimal import Decimal
import re
import fitz

from importers.detail_enrichment import collect_source_rows
from importers.iv_cee_hierarchy import detail_fields, _net_profit_from_ce

ZERO = Decimal(0)


def extract_path_source(file_path):
    from importers.source_reconciliation import AGG, _category
    with fitz.open(file_path) as document:
        headings = []
        for page in document:
            words = page.get_text('words')
            dates = [w for w in words if re.fullmatch(r'\d{2}/\d{2}/20\d{2}', w[4])]
            for a in dates:
                for b in dates:
                    if b[0]>a[2] and abs(a[1]-b[1])<3 and int(a[4][-4:])-int(b[4][-4:])==1:
                        following = [w for w in words if w[0]>b[2] and abs(w[1]-b[1])<3 and 'differenz' in w[4].lower()]
                        if following:
                            centers = [(w[0]+w[2])/2 for w in (a,b,following[0])]
                            headings.append(centers)
    if not headings:
        return None
    # Consistent numeric bands across repeating headers, never infer periods
    # from naked monetary cells or the last two numbers in a row.
    centers = headings[0]
    if any(any(abs(x-y)>3 for x,y in zip(centers,h)) for h in headings):
        return None
    left = centers[0]-(centers[1]-centers[0])/2
    middle = (centers[0]+centers[1])/2
    right = (centers[1]+centers[2])/2
    tables = [defaultdict(dict),defaultdict(dict)]
    errors, evidence = [], [[],[]]
    section = None
    for row in collect_source_rows(file_path):
        label = re.sub(r'^\d+(?:\.\d+)?\s+', '', row.text).strip()
        lower = label.lower()
        if lower.startswith('stato patrimoniale attivo'):
            section = 'asset'
        elif lower.startswith('stato patrimoniale passivo'):
            section = 'liability'
        elif lower.startswith('conto economico'):
            section = 'ce'
        if section is None:
            continue
        match = re.match(r'^([A-E](?:\.[IVX]+)?(?:\.[\da-zA-Z]+(?:\s+(?:bis|ter|quater))?)*)\)', label)
        key = re.sub(r'\s+', '', match[1]) if match else (
            'total' if lower.startswith('stato patrimoniale') else
            'pretax' if lower.startswith('risultato prima delle imposte') else
            'result' if re.match(r'^21\)\s*utile',lower) else
            'tax' if re.match(r'^20\)',lower) else None)
        if key is None:
            continue
        for period in range(2):
            values = [v for v,x in zip(row.amounts,row.positions)
                      if (left<=x<middle if period==0 else middle<=x<right)]
            if len(values)!=1:
                continue
            value=values[0]
            previous=tables[period][section].get(key)
            if previous and previous[0]!=value:
                errors.append('contradictory legal path: '+key)
            tables[period][section][key]=(value,label,row)
            evidence[period].append({'row':row.id,'page':row.page,'path':key,'section':section,'value':str(value)})
    if not any('asset' in t and any(k.startswith('C.II.') for k in t['asset']) for t in tables):
        return None
    results=[]
    for period,t in enumerate(tables):
        err=list(errors)
        def val(section,path,required=False):
            entry=t[section].get(path)
            if required and entry is None:
                err.append('missing legal path: '+section+'/'+path)
            return entry[0] if entry else ZERO
        bs={a:ZERO for a in AGG}
        for path,index in (('B.I',1),('B.II',2),('B.III',3),('C.I',4),('C.III',7),('C.IV',8),('D',9)):
            bs[AGG[index]]=val('asset',path)
        for path,index in (('A.I',10),('A.IX',12),('B',13),('C',14),('E',17)):
            bs[AGG[index]]=val('liability',path)
        bs[AGG[11]]=val('liability','A',True)-bs[AGG[10]]-bs[AGG[12]]
        for path,field in (('A.II','sp12a_riserva_sovrapprezzo'),('A.III','sp12b_riserve_rivalutazione'),
                           ('A.IV','sp12c_riserva_legale'),('A.V','sp12d_riserve_statutarie'),
                           ('A.VI','sp12e_altre_riserve'),('A.VIII','sp12g_utili_perdite_portati')):
            bs[field]=val('liability',path)
        for section,path,index in (('asset','B.I',1),('asset','B.II',2),('asset','C.I',4),('liability','B',13)):
            for n,field in enumerate(detail_fields(AGG[index]),1):
                bs[field]=val(section,path+'.'+str(n))
        bs['sp04a_partecipazioni']=val('asset','B.III.1')
        bs['sp04d_altri_titoli']=val('asset','B.III.3')
        # Maturity quotas of financial receivables, if explicitly printed.
        financial=val('asset','B.III.2')
        long_fin=sum((v for k,(v,label,r) in t['asset'].items()
                      if k.startswith('B.III.2.') and 'esigibili oltre' in label.lower()),ZERO)
        bs['sp04b_crediti_immob_breve']=financial-long_fin
        bs['sp04c_crediti_immob_lungo']=long_fin
        for section,path,short,long,debt in (('asset','C.II',5,6,False),('liability','D',15,16,True)):
            for key,(value,label,row) in t[section].items():
                if not re.fullmatch(re.escape(path)+r'\.\d+(?:bis|ter|quater)?',key):
                    continue
                letter=_category(label.lower(),debt)
                quotas={}
                for child,(amount,caption,_) in t[section].items():
                    if not child.startswith(key+'.') or 'esigibili' not in caption.lower():
                        continue
                    maturity='long' if 'oltre' in caption.lower() else 'short' if 'entro' in caption.lower() else None
                    if maturity:
                        if maturity in quotas and quotas[maturity]!=amount:
                            err.append('conflicting maturity: '+key)
                        quotas[maturity]=amount
                if not quotas:
                    quotas={'long' if debt and any(w in label.lower() for w in ('finanz','mutu')) else 'short':value}
                if sum(quotas.values(),ZERO)!=value:
                    err.append('incomplete maturity: '+key)
                for maturity,index in (('short',short),('long',long)):
                    amount=quotas.get(maturity,ZERO)
                    field=next(f for f in detail_fields(AGG[index]) if f[4]==letter)
                    bs[field]=bs.get(field,ZERO)+amount
                    bs[AGG[index]]+=amount
            if bs[AGG[short]]+bs[AGG[long]]!=val(section,path,True):
                err.append('incomplete family: '+path)
        for a in AGG:
            fields=detail_fields(a)
            if any(f in bs for f in fields) and sum((bs.get(f,ZERO) for f in fields),ZERO)!=bs[a]:
                err.append('incomplete subfields: '+a)
        for section,indices in (('asset',slice(0,10)),('liability',slice(10,None))):
            total=sum((bs[k] for k in AGG[indices]),ZERO)
            bs['totale_attivo' if section=='asset' else 'totale_passivo']=total
            if total!=val(section,'total',True):
                err.append('incomplete statement: '+section)
        if bs['totale_attivo']!=bs['totale_passivo']:
            err.append('unbalanced printed statement')
        ce={}
        mapping={'A.1':'ce01_ricavi_vendite','A.2':'ce02_variazioni_rimanenze','A.4':'ce03_lavori_interni',
            'A.5':'ce04_altri_ricavi','B.6':'ce05_materie_prime','B.7':'ce06_servizi','B.8':'ce07_godimento_beni',
            'B.9':'ce08_costi_personale','B.10':'ce09_ammortamenti','B.11':'ce10_var_rimanenze_mat_prime',
            'B.12':'ce11_accantonamenti','B.13':'ce11b_altri_accantonamenti','B.14':'ce12_oneri_diversi',
            'C.15':'ce13_proventi_partecipazioni','C.16':'ce14_altri_proventi_finanziari','C.17':'ce15_oneri_finanziari',
            'tax':'ce20_imposte'}
        ce={f:val('ce',p) for p,f in mapping.items()}
        for path,fields in (('B.9',('ce08b_salari_stipendi','ce08c_oneri_sociali','ce08a_tfr_accrual',
                                   'ce08d_altri_costi_personale','ce08d_altri_costi_personale')),
                            ('B.10',detail_fields('ce09_ammortamenti'))):
            for letter,field in zip('abcde',fields):
                ce[field]=ce.get(field,ZERO)+val('ce',path+'.'+letter)
        ce_result=_net_profit_from_ce(ce)
        costs=sum((ce[mapping['B.'+str(i)]] for i in range(6,15)),ZERO)
        production=sum((ce[mapping['A.'+str(i)]] for i in (1,2,4,5)),ZERO)
        ce_ok=(costs==val('ce','B',True) and production==val('ce','A',True)
               and ce_result==val('ce','result',True)
               and ce_result+ce['ce20_imposte']==val('ce','pretax',True))
        if not ce_ok:
            err.append('income source does not cross-foot')
        bs['_source_credit_maturities_verified']=Decimal(1)
        bs['_source_debt_maturities_verified']=Decimal(1)
        mismatch=ce_result!=bs['sp13_utile_perdita']
        audit={'status':'declined' if err else 'verified','method':'qualified_legal_paths',
               'errors':err or (['Printed CE/SP profit mismatch'] if mismatch else []),
               'requires_review':bool(err) or mismatch,'income_verified':ce_ok,'evidence':evidence[period]}
        results.append((None,None,audit) if err else (bs,ce,audit))
    return results
