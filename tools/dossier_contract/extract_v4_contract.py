#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Estrae il contratto di pagina del dossier dall'anteprima v4.

Fonte di verità: ``build-dossier-preview.py``, il generatore che ha prodotto
``report-finale-anteprima-v4.html``/``.pdf`` (33 pagine). Questo script:

1. ESEGUIsce il generatore in modalità contratto: le scritture su file sono
   disattivate (nessun artifact viene toccato) e si raccolgono ``sections``,
   ``cover``, ``CSS``, ``COLORS`` dal suo namespace.
2. PARSESA l'HTML finale di ogni pagina (mini-DOM con ``html.parser``) e ne
   ricava i blocchi nell'ordine in cui compaiono: ``kpi_rail``, ``chart``,
   ``table``, ``note``, ``text``, ``panel_grid``, ``toc``, ``meta_row``.
3. Produce ``contracts/dossier_page_contract.json`` (pagine, ordine, blocchi,
   layout) e ``contracts/dossier_style_contract.json`` (corpi in pt, pesi,
   colori, spaziature, margini di pagina) — mai scritti a mano.
4. ``--check``: rigenera e confronta con i JSON nel repo; esce 1 alla prima
   divergenza (il contratto non può invecchiare in silenzio).
5. Verifica incrociata (se ``--html`` / ``--pdf`` esistono): ogni grafico e
   ogni tabella dell'HTML/PDF v4 deve avere il suo blocco nel contratto.

I TITOLI della v4 (``title``/``headline``/``lede``) sono dinamici e su misura
del campione: nel contratto sono riferimento (``dynamic: true`` su
headline/lede, decisione del proprietario 2026-09-18). Ciò che vincola è
l'elenco e l'ordine delle pagine, la forma dei blocchi, i valori di stile.

Solo standard library: json, re, sys, hashlib, pathlib, html.parser,
subprocess (per ``pdftotext``, opzionale).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_SOURCE = Path(
    "/home/peter/DEV/budget/inbox/artifacts/2026-09-15-report-finale/build-dossier-preview.py"
)
DEFAULT_V4_HTML = Path(
    "/home/peter/DEV/budget/inbox/artifacts/2026-09-15-report-finale/report-finale-anteprima-v4.html"
)
DEFAULT_V4_PDF = Path(
    "/home/peter/DEV/budget/inbox/artifacts/2026-09-15-report-finale/report-finale-anteprima-v4.pdf"
)
REPO_ROOT = Path(__file__).resolve().parents[2]

PAGE_CONTRACT_NAME = "dossier_page_contract.json"
STYLE_CONTRACT_NAME = "dossier_style_contract.json"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Esecuzione del generatore in modalità contratto
# ─────────────────────────────────────────────────────────────────────────────

# Ogni riga deve essere trovata ed esattamente una volta: se il generatore
# cambia forma, l'estrazione fallisce forte invece di produrre un contratto
# silenziosamente diverso.
LINE_SUBS = {
    "if not (ROOT/'report-finale-anteprima-v1.html').exists():": "if False:  # contract mode: nessuna copia su disco",
    "fonts=''.join(": "fonts=''  # contract mode: i base64 dei font non servono",
    "print(TARGET": "print('contract mode: generazione completata, nessuna scrittura')",
    "TARGET.write_text(": "pass  # contract mode: report-finale-anteprima.html non viene toccato",
}


def run_generator(source: Path) -> dict:
    src = source.read_text(encoding="utf-8")
    lines = src.splitlines()
    hits = {needle: 0 for needle in LINE_SUBS}
    out = []
    for line in lines:
        for needle, repl in LINE_SUBS.items():
            if needle in line:
                hits[needle] += 1
                line = repl
                break
        out.append(line)
    for needle, count in hits.items():
        if count != 1:
            raise SystemExit(
                f"ATTENZIONE: il generatore v4 è cambiato: l'ancoraggio {needle!r} "
                f"compare {count} volte (atteso 1). Aggiornare questo script prima di fidarsi del contratto."
            )
    ns: dict = {"__name__": "__dossier_contract_source__", "__file__": str(source)}
    exec(compile("\n".join(out) + "\n", str(source) + " [contract]", "exec"), ns)
    return ns


# ─────────────────────────────────────────────────────────────────────────────
# 2. Mini-DOM
# ─────────────────────────────────────────────────────────────────────────────

VOID = {"br", "img", "meta", "hr", "input", "link"}


class Node:
    __slots__ = ("tag", "attrs", "kids", "text")

    def __init__(self, tag, attrs=None, text=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.kids = []
        self.text = text

    def __repr__(self):
        return f"<{self.tag} {self.attrs}>{self.text or ''}"


class DOMBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#doc")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].kids.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].kids.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
        # fine-tag orfano: ignorato

    def handle_data(self, data):
        if data.strip():
            self.stack[-1].kids.append(Node("#text", text=data.strip()))


def dom(fragment: str) -> Node:
    b = DOMBuilder()
    b.feed(fragment)
    return b.root


def classes(node: Node) -> set:
    return set((node.attrs.get("class") or "").split())


def text_of(node) -> str:
    if node.tag == "#text":
        return node.text
    return " ".join(text_of(k) for k in node.kids).strip()


def find(node, tag=None, cls=None):
    for k in node.kids:
        if k.tag == "#text":
            continue
        if (tag is None or k.tag == tag) and (cls is None or cls in classes(k)):
            yield k
        yield from find(k, tag, cls)


def child(node, tag=None, cls=None):
    for k in node.kids:
        if k.tag == "#text":
            continue
        if (tag is None or k.tag == tag) and (cls is None or cls in classes(k)):
            return k
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Blocchi dalla DOM di una pagina
# ─────────────────────────────────────────────────────────────────────────────

def chart_block(node) -> dict:
    title_el = child(node, "h3")
    sub_el = child(node, "div", "chart-sub")
    sub = text_of(sub_el) if sub_el else ""
    svg = child(node, "svg")
    legend_el = child(node, "div", "legend")
    kinds = {
        "dumbbell": sub.startswith("Confronto degli estremi"),
        "stacked": sub.startswith("Composizione percentuale"),
    }
    if kinds["dumbbell"]:
        kind = "dumbbell"
    elif kinds["stacked"]:
        kind = "stacked"
    else:
        kind = "bar" if svg is not None and any(True for _ in find(svg, "rect")) else "line"
    series = []
    if legend_el:
        order = [i for i, k in enumerate(node.kids) if k is legend_el]
        after_svg = bool(order and svg in node.kids and node.kids.index(svg) < order[0])
        for span in (k for k in legend_el.kids if k.tag == "span"):
            name = text_of(span).lstrip("○●").strip()
            series.append(name)
        legend_pos = "bottom" if after_svg else "top"
    else:
        legend_pos = None
    cats = []
    if svg is not None:
        if kind in ("bar", "line"):
            cats = [text_of(t) for t in find(svg, "text") if t.attrs.get("text-anchor") == "middle"]
        else:
            cats = [text_of(t) for t in find(svg, "text") if t.attrs.get("x") == "0"]
    unit = None
    if sub.endswith("· valori dimostrativi"):
        unit = sub.rsplit(" · ", 1)[0].strip()
    elif kind == "dumbbell":
        unit = "%"  # etichette dei valori: «a → b%» nel markup svg
    block = {
        "type": "chart",
        "kind": kind,
        "title": text_of(title_el) if title_el else None,
        "unit": unit,
        "n_series": len(series),
        "series": series,
        "legend": legend_pos,
        "n_categories": len(cats),
    }
    return block


def table_block(node, header_repeated: bool) -> dict:
    full = "full" in classes(node)
    table = child(node, "table")
    thead = child(table, "thead") if table else None
    headers = [text_of(th) for th in find(thead, "th")] if thead else []
    tbody = child(table, "tbody") if table else None
    rows = [k for k in (tbody.kids if tbody else []) if k.tag == "tr"]
    totals = sum(1 for r in rows if "total" in classes(r))
    indents = sum(1 for r in rows for c in r.kids if "indent" in classes(c))
    block = {
        "type": "table",
        "n_columns": len(headers),
        "n_rows": len(rows),
        "headers": headers,
        "variant": "full" if full else "standard",
        "header_repeated": header_repeated,
        "total_rows": totals,
        "indent_rows": indents,
        "evidence": {
            "header_repeated": "@media print thead{display:table-header-group} nel CSS del generatore",
        },
    }
    return block


def kpi_rail_block(node) -> dict:
    kpis = [
        {"label": text_of(k) if (k := child(c, "div", "k")) else None}
        for c in node.kids
        if c.tag == "div" and "kpi" in classes(c)
    ]
    return {"type": "kpi_rail", "n_kpis": len(kpis), "kpis": [k["label"] for k in kpis], "variant": "rail"}


def note_block(node) -> dict:
    title_el = child(node, "div", "comment-title")
    return {"type": "note", "title": text_of(title_el) if title_el else None}


def toc_block(node) -> dict:
    entries = list(find(node, "a"))
    columns = len([k for k in node.kids if k.tag == "div"]) or 1
    return {"type": "toc", "entries": len(entries), "columns": columns}


def meta_row_block(node, labels) -> dict:
    return {"type": "meta_row", "fields": labels}


TEXT_ROLE_BY_CLASS = {
    "source": "source",
    "blk": "heading",
}


def scan_blocks(kids, header_repeated, pending=None):
    """Ritorna i blocchi in ordine di documento. `pending` trasporta il
    caption di un h3/h4 visto prima del blocco strutturale successivo."""
    blocks = []
    for node in kids:
        if node.tag == "#text":
            continue
        cls = classes(node)
        if node.tag == "div" and "row" in cls:
            rail = child(node, "aside", "rail")
            main = child(node, "div", "main")
            if rail is not None:
                blocks.append(kpi_rail_block(rail))
            if main is not None:
                sub, _ = scan_blocks(main.kids, header_repeated)
                blocks.extend(sub)
            continue
        if node.tag == "aside" and "rail" in cls:
            blocks.append(kpi_rail_block(node))
            continue
        if node.tag == "div" and "chart" in cls:
            blocks.append(_captioned(chart_block(node), pending))
            pending = None
            continue
        if node.tag == "div" and ("tw" in cls):
            blocks.append(_captioned(table_block(node, header_repeated), pending))
            pending = None
            continue
        if node.tag == "div" and "comment" in cls:
            blocks.append(note_block(node))
            continue
        if node.tag == "div" and "panel-grid" in cls:
            children = []
            for panel in (k for k in node.kids if "panel" in classes(k)):
                sub, _ = scan_blocks(panel.kids, header_repeated)
                children.extend(sub)
            blocks.append({"type": "panel_grid", "panels": len(children), "children": children})
            continue
        if node.tag == "div" and "two" in cls:
            cols = [k for k in node.kids if k.tag == "div"]
            blocks.append(
                _captioned(
                    {
                        "type": "text",
                        "role": "two_columns",
                        "columns": len(cols),
                        "headings": [text_of(h) for c in cols for h in c.kids if h.tag == "h4"],
                        "items_per_column": [len(list(find(c, "li"))) for c in cols],
                    },
                    pending,
                )
            )
            pending = None
            continue
        if node.tag == "div" and ("toc" in cls or "attachment-toc" in cls):
            blocks.append(_captioned(toc_block(node), pending))
            pending = None
            continue
        if node.tag == "div" and "band" in cls:
            fields = [
                text_of(child(node, "div", "kicker")),
                text_of(child(node, "h1")),
                text_of(child(node, "div", "co")),
                text_of(child(node, "div", "meta")),
            ]
            blocks.append(meta_row_block(node, [f for f in fields if f]))
            continue
        if node.tag == "div" and "cover-kpis" in cls:
            blocks.append(
                {
                    "type": "kpi_rail",
                    "n_kpis": len([k for k in node.kids if k.tag == "div"]),
                    "kpis": [text_of(k) if (k := child(c, "div", "k")) else None for c in node.kids if c.tag == "div"],
                    "variant": "cover",
                }
            )
            continue
        if node.tag == "div" and "prep" in cls:
            fields = [text_of(k) for k in node.kids if k.tag == "div"]
            blocks.append(meta_row_block(node, fields))
            continue
        if node.tag == "div" and cls & {"cover-label", "cover-message", "cover-caption"}:
            role = next(iter(cls & {"cover-label", "cover-message", "cover-caption"}))
            blocks.append({"type": "text", "role": role, "text": text_of(node)})
            continue
        if node.tag in ("h3", "h4"):
            pending = text_of(node)
            continue
        if node.tag == "p":
            role = "source" if "source" in cls else "paragraph"
            blocks.append({"type": "text", "role": role, "text": text_of(node)})
            continue
        if node.tag in ("section", "div", "main", "aside", "header"):
            sub, carry = scan_blocks(node.kids, header_repeated, pending)
            blocks.extend(sub)
            pending = carry
            continue
    return blocks, pending


def _captioned(block, pending):
    if pending:
        block = {**block, "caption": pending}
    return block


# scan_blocks è chiamata anche con unpacking: definiamo un wrapper pulito
def blocks_of(html: str, header_repeated: bool):
    node = dom(html)
    blocks, _leftover = scan_blocks(node.kids, header_repeated)
    return blocks


def layout_of(html: str) -> dict:
    node = dom(html)
    rows = list(find(node, "div", "row"))
    grids = list(find(node, "div", "panel-grid"))
    if rows:
        form = "rail+main"
    elif grids:
        form = "full+panels"
    else:
        form = "full"
    return {"form": form, "rows": len(rows), "panel_grids": len(grids)}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Blocchi opzionali (contenuto v4 che il modello non ha)
# ─────────────────────────────────────────────────────────────────────────────
# Chiave: (page_id, tipo, match sul titolo/caption del blocco). Fonte: le
# mappature «assente» di mappatura-v4-pagine-1-11.md / -12-33.md (stessa
# cartella SDD del brief). Un blocco marcato `optional: true` NON è un
# obbligo per il prodotto: la sua assenza non è un difetto.
OPTIONAL_BLOCKS = {
    ("copertina", "meta_row", "Preparato"): (
        "costanti di deploy (fornitore, versione editoriale, data), non un campo del modello v2"
    ),
    ("sintesi", "text", "Decisioni"): (
        "elenco redazionale a due colonne scritto a mano nel campione: nel prodotto la "
        "personalizzazione vive nei commenti del piano editoriale, non in un blocco dati"
    ),
    ("allegato-E", "table", "calendario dei rimborsi"): (
        "tabella debito iniziale/nuovi finanziamenti/rimborsi/debito finale: assente nel modello "
        "(mappatura 12-33, pag. 29) — derivabile solo da un servizio dedicato, non un obbligo"
    ),
}


def mark_optional(page_id: str, blocks: list) -> list:
    out = []
    for b in blocks:
        hay = " ".join(
            str(b.get(k, ""))
            for k in ("title", "caption", "role", "text")
        ) + " " + " ".join(str(x) for x in (b.get("fields") or []))
        for (pid, btype, needle), reason in OPTIONAL_BLOCKS.items():
            if pid == page_id and btype == b.get("type") and needle in hay:
                b = {**b, "optional": True, "optional_reason": reason}
                break
        if b.get("type") == "panel_grid":
            b = {**b, "children": mark_optional(page_id, b["children"])}
        out.append(b)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 5. Contratto di pagina
# ─────────────────────────────────────────────────────────────────────────────

def css_flat(css: str):
    """→ dict[(media, selector)] = props. I blocchi @media vengono appiattiti
    con il loro contesto come chiave di media."""
    rules = {}
    i, n = 0, len(css)
    stack_media = ["all"]

    def parse(body, media):
        j = 0
        while j < len(body):
            b = body.find("{", j)
            if b < 0:
                break
            sel = body[j:b].strip()
            depth, k = 1, b + 1
            while k < len(body) and depth:
                if body[k] == "{":
                    depth += 1
                elif body[k] == "}":
                    depth -= 1
                k += 1
            inner = body[b + 1 : k - 1]
            if sel.startswith("@media"):
                parse(inner, sel[len("@media"):].strip())
            elif sel.startswith("@page"):
                for propsel, props in _split_decls(inner):
                    rules.setdefault((media, "@page" + ("" if propsel is None else " " + propsel)), {}).update(props)
            elif sel.startswith("@"):
                pass
            else:
                for group_sel in sel.split(","):
                    for propsel, props in _split_decls(inner):
                        rules.setdefault((media, group_sel.strip() + (" " + propsel if propsel else "")), {}).update(props)
            j = k
        return

    def _split_decls(text):
        # 'p{a:b}' dentro un blocco è un se annidato (es. @page dentro @media);
        # qui gestiamo sia le dichiarazioni dirette sia un eventuale selettore.
        decls, subs = [], []
        depth = 0
        cur = ""
        for ch in text:
            if ch == "{":
                depth += 1
                cur += ch
            elif ch == "}":
                depth -= 1
                cur += ch
            else:
                if depth == 0 and ch == ";":
                    decls.append(cur)
                    cur = ""
                else:
                    cur += ch
            if depth == 0 and ch == "}":
                subs.append(cur)
                cur = ""
        if cur.strip():
            (subs if depth == 0 and "{" in cur else decls).append(cur)
        props = {}
        for d in decls:
            if ":" in d:
                p, v = d.split(":", 1)
                props[p.strip()] = v.strip()
        out = [(None, props)] if props else []
        for s in subs:
            if "{" in s:
                sels, inner = s.split("{", 1)
                for psel, pr in _split_decls(inner.rstrip("}")):
                    out.append(((sels.strip() + (" " + psel if psel else "")), pr))
        return out

    parse(css, "all")
    return rules


def get_rule(rules, selector, prop, media="all"):
    val = rules.get((media, selector), {}).get(prop)
    if val is None:
        raise SystemExit(
            f"ATTENZIONE: regola CSS mancante: [{media}] {selector} {{ {prop} }} — "
            "il CSS del generatore v4 è cambiato, aggiornare il ruolo in questo script."
        )
    return val


def to_pt(value: str) -> float:
    m = re.fullmatch(r"(-?[\d.]+)(pt|px|mm)", value.strip())
    if not m:
        return value
    num, unit = float(m.group(1)), m.group(2)
    return round(num * 0.75, 3) if unit == "px" else num if unit == "pt" else round(num * 28.3465, 1)


TYPE_ROLES = (
    ("body", "corpo"),
    (".part", "occhiello"),
    (".act", "titolo_pagina"),
    (".lede", "sottotitolo"),
    (".v", "kpi_valore"),
    (".k", "kpi_etichetta"),
    ("h3", "titolo_blocco"),
    ("h4", "titolo_colonna"),
    ("table", "tabella"),
    ("th", "intestazione_tabella"),
    (".full table", "tabella_estesa"),
    (".chart svg text", "etichette_grafico"),
    (".panel .chart svg text", "etichette_grafico_pannelli"),
    (".chart-sub", "sottotitolo_grafico"),
    (".legend", "legenda"),
    (".comment-title", "titolo_nota"),
    (".comment p", "testo_nota"),
    (".source", "fonte"),
    (".sh-head", "intestazione_pagina_fissa"),
    (".sh-foot", "pie_pagina_fisso"),
    (".band h1", "copertina_titolo"),
    (".band .kicker", "copertina_kicker"),
    (".band .co", "copertina_azienda"),
    (".band .meta", "copertina_meta"),
    (".cover-label", "copertina_etichetta"),
    (".cover-message", "copertina_messaggio"),
    (".cover-caption", "copertina_didascalia"),
    (".cover-kpis .v", "copertina_kpi_valore"),
    (".cover-kpis .k", "copertina_kpi_etichetta"),
    (".toc h4", "indice_sezione"),
    (".toc a", "indice_voce"),
    (".attachment-toc a", "indice_allegati_voce"),
    (".prep", "copertina_prep"),
)


def style_contract(ns) -> dict:
    rules = css_flat(ns["CSS"])
    css_src = ns["CSS"]

    def raw(sel, prop, media="all"):
        return get_rule(rules, sel, prop, media)

    # :root è un unico blocco di dichiarazioni variabili
    root_block = re.search(r":root\{([^}]*)\}", css_src).group(1)
    colors = {}
    for decl in root_block.split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            colors[k.strip().lstrip("-")] = v.strip()

    src_text = Path(ns["__file__"]).read_text(encoding="utf-8")
    chart_strokes = {}
    for name, needle in (
        ("gridline", 'stroke="#E4E9EE"'),
        ("zero_axis", 'stroke="#5E6B78"'),
        ("dumbbell_link", 'stroke="#9CC0D8" stroke-width="3"'),
    ):
        if needle not in src_text:
            raise SystemExit(f"ATTENZIONE: tratto SVG {name} non trovato nel sorgente v4: {needle!r}")
        chart_strokes[name] = re.search(r"#[0-9A-Fa-f]{6}", needle).group(0)

    type_roles = {}
    for sel, name in TYPE_ROLES:
        r = rules.get(("all", sel))
        if r is None:
            raise SystemExit(
                f"ATTENZIONE: regola CSS mancante per il ruolo {name!r} (selettore {sel!r}) — "
                "il CSS del generatore v4 è cambiato, aggiornare TYPE_ROLES."
            )
        entry = {}
        if "font-size" in r:
            entry["size"] = {"css": r["font-size"], "pt": to_pt(r["font-size"])}
        for prop in ("font-weight", "line-height", "color", "letter-spacing", "text-transform", "font-family", "fill"):
            if prop in r:
                entry[prop.replace("-", "_")] = r[prop]
        type_roles[name] = entry

    def shorthand(value):
        parts = value.split()
        if len(parts) == 1:
            top = right = bottom = left = parts[0]
        elif len(parts) == 2:
            top = bottom = parts[0]; right = left = parts[1]
        elif len(parts) == 3:
            top = parts[0]; right = left = parts[1]; bottom = parts[2]
        else:
            top, right, bottom, left = parts[:4]
        return {"top": top, "right": right, "bottom": bottom, "left": left}

    spacing = {
        "rail_colonna": {"width": raw(".rail", "width")},
        "colonne_in_row": {"gap": raw(".row", "gap")},
        "kpi_riquadro": {"padding": shorthand(raw(".kpi", "padding")), "separatore": raw(".kpi", "border-top")},
        "occhiello_dopo": shorthand(raw(".part", "margin"))["bottom"],
        "titolo_pagina_dopo": shorthand(raw(".act", "margin"))["bottom"],
        "sottotitolo_dopo": shorthand(raw(".lede", "margin"))["bottom"],
        "titolo_blocco": {"margin": shorthand(raw("h3.blk", "margin")), "padding_top": raw("h3.blk", "padding-top"), "separatore": raw("h3.blk", "border-top")},
        "grafico_dopo": shorthand(raw(".chart", "margin"))["bottom"],
        "nota": {"margin_top": shorthand(raw(".comment", "margin"))["top"], "padding_top": raw(".comment", "padding").split()[0], "separatore": raw(".comment", "border-top")},
        "tabella_celle": shorthand(raw("td", "padding"))["top"],
        "tabella_estesa_celle": shorthand(raw(".full td", "padding"))["top"],
        "fonte": shorthand(raw(".source", "margin")),
        "pannelli_affiancati": {"gap": raw(".panel-grid", "gap"), "margin_top": shorthand(raw(".panel-grid", "margin"))["top"], "margin_bottom": shorthand(raw(".panel-grid", "margin"))["bottom"]},
        "indice_voce": shorthand(raw(".toc a", "padding"))["top"],
        "indice_allegati_voce": shorthand(raw(".attachment-toc a", "padding"))["top"],
        "due_colonne": {"gap": raw(".two", "gap")},
    }

    page = {
        "formato": "A4",
        "foglio": {"width": raw(".sheet", "width"), "height": raw(".sheet", "height")},
        "margini": shorthand(raw(".sheet", "padding")),
        "testata": {"top": raw(".sh-head", "top"), "left": raw(".sh-head", "left"), "right": raw(".sh-head", "right"), "font_size": raw(".sh-head", "font-size")},
        "pie_pagina": {"bottom": raw(".sh-foot", "bottom"), "border_top": raw(".sh-foot", "border-top"), "font_size": raw(".sh-foot", "font-size")},
        "copertina_banda": {"background": raw(".band", "background"), "padding": raw(".band", "padding"), "min_height": raw(".band", "min-height")},
        "print": {"@page_size": raw("@page", "size", "print"), "intestazione_tabella_ripetuta": raw("thead", "display", "print")},
    }

    return {
        "schema_version": 1,
        "source": _source_info(ns),
        "convenzioni": {
            "unita": "valori CSS originali conservati in 'css'; i px sono convertiti in pt ×0,75",
            "ruoli": "un ruolo per selettore: il layout del prodotto deve replicare corpo/pesi/colori qui, non inventarne di propri",
            "dinamica": "il contratto descrive forma e stile: nessun numero del campione vincola il prodotto",
        },
        "colors": {
            "semantic": colors,
            "chart_strokes": chart_strokes,
            "series_palette": list(ns["COLORS"]),
            "stato": {"good": raw(".good", "color"), "warn": raw(".warn", "color")},
        },
        "type": type_roles,
        "spacing": spacing,
        "page": page,
    }


    sheet = t(".sheet", "padding").split()
    page = {
        "formato": "A4",
        "size": {"width": t(".sheet", "width"), "height": t(".sheet", "height"), "css_margin": t("@page", "size", "print")},
        "margini_mm": {"top": sheet[0], "right": sheet[1], "bottom": sheet[2] if len(sheet) > 2 else sheet[0], "left": sheet[3] if len(sheet) > 3 else sheet[1]},
        "testata": {"top": t(".sh-head", "top"), "left": t(".sh-head", "left"), "right": t(".sh-head", "right")},
        "pie_pagina": {"bottom": t(".sh-foot", "bottom"), "border_top": t(".sh-foot", "border-top")},
        "contenitore_copertina": {"band_background": "var(--deep)", "band_padding": t(".band", "padding")},
    }

    return {
        "schema_version": 1,
        "source": _source_info(ns),
        "convenzioni": {
            "unita": "pt dove estratto da CSS in pt; i valori px del CSS sono convertiti ×0,75 (campo css conserva l'originale)",
            "percentuali": "assolute (25,5 = 25,5%)",
            "dinamica": "i colori dei dati sono solo di forma: nessun numero del campione è un obbligo",
        },
        "colors": {
            "semantic": colors,
            "chart_strokes": chart_strokes,
            "series_palette": palette,
            "stato": {"good": t(".good", "color"), "warn": t(".warn", "color")},
            "copertina": {"band_bg": "var(--deep)", "kicker_fg": t(".band .kicker", "color"), "meta_fg": t(".band .meta", "color")},
        },
        "type": type_roles,
        "spacing": spacing,
        "page": page,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Assemblaggio contratto di pagina
# ─────────────────────────────────────────────────────────────────────────────

def _source_info(ns) -> dict:
    src = Path(ns["__file__"]).read_bytes()
    return {
        "file": str(ns["__file__"]),
        "sha256": hashlib.sha256(src).hexdigest(),
        "generated_html_sections": len(ns["sections"]) + 1,
    }


def page_contract(ns) -> dict:
    rules = css_flat(ns["CSS"])
    header_repeated = "table-header-group" in get_rule(rules, "thead", "display", "print")

    pages = []
    cover = ns["cover"]
    cover_node = dom(cover)
    band = next(find(cover_node, "div", "band"), None)
    body = next(find(cover_node, "div", "cover-body"), None)
    blocks, _ = scan_blocks([band, body], header_repeated)
    pages.append(
        {
            "order": 1,
            "id": "copertina",
            "group": "COPERTINA",
            "titles": {
                "title": ns["DOCUMENT_TITLE"],
                "headline": next((b["text"] for b in blocks if b.get("role") == "cover-message"), None),
                "lede": next((b["text"] for b in blocks if b.get("role") == "cover-caption"), None),
                "dynamic": {"title": False, "headline": True, "lede": True},
            },
            "layout": {"form": "cover"},
            "priority": "executive",
            "blocks": mark_optional("copertina", blocks),
            "note_expected": True,
        }
    )

    for i, s in enumerate(ns["sections"]):
        pid = s["id"]
        body_html = s["body"]
        # segnaposto non più sostituito = indice allegati vuoto
        blocks = blocks_of(body_html, header_repeated)
        pages.append(
            {
                "order": i + 2,
                "id": pid,
                "group": s["group"],
                "titles": {
                    "title": s["title"],
                    "headline": s["headline"],
                    "lede": s["lede"],
                    "dynamic": {"title": False, "headline": True, "lede": True},
                },
                "layout": layout_of(body_html),
                # Decisione del proprietario 2026-09-18: la parte executive (pag. 1-18)
                # segue l'artifact con priorità alta; i prospetti 19-33 della bozza sono
                # già accettabili e le loro differenze hanno priorità bassa.
                "priority": "allegati" if (i + 2) >= 19 else "executive",
                "blocks": mark_optional(pid, blocks),
                "note_expected": True,
            }
        )

    total = len(pages)
    for p in pages:
        notes = [b for b in _flatten(p["blocks"]) if b["type"] == "note"]
        p["has_note"] = bool(notes)

    return {
        "schema_version": 1,
        "source": _source_info(ns),
        "binding": {
            "vincolanti": ["ordine e elenco delle pagine", "sequenza e forma dei blocchi per pagina", "valori di stile (dossier_style_contract.json)", "la nota di commento presente su ogni pagina"],
            "priorita": "pagine 1-18 (priority=executive): il layout dell'artifact è l'obiettivo, priorità alta; pagine 19-33 (priority=allegati): la bozza attuale è già accettabile, differenze a priorità bassa (proprietario 2026-09-18)",
            "riferimento": ["title/headline/lede: testo del campione, nel prodotto titoli neutri + personalizzazione nei commenti del piano editoriale (dynamic: true)"],
            "non_vincolanti": ["numeri e valori mostrati: vengono dal modello v2"],
        },
        "page_count": total,
        "chrome": {
            "header": {"sinistra": "<company> · Report finale della pratica", "destra": "<title di pagina>", "from": "pages template nel generatore v4"},
            "footer": {"sinistra": "nota unità di misura", "destra": "<n> / <totale>", "from": "pages template nel generatore v4"},
        },
        "totals": _totals(pages),
        "pages": pages,
    }


def _flatten(blocks):
    for b in blocks:
        yield b
        if b["type"] == "panel_grid":
            yield from _flatten(b["children"])


def _totals(pages):
    counts = {}
    for b in _flatten([blk for p in pages for blk in p["blocks"]]):
        counts[b["type"]] = counts.get(b["type"], 0) + 1
    charts = {}
    for b in _flatten([blk for p in pages for blk in p["blocks"]]):
        if b["type"] == "chart":
            charts[b["kind"]] = charts.get(b["kind"], 0) + 1
    return {"blocks": counts, "chart_kinds": charts, "pages_with_note": sum(1 for p in pages if p["has_note"])}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Verifica incrociata contro HTML e PDF v4
# ─────────────────────────────────────────────────────────────────────────────

def crosscheck_html(contract: dict, html_path: Path) -> list:
    """Ogni grafico/tabella dell'HTML v4 deve avere un blocco nel contratto."""
    errors = []
    h = html_path.read_text(encoding="utf-8")
    sections = re.findall(r'<section[^>]*class="sheet[^"]*"[^>]*>(.*?)</section>', h, re.S)
    if len(sections) != contract["page_count"]:
        errors.append(f"sezioni HTML {len(sections)} ≠ pagine contratto {contract['page_count']}")
        return errors
    for i, (sec, page) in enumerate(zip(sections, contract["pages"]), start=1):
        n_chart = sec.count('<div class="chart">')
        n_table = sec.count("<table>")
        got_chart = sum(1 for b in _flatten(page["blocks"]) if b["type"] == "chart")
        got_table = sum(1 for b in _flatten(page["blocks"]) if b["type"] == "table")
        if n_chart != got_chart:
            errors.append(f"pag {i} {page['id']}: grafici HTML {n_chart} ≠ contratto {got_chart}")
        if n_table != got_table:
            errors.append(f"pag {i} {page['id']}: tabelle HTML {n_table} ≠ contratto {got_table}")
    return errors


def crosscheck_pdf(contract: dict, pdf_path: Path) -> list:
    """Verifica sul PDF v4: numero di pagine e presenza dei sottotitoli dei
    grafici (bar/line → «valori dimostrativi», stacked, dumbbell) pagina per
    pagina, per quanto pdftotext consente."""
    errors = []
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, timeout=60
        )
        text = out.stdout.decode("utf-8", "replace")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [f"pdftotext non eseguibile su {pdf_path}"]
    pages = text.split("\f")
    pages = [p for p in pages if p.strip()]
    if len(pages) != contract["page_count"]:
        errors.append(f"pagine PDF {len(pages)} ≠ contratto {contract['page_count']}")
        return errors
    for i, (ptext, page) in enumerate(zip(pages, contract["pages"]), start=1):
        flat = re.sub(r"\s+", " ", ptext)
        want = sum(1 for b in _flatten(page["blocks"]) if b["type"] == "chart")
        got = len(re.findall(r"(?:migliaia|%|volte|giorni) · valori dimostrativi", flat))
        got += flat.count("Composizione percentuale") + flat.count("Confronto degli estremi")
        if want != got:
            errors.append(f"pag {i} {page['id']}: grafici PDF {got} ≠ contratto {want}")
        for b in _flatten(page["blocks"]):
            if b["type"] == "chart" and b.get("title") and re.sub(r"\s+", " ", b["title"]) not in flat:
                errors.append(f"pag {i} {page['id']}: titolo grafico {b['title']!r} non presente nel PDF")
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# 8. Main
# ─────────────────────────────────────────────────────────────────────────────

def canon(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "contracts")
    ap.add_argument("--check", action="store_true", help="rigenera e confronta con i JSON nel repo")
    ap.add_argument("--html", type=Path, default=DEFAULT_V4_HTML, help="HTML v4 per la verifica incrociata")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_V4_PDF, help="PDF v4 per la verifica incrociata")
    ap.add_argument("--no-crosscheck", action="store_true")
    args = ap.parse_args(argv)

    if not args.source.exists():
        raise SystemExit(f"sorgente v4 non trovata: {args.source}")
    ns = run_generator(args.source)
    contract = page_contract(ns)
    style = style_contract(ns)

    ok = True
    for name, obj in ((PAGE_CONTRACT_NAME, contract), (STYLE_CONTRACT_NAME, style)):
        path = args.out_dir / name
        if args.check:
            if not path.exists():
                print(f"MANCANTE: {path}")
                ok = False
                continue
            if path.read_text(encoding="utf-8") != canon(obj):
                print(f"DIVERGENTE: {path} non corrisponde più alla sorgente v4")
                ok = False
            else:
                print(f"ok {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(canon(obj), encoding="utf-8")
            print(f"scritto {path}")

    if not args.no_crosscheck:
        if args.html.exists():
            errs = crosscheck_html(contract, args.html)
            print("crosscheck HTML:", "ok" if not errs else "")
            for e in errs:
                print("  ", e)
                ok = False
        else:
            print(f"crosscheck HTML saltato (non trovato: {args.html})")
        if args.pdf.exists():
            errs = crosscheck_pdf(contract, args.pdf)
            print("crosscheck PDF:", "ok" if not errs else "")
            for e in errs:
                print("  ", e)
                ok = False
        else:
            print(f"crosscheck PDF saltato (non trovato: {args.pdf})")

    t = contract["totals"]
    print(f"pagine: {contract['page_count']} · blocchi: {t['blocks']} · tipi grafico: {t['chart_kinds']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
