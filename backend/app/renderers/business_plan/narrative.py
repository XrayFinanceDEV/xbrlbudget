"""Testi a regole del Business plan (versione completa nel Task 6)."""
from decimal import Decimal


def subtitle_flussi(data) -> str:
    base = "Rendiconto finanziario di sintesi (metodo indiretto)."
    plan = [(data.columns[i], data.v("cf_variazione")[i]) for i in data.plan_idx]
    if not plan or any(v is None for _, v in plan):
        return base
    neg = [str(c.year) for c, v in plan if v < 0]
    if not neg:
        return base + " Il piano genera cassa in ogni anno, sufficiente a finanziare investimenti e rimborsi."
    return base + " La cassa diminuisce nel " + (neg[0] if len(neg) == 1 else ", ".join(neg[:-1]) + " e " + neg[-1]) + "."


def lettura_costi(data) -> list:
    return ["Lettura in preparazione."]
