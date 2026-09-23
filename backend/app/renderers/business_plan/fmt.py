"""Formati italiani del Business plan. Il segno meno delle tabelle è U+2212, quello dei grafici è ASCII."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

ND = "n.d."
MINUS = "−"
Num = Optional[Decimal]


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _q(v, dec: int) -> Decimal:
    return _dec(v).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)


def _group(v, dec: int) -> str:
    s = format(abs(_q(v, dec)), f",.{dec}f")
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _signed(v, dec: int, suffix: str = "") -> str:
    if v is None:
        return ND
    sign = MINUS if _q(v, dec) < 0 else ""
    return f"{sign}{_group(v, dec)}{suffix}"


def eur(v: Num) -> str:
    return _signed(v, 0)


def pct(v: Num, dec: int = 2) -> str:
    return _signed(v, dec, "%")


def ratio(v: Num, dec: int = 2) -> str:
    return _signed(v, dec, "×")


def days(v: Num, dec: int = 1) -> str:
    return _signed(v, dec, " gg")


def value(v: Num, unit: str) -> str:
    """Formato per unità del modello v2: eur | percent | ratio | days | score."""
    if unit == "eur":
        return eur(v)
    if unit == "percent":
        return pct(v)
    if unit == "days":
        return days(v)
    return ratio(v) if unit == "ratio" else _signed(v, 2)


def _trim(s: str) -> str:
    return s[:-2] if s.endswith(",0") else s


def compact_eur(v: Num) -> str:
    """€ 4,11 mln · € 402,2 mila · € 150 mila · € 55 (sempre due decimali sui milioni)."""
    if v is None:
        return ND
    v = _dec(v)
    sign = MINUS if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000:
        body = f"{_group(a / 1_000_000, 2)} mln"
    elif a >= 1_000:
        body = f"{_trim(_group(a / 1_000, 1))} mila"
    else:
        body = _group(a, 0)
    return f"{sign}€ {body}"


def compact_range(a: Num, b: Num) -> str:
    """€ 4,11 → 4,67 mln · € 961 → 73 mila: una sola unità, scelta sul valore più grande."""
    if a is None or b is None:
        return ND
    a, b = _dec(a), _dec(b)
    top = max(abs(a), abs(b))
    if top >= 1_000_000:
        div, dec, unit = Decimal(1_000_000), 2, " mln"
    elif top >= 1_000:
        div, dec, unit = Decimal(1_000), 0, " mila"
    else:
        div, dec, unit = Decimal(1), 0, ""
    return f"€ {_signed(a / div, dec)} → {_signed(b / div, dec)}{unit}"


def pct_short(v: Num) -> str:
    """5% · 5,5% · 0%: per le liste di crescita («5% / 6% / 1%»)."""
    if v is None:
        return ND
    q = _q(v, 2)
    if q == q.to_integral_value():
        return _signed(q, 0, "%")
    return _trim_pct(q)


def _trim_pct(q: Decimal) -> str:
    s = _signed(q, 2, "")
    s = s.rstrip("0").rstrip(",")
    return s + "%"


def chart_num(v: float, dec: int = 0) -> str:
    """Etichetta di grafico: separatori italiani, segno meno ASCII come nel riferimento."""
    s = format(round(float(v), dec) + 0.0, f",.{dec}f")
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def prep(word: str, value_str: str) -> str:
    """«del 5%», «dell'1%», «dall'8,61%»: elisione davanti ai numeri che si leggono con vocale."""
    bare = value_str.lstrip(MINUS)
    integer = bare.split(",")[0].rstrip("%").replace(".", "")
    elide = integer.startswith("8") or integer in ("1", "11", "18")
    if not elide:
        return f"{word} {value_str}"
    return {"del": "dell'", "dal": "dall'", "al": "all'"}[word] + value_str
