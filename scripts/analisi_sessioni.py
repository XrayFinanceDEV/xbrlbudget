#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
analisi_sessioni.py — estrattore di metadati dalle trascrizioni di Claude Code e di pi.

Scansiona le trascrizioni JSONL del progetto (sessioni principali + trascrizioni dei
subagenti) e produce, per ogni sessione principale, una "scheda" in markdown; in piu'
scrive aggregati complessivi in JSON e markdown.

Uso:
    python scripts/analisi_sessioni.py --da 2026-08-24 --out .superpowers/retrospettiva
    python scripts/analisi_sessioni.py --da 2026-09-11 --a 2026-09-19 --out <dir>

Dall'11/09 legge anche le sessioni pi (worker su modello locale gx10/Qwen), una run per
file JSONL in ~/.pi/agent/sessions/--<percorso-worktree>--/*.jsonl con "budget" nel nome:
worktree, modello, turni, strumenti, comandi falliti, git commit, token (il formato li
riporta per messaggio) e compattazioni.

Cosa legge (sola lettura):
    <projects-dir>/*.jsonl                      sessioni principali
    <projects-dir>/<sessionId>/subagents/
            agent-<agentId>.jsonl               trascrizione del subagente
            agent-<agentId>.meta.json           description / agentType / model / toolUseId

Cosa NON fa:
    - non carica mai un file intero in memoria: legge una riga alla volta in streaming;
    - non copia mai il contenuto dei risultati degli strumenti (file letti, output di
      comandi): nei report finiscono solo metadati, conteggi, e i primi 300 caratteri
      dei messaggi del proprietario;
    - maschera ogni stringa che somiglia a una chiave/segreto/indirizzo email e i nomi delle aziende
      dei dati di test.

Una riga malformata o non-JSON viene contata e saltata, mai fatta fallire.

--------------------------------------------------------------------------
REGOLA DI CLASSIFICAZIONE DEL TIPO DI LAVORO (un solo punto di verita', qui)
--------------------------------------------------------------------------
Si guarda, in ordine, la `description` dell'agente (e, in subordine, il suo
`subagent_type` / `name`), con matching a parola chiave (regex, case-insensitive, solo
`\b` in apertura per accettare i prefissi italiani: `collaud` matcha "Collaudo").
Vince la regola la cui parola compare PRIMA nel testo (a parita' di posizione, la regola
col numero piu' basso); la regex matchata viene registrata nell'aggregato perche' la
classificazione sia verificabile a posteriori. Gli agenti di un workflow fan-out
(`subagent_type == "workflow-subagent"`, senza description) finiscono nel bucket
"workflow (fan-out)" e non vengono spacciati per lavoro classificato:

    1. ri-revisione      \b(re-?\s?review|re-?check|reverify|rigiro|contro-?revisione)
    2. collaudo          \b(collaud|playwright|browser|e2e|screenshot|ui[- ]?test|tester|smoke|banco di par|exploratory)
    3. revisione         \b(review|revis|quality|spec compliance|audit|verific)
    4. scrittura piani   \b(plan|piano|brief|spec|design|proposta|roadmap|issue|ticket|contratti|riallinea|doc)
    5. implementazione   \b(implement|fix|task[- ]\d+|correggi|patch|apply|refactor|follow-?up|crea|chiudi)
    6. ricognizione      \b(map|explore|search|survey|find|inventar|analys|check|where|ricogniz|studi)
                         (anche subagent_type == "Explore")
    7. altro             (nessuna corrispondenza)

L'ordine delle regole conta solo a parita' di posizione nel testo: "Review Task 5
(spec + quality)" e' revisione perche' "review" sta prima di "spec"; "Fix rilievi del
collaudo" e' implementazione perche' "fix" sta prima di "collaud". Il matching e' a
inizio parola, quindi "preview" NON matcha \breview.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ------------------------------------------------------------------ parametri

DEFAULT_PROJECTS = "/home/peter/.claude/projects/-home-peter-DEV-budget"
PAUSE_Soglie = 30 * 60          # pausa oltre la quale il tempo non conta come "attivo"
CARD_BUDGET_BYTES = 15000       # tetto indicativo della scheda
OWNER_SNIPPET = 300             # caratteri dei messaggi del proprietario

# ------------------------------------------------------------------ redazione

SECRET_RES = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}"), "[omesso]"),                    # API key
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]{2,}){0,2}"), "[omesso]"),  # JWT
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{6,}"), "Bearer [omesso]"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)\b\s*[=:]\s*(?!\[)\S+"),
     r"\1=[omesso]"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]*[A-Za-z0-9\-]"), "[omesso]"),  # email e prompt `utente@host`
    # Catena con un simbolo in mezzo (una chiave incollata senza etichetta: `FF2026*5aot...`):
    # almeno 4 alfanumerici prima e 6 dopo, e almeno una cifra. Il simbolo non è mai l'ultimo
    # carattere, così i suffissi di codice (`foo_BAR_1+`, `x+1234567`) restano interi.
    (re.compile(r"\b(?=[A-Za-z\d]{4,}[*#$+@%&!][A-Za-z\d]{6,}\b)(?=[A-Za-z\d]*\d)"
                r"[A-Za-z\d]{2,}[*#$+@%&!][A-Za-z\d]+"), "[omesso]"),
    # Parola-chiave di credenziale che precede il valore senza `=`
    (re.compile(r"(?i)\b(password|passwd|credentials?|chiave|secret)\b(?!\s*[=:])[^\nA-Za-z0-9]{0,4}"
                r"(?!\[)[A-Za-z\d][A-Za-z\d.*#$+@%&!_-]{5,}"), r"\1 [omesso]"),
]

# Nomi di azienda nei dati di test: forma giuridica italiana, con il pre-contesto.
COMPANY_RES = [
    re.compile(r"\b(?:[A-Za-zÀ-ÿ0-9.&'\-]+\s+){0,4}"
               r"(?:S\.?\s?p\.?\s?A\.?|S\.?\s?r\.?\s?l\.?|S\.?\s?C\.?\s?A\.?|SPA|SRL|SAPA)\b"),
]

# Elenco letterale: nomi delle aziende che compaiono nei dati di prova e nel DB
# (distinti per nome, in maiuscolo). Mascherati anche senza forma giuridica dietro.
COMPANY_NAMES = [
    "AIC SRL", "AIC", "AITEC SRL", "AITEC", "SALETTI MECCANICA", "UNICARTON",
    "ELLEVI SRL", "ELLEVI", "GCGROUP", "FACCHINETTI", "ROSSI MECCANICA",
    "IMPORTED COMPANY", "TEST MANUFACTURING", "INDUSTRIA TEST", "PROVA AMBIENTA",
    "PROVA SRL", "PLAYWRIGHT STARTUP TEST", "PLAYWRIGHT VERIFY CO",
    "STARTUP TEST PRATICA", "RECHECK PRATICA AZIENDA NUOVA",
    "FERRAMENTA",   # non nel DB di sviluppo: compare nei transcript come azienda di prova
]
_COMPANY_RX = re.compile(
    r"(?<![A-Za-z0-9])(" +
    "|".join(re.escape(n) for n in sorted(COMPANY_NAMES, key=len, reverse=True)) +
    r")(?:\s+(?:S\.?r\.?l\.?|S\.?p\.?A\.?|S\.?C\.?A\.?|SRL|SPA|SAPA))?\b",
    re.I)


def add_company_names(names):
    """Aggiunge nomi di azienda all'elenco di redazione (chiamato dal DB, se leggibile)."""
    for n in names or []:
        n = (n or "").strip()
        if len(n) >= 4 and n.upper() not in COMPANY_NAMES:
            COMPANY_NAMES.append(n.upper())
    global _COMPANY_RX
    _COMPANY_RX = re.compile(
        r"(?<![A-Za-z0-9])(" +
        "|".join(re.escape(x) for x in sorted(COMPANY_NAMES, key=len, reverse=True)) +
        r")(?:\s+(?:S\.?r\.?l\.?|S\.?p\.?A\.?|S\.?C\.?A\.?|SRL|SPA|SAPA))?\b", re.I)

# Rumore di sistema che non e' un messaggio del proprietario.
NON_OWNER_PREFIXES = (
    "<local-command-caveat>", "<local-command-stdout>", "<command-name>",
    "<command-message>", "<task-notification>", "<task-id>",
    "This session is being continued from a previous conversation",
    "[Request interrupted by user]", "<total_tokens>", "Caveat:",
)

WORK_RULES = [
    ("ri-revisione", r"\b(re-?\s?review|re-?check|reverify|rigiro|contro-?revisione)"),
    ("collaudo", r"\b(collaud|playwright|browser|e2e|screenshot|ui[- ]?test|tester|smoke|manual[- ]test|banco di par|exploratory)"),
    ("revisione", r"\b(review|revis|quality|spec compliance|audit|verific)"),
    ("scrittura di piani", r"\b(plan|piano|brief|spec|design|proposta|proposal|roadmap|issue|ticket|contratti|documenta|riallinea|doc\b)"),
    ("implementazione", r"\b(implement|fix|task[- ]\d+|correggi|patch|apply|refactor|follow-?up|write|crea|chiudi)"),
    ("ricognizione", r"\b(map|explore|search|survey|find|inventar|riassun|analys|analyz|check|where|read-?only|ricogniz|studi)"),
]
WORK_TYPES = [r[0] for r in WORK_RULES] + ["workflow (fan-out)", "altro"]

RE_TS = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')


# Un nome in MAIUSCOLE dopo una di queste prefiche è l'azienda sotto prova: `record 2025 di
# ROSSO`, `we are testing ROSSO`, `admin >> ROSSO`. Sono le uniche costruzioni con cui i transcript
# nominano un'azienda che non sta nel DB; il nome nudo in mezzo a una frase non viene toccato, e
# una forma già mascherata non viene mascherata due volte.
COMPANY_CTX = re.compile(
    r"(?P<pre>(?i:record\s+\d{4}\s+di|testing|testing\s+su|>>)\s+)"
    r"(?!\[)"
    r"(?P<nome>[A-ZÀ-Ü][A-ZÀ-Ü0-9](?:[A-ZÀ-Ü0-9 ]{2,30}[A-ZÀ-Ü0-9])?)(?![a-zà-ü])"
)


def redact(text: str) -> str:
    """Maschera segreti e nomi di azienda. Idempotente su testo gia' pulito."""
    if not text:
        return ""
    out = text
    for rx, rep in SECRET_RES:
        out = rx.sub(rep, out)
    for rx in COMPANY_RES:
        out = rx.sub("[azienda]", out)
    out = _COMPANY_RX.sub("[azienda]", out)
    out = COMPANY_CTX.sub(lambda m: m["pre"] + "[azienda]", out)
    return out.replace("\r", " ").replace("\n", " ").strip()


def classify(desc: str, subagent_type: str = "", name: str = ""):
    """(tipo_lavoro, regex_matchata) secondo la REGOLA descritta nel docstring.

    Vince la regola la cui parola compare PRIMA nella stringa (a parita' di posizione,
    vince la regola con il numero piu' basso): cosi' 'Fix rilievi del collaudo' e'
    implementazione e 'Collaudo del wizard' e' collaudo.
    """
    if (subagent_type or "").lower() == "workflow-subagent":
        return "workflow (fan-out)", "subagent_type=workflow-subagent"
    hay = " ".join(x for x in (desc or "", subagent_type or "", name or ""))
    best = None
    for idx, (tipo, pat) in enumerate(WORK_RULES):
        m = re.search(pat, hay, re.I)
        if m and (best is None or (m.start(), idx) < best[0]):
            best = ((m.start(), idx), tipo, m.group(0))
    if best:
        return best[1], best[2]
    if (subagent_type or "").lower() == "explore":
        return "ricognizione", "subagent_type=Explore"
    return "altro", ""


def parse_ts(s):
    if not isinstance(s, str) or not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt(dt, tz=None):
    if dt is None:
        return "—"
    if tz:
        dt = dt.astimezone(tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fmt_dur(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def model_family(m):
    # 'opus' | 'sonnet' | 'haiku' | 'fable' | 'pi' | 'qwen' dagli id/alias dei modelli
    s = (m or "").lower()
    for k in ("opus", "sonnet", "haiku", "fable", "qwen", "pi"):
        if k in s:
            return k
    return None


def human(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


# ------------------------------------------------------------------ lettura

def iter_lines(path):
    """Rende (record|None, ok_bool) riga per riga, senza mai caricare il file."""
    with io.open(path, "r", encoding="utf-8", errors="replace", buffering=1 << 22) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield line


class Tally:
    def __init__(self):
        self.lines = 0
        self.bad = 0

    def add(self, n=1):
        self.lines += n


# ------------------------------------------------------------------ subagenti

def scan_subagent(path, tally):
    """Metadati di una trascrizione di subagente: modello, token, strumenti, durata, file scritti."""
    out = {
        "file": os.path.basename(path),
        "model": None, "models": Counter(),
        "first": None, "last": None,
        "tool_calls": 0, "tools": Counter(),
        "in": 0, "out": 0, "cache_read": 0, "cache_creation": 0, "thinking": 0,
        "api_errors": 0, "interrupts": 0,
        "files_written": [],
        "reports": [],
    }
    for line in iter_lines(path):
        tally.add()
        if not line.startswith("{"):
            tally.bad += 1
            continue
        m = RE_TS.search(line)
        if m:
            ts = parse_ts(m.group(1))
            if ts:
                if out["first"] is None:
                    out["first"] = ts
                out["last"] = ts
        if '"apiErrorStatus"' in line or '"isApiErrorMessage"' in line:
            out["api_errors"] += 1
        if "interruptedMessageId" in line:
            out["interrupts"] += 1
        if '"tool_use"' not in line and '"usage"' not in line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            tally.bad += 1
            continue
        if rec.get("type") != "assistant":
            continue
        msg = rec.get("message") or {}
        mdl = msg.get("model")
        if mdl and mdl != "<synthetic>":
            out["models"][mdl] += 1
        u = msg.get("usage") or {}
        if u:
            out["in"] += int(u.get("input_tokens") or 0)
            out["out"] += int(u.get("output_tokens") or 0)
            out["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
            out["cache_creation"] += int(u.get("cache_creation_input_tokens") or 0)
            det = u.get("output_tokens_details") or {}
            out["thinking"] += int(det.get("thinking_tokens") or 0)
        cont = msg.get("content")
        if isinstance(cont, list):
            for blk in cont:
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    out["tool_calls"] += 1
                    out["tools"][blk.get("name") or "?"] += 1
                    if blk.get("name") in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                        fp = (blk.get("input") or {}).get("file_path") or ""
                        if fp:
                            out["files_written"].append(fp)
                            if re.search(r"(report|esito|resoconto)\.md$", fp, re.I):
                                out["reports"].append(fp)
    out["model"] = out["models"].most_common(1)[0][0] if out["models"] else None
    return out


# ------------------------------------------------------------------ sessioni

def scan_session(path, da, fine, tz):
    sid = os.path.splitext(os.path.basename(path))[0]
    sdir = os.path.join(os.path.dirname(path), sid)
    t = Tally()
    S = {
        "id": sid, "path": path, "lines": 0, "bad": 0,
        "first": None, "last": None, "active_s": 0.0,
        "owner_msgs": [], "owner_n": 0, "slash_cmds": [],
        "skills": [], "agents": {}, "agent_order": [], "resumes": [],
        "questions": [], "compactions": [], "api_errors": [], "quota_events": [],
        "interrupts": [], "git_commits": [], "git_merges": [], "orca_cmds": [],
        "tools": Counter(), "tool_errors": Counter(), "errors_total": 0,
        "bash_cmds": Counter(), "sleep_s": 0, "n_sleep": 0,
        "models_main": Counter(), "tok_main": Counter(),
        "cwd": None, "branches": Counter(), "version": Counter(),
        "cost_state": None, "n_task_notifications": 0, "in_range_n": 0,
        "subagents_meta": {},
    }

    # 1) metadati dei subagenti presenti sul disco (fonte autonoma, gia' filtrati dal
    #    pattern dei nomi; possono esistere agenti senza tool_use nel transcript madre,
    #    perche' lanciati da uno slash-command).
    for meta_path in sorted(glob.glob(os.path.join(sdir, "**", "agent-*.meta.json"), recursive=True)):
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception:
            t.bad += 1
            continue
        aid = re.sub(r"^agent-|\.meta\.json$", "", os.path.basename(meta_path))
        jsonl = meta_path[: -len(".meta.json")] + ".jsonl"
        S["subagents_meta"][aid] = {
            "meta": meta, "jsonl": jsonl if os.path.exists(jsonl) else None,
        }

    ts_events = []

    def agent(aid):
        if aid not in S["agents"]:
            S["agents"][aid] = {
                "id": aid, "tool_use_id": None, "description": None,
                "subagent_type": None, "model_requested": None, "isolation": None,
                "launched_at": None, "finished_at": None, "status": None,
                "notify_tokens": None, "notify_tool_uses": None, "notify_duration_ms": None,
                "result_head": None, "resumes": 0, "n_notifications": 0,
                "transcript": None,
            }
            S["agent_order"].append(aid)
        return S["agents"][aid]

    name_by_tooluse = {}
    answers = {}

    def relink(old_key, new_key):
        """Rinomina la chiave di un agente quando il vero agentId arriva dal tool_result."""
        if old_key == new_key or new_key in S["agents"] or old_key not in S["agents"]:
            return S["agents"].get(new_key) or S["agents"].get(old_key)
        S["agents"][new_key] = S["agents"].pop(old_key)
        S["agents"][new_key]["id"] = new_key
        i = S["agent_order"].index(old_key)
        S["agent_order"][i] = new_key
        return S["agents"][new_key]

    for line in iter_lines(path):
        t.add()
        if not line.startswith("{"):
            t.bad += 1
            continue
        try:
            rec = json.loads(line)
        except Exception:
            t.bad += 1
            continue
        ts = parse_ts(rec.get("timestamp"))
        if ts is not None:
            if da <= ts < fine:
                ts_events.append(ts)
                S["in_range_n"] += 1
        if rec.get("isSidechain"):
            continue
        typ = rec.get("type")
        if ts is not None and (ts >= fine or ts < da):
            continue
        if rec.get("cwd"):
            S["cwd"] = rec["cwd"]
        if rec.get("gitBranch"):
            S["branches"][rec["gitBranch"]] += 1
        if rec.get("version"):
            S["version"][rec["version"]] += 1

        # ---- costo cumulativo (snapshot a fine sessione)
        if typ == "cost-state":
            S["cost_state"] = rec

        # ---- compattazioni
        if typ == "system" and rec.get("subtype") == "compact_boundary":
            cm = rec.get("compactMetadata") or {}
            S["compactions"].append({
                "ts": ts, "trigger": cm.get("trigger"),
                "pre_tokens": cm.get("preTokens"), "post_tokens": cm.get("postTokens"),
                "dropped_cum": cm.get("cumulativeDroppedTokens"),
                "duration_ms": cm.get("durationMs"),
            })

        # ---- messaggi
        if typ == "user":
            msg = rec.get("message") or {}
            cont = msg.get("content")
            txts = []
            if isinstance(cont, str):
                txts = [cont]
            elif isinstance(cont, list):
                for blk in cont:
                    if isinstance(blk, dict) and blk.get("type") == "text":
                        txts.append(blk.get("text") or "")
                    elif isinstance(blk, dict) and blk.get("type") == "tool_result":
                        if blk.get("is_error"):
                            S["tool_errors"][name_by_tooluse.get(
                                blk.get("tool_use_id"), "?")] += 1
                            S["errors_total"] += 1
                        c = blk.get("content")
                        nested = c if isinstance(c, str) else (
                            " ".join(b.get("text", "") for b in c
                                     if isinstance(b, dict) and b.get("type") == "text")
                            if isinstance(c, list) else "")
                        if not isinstance(nested, str):
                            nested = ""
                        m_aid = re.search(r"agentId:\s*([0-9a-f]{10,})", nested)
                        if m_aid:
                            relink("tu:" + str(blk.get("tool_use_id")), m_aid.group(1))
                        if "Your questions have been answered" in nested:
                            answers[blk.get("tool_use_id")] = redact(nested)[:1200]
            for txt in txts:
                if txt.startswith("<task-notification>") or "task-notification" in txt[:40]:
                    S["n_task_notifications"] += 1
                    body = txt
                    aid = re.search(r"<agentId>([0-9a-f]{6,})</agentId>", body)
                    tid = re.search(r"<task-id>([0-9a-f]{6,})</task-id>", body)
                    st = re.search(r"<status>([^<]*)</status>", body)
                    su = re.search(r"<usage>(.*?)</usage>", body, re.S)
                    sm = re.search(r"<summary>(.*?)</summary>", body, re.S)
                    ru = re.search(r"Resuming agent ([0-9a-f]{6,})", body)
                    cand = (aid.group(1) if aid else (tid.group(1) if tid else None))
                    usage = {}
                    if su:
                        usage = {k: v for k, v in re.findall(
                            r"<(subagent_tokens|tool_uses|total_tokens|duration_ms)>(\d+)</\1>",
                            su.group(1))}
                    if cand and (st or usage or sm):
                        a = agent(cand)
                        if st:
                            a["status"] = st.group(1).strip()
                        if sm:
                            a["result_head"] = redact(sm.group(1).strip())[:120]
                        if usage.get("subagent_tokens"):
                            a["notify_tokens"] = int(usage["subagent_tokens"])
                        if usage.get("tool_uses"):
                            a["notify_tool_uses"] = int(usage["tool_uses"])
                        if usage.get("duration_ms"):
                            a["notify_duration_ms"] = int(usage["duration_ms"])
                        a["n_notifications"] += 1
                        a["finished_at"] = ts
                    continue
                if rec.get("isMeta"):
                    continue
                m = re.search(r"<command-name>/?([^<\s]+)</command-name>", txt)
                if m:
                    args = re.search(r"<command-args>(.*?)</command-args>", txt, re.S)
                    S["slash_cmds"].append({
                        "ts": ts, "cmd": m.group(1),
                        "args": redact((args.group(1) if args else "").strip())[:80],
                    })
                    if "skill" in m.group(1).lower() or ":" in m.group(1):
                        S["skills"].append((ts, "/" + m.group(1)))
                    continue
                if txt.startswith("[Request interrupted by user]"):
                    S["interrupts"].append({"ts": ts, "kind": "interruzione"})
                    continue
                if any(txt.startswith(p) for p in NON_OWNER_PREFIXES):
                    continue
                S["owner_n"] += 1
                if ts and (ts >= da):
                    S["owner_msgs"].append({"ts": ts,
                                           "text": redact(txt)[:OWNER_SNIPPET]})

        if typ == "assistant":
            msg = rec.get("message") or {}
            mdl = msg.get("model")
            u = msg.get("usage") or {}
            if ts and ts >= da and u:
                S["tok_main"][mdl or "?"] += (int(u.get("input_tokens") or 0)
                                             + int(u.get("output_tokens") or 0))
            if mdl and mdl != "<synthetic>":
                S["models_main"][mdl] += 1
            if rec.get("error") or rec.get("apiErrorStatus"):
                S["api_errors"].append({
                    "ts": ts, "kind": str(rec.get("error") or "api"),
                    "status": rec.get("apiErrorStatus"),
                })
            if rec.get("quotaLimits"):
                q = rec["quotaLimits"]
                S["quota_events"].append({
                    "ts": ts, "status": q.get("status"),
                    "type": q.get("rateLimitType"), "resets_at": q.get("resetsAt"),
                    "overage": q.get("overageStatus"),
                })
            cont = msg.get("content")
            if isinstance(cont, list):
                for blk in cont:
                    if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                        continue
                    name = blk.get("name") or "?"
                    inp = blk.get("input") or {}
                    S["tools"][name] += 1
                    name_by_tooluse[blk.get("id")] = name
                    if name in ("Agent", "Task"):
                        a = agent("tu:" + str(blk.get("id")))
                        a["tool_use_id"] = blk.get("id")
                        a["description"] = redact(str(inp.get("description") or ""))[:160]
                        a["subagent_type"] = inp.get("subagent_type") or inp.get("agent_type")
                        a["model_requested"] = inp.get("model")
                        a["isolation"] = inp.get("isolation")
                        a["launched_at"] = ts
                    elif name == "Skill":
                        S["skills"].append((ts, redact(str(inp.get("skill") or ""))[:80]))
                    elif name == "SendMessage":
                        to = str(inp.get("to") or "")
                        S["resumes"].append({
                            "ts": ts, "to": to,
                            "summary": redact(str(inp.get("summary") or ""))[:120],
                        })
                        if to in S["agents"]:
                            S["agents"][to]["resumes"] += 1
                    elif name == "AskUserQuestion":
                        qs = []
                        for q in inp.get("questions") or []:
                            qs.append({
                                "question": redact(str(q.get("question") or ""))[:200],
                                "options": [redact(str(o.get("label") or ""))[:80]
                                            for o in (q.get("options") or [])],
                            })
                        S["questions"].append({"ts": ts, "questions": qs,
                                               "tool_use_id": blk.get("id"), "answer": None})
                    elif name == "Bash":
                        cmd = str(inp.get("command") or "")
                        one = cmd.replace("\n", " ")
                        # la sola PARTE DI COMANDO (prima di un eventuale heredoc) decide
                        # se e' un commit o un merge: il messaggio di un commit puo'
                        # contenere la parola "git merge" e dare un falso positivo
                        head = one.split("<<")[0]
                        if re.search(r"\bgit\s+commit\b", head):
                            m = re.search(r"-m\s+[\"'](.{2,140}?)[\"']", one)
                            if not m:
                                m = re.search(r"<<-?\s*['\"]?[A-Z_]+['\"]?\s*\n\s*(.{2,140})", cmd)
                            S["git_commits"].append({"ts": ts, "sha": None,
                                                    "msg": redact(m.group(1) if m else one)[:120]})
                        if re.search(r"\bgit\s+merge\b", head):
                            S["git_merges"].append({"ts": ts, "cmd": redact(one)[:95]})
                        # riduzioni utili a vedere attese/polling e comandi ripetuti
                        S["bash_cmds"][redact(one.split("&&")[0])[:80]] += 1
                        for mm in re.finditer(r"\bsleep\s+(\d+(?:\.\d+)?)", one):
                            S["n_sleep"] += 1
                            S["sleep_s"] += float(mm.group(1))
                        if "orca-ide orchestration" in one:
                            m = re.search(r"--type\s+([a-z_]+)", one)
                            m2 = re.search(r"--verb\s+([a-z_]+)", one)
                            S["orca_cmds"].append({
                                "ts": ts,
                                "kind": (m.group(1) if m else (m2.group(1) if m2 else "?")),
                                "cmd": redact(one)[:140],
                            })
            continue

    # ---- risposte alle domande al proprietario (gia' raccolte nel passaggio principale)
    for q in S["questions"]:
        q["answer"] = answers.get(q["tool_use_id"])

    # ---- agenti: unisce tool_use, meta.json e trascrizioni trovate su disco
    by_tooluse = {a["tool_use_id"]: a for a in S["agents"].values() if a["tool_use_id"]}
    for aid, info in S["subagents_meta"].items():
        meta = info["meta"]
        tu = meta.get("toolUseId")
        a = by_tooluse.get(tu)
        if a is None:
            a = agent(aid)
            a["description"] = redact(str(meta.get("description") or ""))[:160] or a["description"]
        a["meta_agent_id"] = aid
        a["subagent_type"] = a["subagent_type"] or meta.get("agentType")
        a["meta_name"] = meta.get("name")
        a["meta_model"] = meta.get("model")
        a["isolation"] = a["isolation"] or ("worktree" if meta.get("spawnedWithWorktree") else None)
        a["jsonl"] = info["jsonl"]
        if a["tool_use_id"] and a["tool_use_id"] in by_tooluse and by_tooluse[a["tool_use_id"]] is a:
            pass

    # ---- trascrizioni dei subagenti (modello, token, strumenti, rapporti)
    agent_jsonls = set()
    for a in S["agents"].values():
        p = a.get("jsonl")
        if p:
            agent_jsonls.add(p)
    for p in sorted(glob.glob(os.path.join(sdir, "**", "agent-*.jsonl"), recursive=True)):
        agent_jsonls.add(p)
    sub_by_file = {}
    for p in agent_jsonls:
        if not os.path.exists(p):
            continue
        sub = scan_subagent(p, t)
        sub_by_file[p] = sub
        aid = re.sub(r"^agent-|\.jsonl$", "", os.path.basename(p))
        a = None
        for cand_id, cand in S["agents"].items():
            if cand.get("meta_agent_id") == aid:
                a = cand
                break
        if a is None:
            a = agent(aid)
            meta = S["subagents_meta"].get(aid, {}).get("meta") or {}
            a["description"] = redact(str(meta.get("description") or ""))[:160]
            a["subagent_type"] = meta.get("agentType")
            a["meta_name"] = meta.get("name")
            a["model_requested"] = meta.get("model")
            a["meta_agent_id"] = aid
        a["transcript"] = sub
    S["sub_tally"] = t

    # ---- durata attiva: unione dei timestamp delle due trascrizioni, con buchi > soglia
    all_ts = sorted(set([x for x in ts_events if x]))
    active = 0.0
    for prev, cur in zip(all_ts, all_ts[1:]):
        gap = (cur - prev).total_seconds()
        if 0 <= gap <= PAUSE_Soglie:
            active += gap
    S["active_s"] = active
    S["first"] = all_ts[0] if all_ts else None
    S["last"] = all_ts[-1] if all_ts else None
    S["n_lines"] = t.lines
    S["n_bad"] = t.bad
    return S


# ------------------------------------------------------------------ sessioni pi
#
# Formato (verificato il 19/09/2026 su ~/.pi/agent/sessions): una riga per record,
#   {"type":"session",  id, timestamp ISO, cwd}                    ← worktree della run
#   {"type":"model_change", provider, modelId}
#   {"type":"thinking_level_change", …}                            ← ignorato
#   {"type":"compaction", timestamp, summary}                      ← contata, summary mai copiato
#   {"type":"message", timestamp, message:{role:user|assistant|toolResult, …}}
# assistant: usage{input,output,cacheRead,cacheWrite,reasoning,totalTokens,cost{total}} per
# ogni messaggio; blocchi content di tipo toolCall{name, arguments(stringa)}; stopReason.
# toolResult: toolName, isError — il contenuto NON viene mai letto oltre il flag.

DEFAULT_PI = os.path.expanduser("~/.pi/agent/sessions")


def scan_pi_session(path, da, fine, tz):
    sid = re.sub(r".*_", "", os.path.splitext(os.path.basename(path))[0])
    S = {
        "id": sid, "path": path, "dir": os.path.basename(os.path.dirname(path)),
        "pid": None, "cwd": None,
        "first": None, "last": None, "active_s": 0.0,
        "providers": Counter(), "models": Counter(),
        "turns": 0, "user_msgs": 0, "tool_calls": 0, "tools": Counter(),
        "in": 0, "out": 0, "cache_read": 0, "cache_write": 0, "reasoning": 0,
        "total_tokens": 0, "cost_sum": 0.0,
        "tool_errors": Counter(), "errors_total": 0,
        "git_commits": [], "branches": Counter(),
        "sleep_s": 0.0, "n_sleep": 0, "orca_types": Counter(),
        "compactions": [], "aborts": 0, "api_errors": 0,
        "in_range_n": 0, "bash_cmds": Counter(),
    }
    ts_events = []
    t = Tally()
    for line in iter_lines(path):
        t.add()
        if not line.startswith("{"):
            t.bad += 1
            continue
        try:
            rec = json.loads(line)
        except Exception:
            t.bad += 1
            continue
        ts = parse_ts(rec.get("timestamp"))
        typ = rec.get("type")
        if ts is not None:
            if da <= ts < fine:
                ts_events.append(ts)
                S["in_range_n"] += 1
        if typ == "session":
            S["pid"] = rec.get("id")
            S["cwd"] = rec.get("cwd")
            continue
        if typ == "compaction":
            if ts and da <= ts < fine:
                S["compactions"].append({"ts": ts})
            continue
        if typ != "model_change" and typ != "message":
            continue
        if typ == "model_change":
            S["providers"][rec.get("provider") or "?"] += 1
            S["models"][rec.get("modelId") or "?"] += 1
            continue
        msg = rec.get("message") or {}
        role = msg.get("role")
        if role == "user":
            S["user_msgs"] += 1
            continue
        if role == "toolResult":
            if msg.get("isError") and ts and da <= ts < fine:
                S["tool_errors"][msg.get("toolName") or "?"] += 1
                S["errors_total"] += 1
            continue
        if role != "assistant":
            continue
        S["providers"][msg.get("provider") or "?"] += 1
        S["models"][msg.get("model") or "?"] += 1
        if not (ts and da <= ts < fine):
            continue
        S["turns"] += 1
        u = msg.get("usage") or {}
        S["in"] += int(u.get("input") or 0)
        S["out"] += int(u.get("output") or 0)
        S["cache_read"] += int(u.get("cacheRead") or 0)
        S["cache_write"] += int(u.get("cacheWrite") or 0)
        S["reasoning"] += int(u.get("reasoning") or 0)
        S["total_tokens"] += int(u.get("totalTokens") or 0)
        S["cost_sum"] += float(((u.get("cost") or {}).get("total")) or 0)
        sr = msg.get("stopReason")
        if sr == "aborted":
            S["aborts"] += 1
        elif sr == "error":
            S["api_errors"] += 1
        cont = msg.get("content")
        if isinstance(cont, list):
            for blk in cont:
                if not isinstance(blk, dict) or blk.get("type") != "toolCall":
                    continue
                name = blk.get("name") or "?"
                S["tool_calls"] += 1
                S["tools"][name] += 1
                argstr = blk.get("arguments")
                if not isinstance(argstr, str):
                    argstr = json.dumps(argstr or {}, ensure_ascii=False)
                one = argstr.replace("\\n", " ")
                if re.search(r"\bgit commit\b", one.split("<<")[0]):
                    m = re.search(r"-m\s+\\?['\"](.{2,140}?)\\?['\"]", one)
                    if not m:
                        m = re.search(r"<<-?\s*['\"]?[A-Z_]+['\"]?\s*\n\s*(.{2,140})", argstr)
                    S["git_commits"].append({
                        "ts": ts, "msg": redact(m.group(1) if m else one)[:120]})
                for mb in re.finditer(r"\bXrayFinanceDEV/([\w.-]+(?:/[\w.-]+)*)", one):
                    tok = mb.group(0)
                    ctx = one[max(0, mb.start() - 12):mb.start()]
                    # il remote si chiama XrayFinanceDEV: `--repo XrayFinanceDEV/xbrlbudget`
                    # e gli URL `.../issues/N` non sono branch
                    if tok == "XrayFinanceDEV/xbrlbudget" or "repo" in ctx or "/issues" in tok:
                        continue
                    S["branches"][tok] += 1
                if "orca-ide orchestration" in one:
                    mt = re.search(r"--type\s+([a-z_]+)", one)
                    S["orca_types"][mt.group(1) if mt else "?"] += 1
                for ms in re.finditer(r"\bsleep\s+(\d+(?:\.\d+)?)", one):
                    S["n_sleep"] += 1
                    S["sleep_s"] += float(ms.group(1))
                if name == "bash":
                    S["bash_cmds"][redact(one.split("&&")[0])[:80]] += 1
    S["n_lines"], S["n_bad"] = t.lines, t.bad
    all_ts = sorted(set(x for x in ts_events if x))
    active = 0.0
    for prev, cur in zip(all_ts, all_ts[1:]):
        gap = (cur - prev).total_seconds()
        if 0 <= gap <= PAUSE_Soglie:
            active += gap
    S["active_s"] = active
    S["first"] = all_ts[0] if all_ts else None
    S["last"] = all_ts[-1] if all_ts else None
    S["worktree"] = (S["cwd"] or S["dir"] or "?").split("/")[-1]
    return S


def render_pi_card(S, tz):
    A = (lambda *a: [out.append(x) for x in a])
    out = []
    A(f"# Scheda pi `{S['id'][:13]}`")
    A("")
    A(f"- **File**: `{os.path.relpath(S['path'], DEFAULT_PI)}` — {S['n_lines']} righe lette, "
      f"{S['n_bad']} scartate")
    A(f"- **Worktree**: `{S['cwd']}` (dir `{S['dir']}`)")
    A(f"- **Inizio / fine (ora locale)**: {fmt(S['first'], tz)} → {fmt(S['last'], tz)}")
    span = ((S['last'] - S['first']).total_seconds() if S['first'] and S['last'] else None)
    A(f"- **Estensione**: {fmt_dur(span)} — **tempo attivo** (senza pause > 30 min): "
      f"{fmt_dur(S['active_s'])}")
    A(f"- **Provider/modello**: " + ", ".join(f"{k} ({n})" for k, n in S['models'].most_common(3)))
    A(f"- **Turni assistant**: {S['turns']} · **chiamate strumento**: {S['tool_calls']} "
      f"· **fallite**: {S['errors_total']}")
    A(f"- **Token**: input {human(S['in'])} · output {human(S['out'])} · "
      f"cache-lettura {human(S['cache_read'])} · cache-scrittura {human(S['cache_write'])} · "
      f"totali {human(S['total_tokens'])} · costo dichiarato USD {S['cost_sum']:.4f}")
    A(f"- **Compattazioni**: {len(S['compactions'])} · **aborti**: {S['aborts']} · "
      f"**errori API**: {S['api_errors']}")
    if S["branches"]:
        A(f"- **Branch citati nei comandi**: "
          + ", ".join(f"`{b}` ({n})" for b, n in S["branches"].most_common(4)))
    A("")
    A("## Strumenti")
    A("")
    A("| strumento | chiamate | fallite |")
    A("|---|---|---|")
    for k, n in S["tools"].most_common():
        A(f"| `{k}` | {n} | {S['tool_errors'].get(k, 0)} |")
    A("")
    A(f"## git commit eseguiti — {len(S['git_commits'])}")
    A("")
    for c in S["git_commits"][:40]:
        A(f"- `{fmt(c['ts'], tz)}` — {c['msg']}")
    if len(S["git_commits"]) > 40:
        A(f"- … altri {len(S['git_commits']) - 40}")
    A("")
    if S["orca_types"]:
        A("## Orchestrazione (messaggi `--type`)")
        A("")
        A(" · ".join(f"`{k}`×{v}" for k, v in S["orca_types"].most_common(8)))
        A("")
    top = {k: v for k, v in S["bash_cmds"].most_common(10) if v > 1}
    if top or S["n_sleep"]:
        A("## Bash ripetuti e attese")
        A("")
        for k, v in top.items():
            A(f"- ×{v} — `{k}`")
        A(f"- sleep: {S['n_sleep']} chiamate, {fmt_dur(S['sleep_s'])} cumulati")
        A("")
    return "\n".join(out)


# ------------------------------------------------------------------ schede

def render_card(S, tz, da, agent_cap=10 ** 9, owner_cap=10 ** 9, resume_cap=10 ** 9):
    out = []
    A = out.append
    A(f"# Scheda sessione `{S['id'][:8]}`")
    A("")
    A(f"- **File**: `{os.path.basename(S['path'])}` — {S['n_lines']} righe lette, "
      f"{S['n_bad']} scartate")
    A(f"- **Inizio / fine (ora locale)**: {fmt(S['first'], tz)} → {fmt(S['last'], tz)}")
    span = ((S['last'] - S['first']).total_seconds() if S['first'] and S['last'] else None)
    A(f"- **Estensione**: {fmt_dur(span)} — **tempo attivo** (senza pause > 30 min): "
      f"{fmt_dur(S['active_s'])}")
    A(f"- **Cwd**: `{S['cwd']}` · **branch**: "
      + ", ".join(f"{b} ({n})" for b, n in S["branches"].most_common(4)))
    A(f"- **Versione CLI**: " + ", ".join(f"{v} ({n})" for v, n in S["version"].most_common(3)))
    if S["cost_state"]:
        cs = S["cost_state"]
        A(f"- **cost-state**: USD {cs.get('totalCostUSD'):.4f} · durata API "
          f"{fmt_dur((cs.get('totalAPIDuration') or 0)/1000)} · durata totale "
          f"{fmt_dur((cs.get('totalDuration') or 0)/1000)} (snapshot finale, include i subagenti)")
    A("")

    A(f"## Messaggi del proprietario — {S['owner_n']} in sessione")
    in_range = [m for m in S["owner_msgs"] if m["ts"] >= da]
    A(f"nel periodo richiesto: {len(in_range)}")
    A("")
    per = 300
    budget = 6200
    if len(in_range) * (per + 40) > budget:
        per = 200
    if len(in_range) * (per + 40) > budget:
        per = 120
    n_show = min(len(in_range), owner_cap, max(1, budget // (per + 40)))
    for m in in_range[:n_show]:
        A(f"- `{fmt(m['ts'], tz)}` — {m['text'][:per]}")
    if n_show < len(in_range):
        A(f"- … altri {len(in_range)-n_show} messaggi (troncati qui: elenco completo in "
          "`aggregato.json` → `per_sessione[*].messaggi_proprietario_elenco`)")
    A("")

    A("## Skill / comandi slash invocati")
    if S["skills"]:
        for ts, name in S["skills"]:
            A(f"- `{fmt(ts, tz)}` skill `{redact(name)}`")
    else:
        A("- (nessuna chiamata diretta dello strumento Skill)")
    slash = Counter(c["cmd"] for c in S["slash_cmds"])
    if slash:
        A("- slash command: " + ", ".join(f"`/{k}`×{v}" for k, v in slash.most_common(12)))
    A("")

    ags = [S["agents"][k] for k in S["agent_order"]]
    ags = [a for a in ags if (a.get("launched_at") or a.get("finished_at") or a.get("transcript"))]
    A(f"## Agenti lanciati — {len(ags)}")
    A("")
    A("| lanciato | fine | tipo | modello | token | strumenti | durata | stato | riprese | descrizione |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for a in ags[:agent_cap]:
        tr = a.get("transcript") or {}
        model = tr.get("model") or a.get("model_requested") or a.get("meta_model") or "?"
        tok = a.get("notify_tokens")
        if tok is None and tr:
            tok = tr.get("out", 0) + tr.get("cache_read", 0) + tr.get("cache_creation", 0) + tr.get("in", 0)
        dur = a.get("notify_duration_ms")
        dur_s = fmt_dur(dur / 1000) if dur else (
            fmt_dur((tr["last"] - tr["first"]).total_seconds()) if tr.get("first") and tr.get("last") else "—")
        tools = a.get("notify_tool_uses") or tr.get("tool_calls") or 0
        A("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            fmt(a.get("launched_at") or (tr.get('first') if tr else None), tz),
            fmt(a.get("finished_at"), tz),
            a.get("subagent_type") or a.get("meta_name") or "?",
            model, human(tok), tools, dur_s,
            a.get("status") or "—", a.get("resumes"),
            (a.get("description") or "")[:44]))
    if len(ags) > agent_cap:
        A(f"| … | … | … | … | … | … | … | … | … | altri {len(ags)-agent_cap} agenti: elenco "
          "completo in `aggregato.json` → `agenti` |")
    reports = sorted({os.path.basename(p)
                      for a in ags for p in ((a.get("transcript") or {}).get("reports") or [])})
    if reports:
        A("")
        A("rapporti scritti: " + ", ".join(f"`{r}`" for r in reports[:20]))
    if S["resumes"]:
        A("")
        A(f"### Agenti ripresi con un messaggio — {len(S['resumes'])}")
        for r in S["resumes"][:min(40, resume_cap)]:
            A(f"- `{fmt(r['ts'], tz)}` → `{str(r['to'])[:12]}` — {r['summary']}")
        if len(S["resumes"]) > min(40, resume_cap):
            A(f"- … altri {len(S['resumes'])-min(40, resume_cap)} ripresi")
    A("")

    if S["questions"]:
        A(f"## Domande al proprietario — {len(S['questions'])}")
        for q in S["questions"][:12]:
            A(f"- `{fmt(q['ts'], tz)}` " + " | ".join(
                f"{x['question'][:90]}" for x in q["questions"][:2]))
            if q.get("answer"):
                A(f"    → {q['answer'][:90]}")
        if len(S["questions"]) > 12:
            A(f"- … altre {len(S['questions'])-12} domande, con opzioni e risposte integrali: "
              "`aggregato.json` → `per_sessione[*].domande_elenco`")
        A("")

    A(f"## Compattazioni — {len(S['compactions'])}")
    for c in S["compactions"]:
        A(f"- `{fmt(c['ts'], tz)}` trigger={c['trigger']} pre={human(c['pre_tokens'])} "
          f"post={human(c['post_tokens'])} scartati_cum={human(c['dropped_cum'])} "
          f"durata={fmt_dur((c['duration_ms'] or 0)/1000)}")
    A("")

    A(f"## Errori API e limiti di sessione — {len(S['api_errors'])} errori, "
      f"{len(S['quota_events'])} rifiuti di quota")
    for e in S["api_errors"][:20]:
        A(f"- `{fmt(e['ts'], tz)}` {e['kind']} http={e['status']}")
    kinds = Counter(f"{q['type']}/{q['status']}" for q in S["quota_events"])
    if kinds:
        A("- quota: " + ", ".join(f"{k}×{v}" for k, v in kinds.most_common()))
    A("")

    A(f"## Interruzioni — {len(S['interrupts'])}")
    for i in S["interrupts"][:20]:
        A(f"- `{fmt(i['ts'], tz)}` {i['kind']}")
    A("")

    A(f"## Commit git eseguiti — {len(S['git_commits'])}")
    for c in S["git_commits"][:max(8, min(60, agent_cap * 2))]:
        A(f"- `{fmt(c['ts'], tz)}` {c['msg']}")
    if len(S["git_commits"]) > max(8, min(60, agent_cap * 2)):
        A(f"- … altri {len(S['git_commits']) - max(8, min(60, agent_cap * 2))} commit"
          " (elenco in aggregato.json)")
    A("")
    A(f"## Merge git — {len(S['git_merges'])}")
    for m in S["git_merges"][:30]:
        A(f"- `{fmt(m['ts'], tz)}` {m['cmd']}")
    A("")
    A(f"## Comandi orca-ide orchestration — {len(S['orca_cmds'])}")
    kinds = Counter(c["kind"] for c in S["orca_cmds"])
    A("- " + (", ".join(f"{k}×{v}" for k, v in kinds.most_common()) or "nessuno"))
    for c in [x for x in S["orca_cmds"] if x["kind"] in ("worker_done", "escalation", "ask")][:20]:
        A(f"- `{fmt(c['ts'], tz)}` {c['kind']}: {c['cmd'][:120]}")
    A("")

    A(f"## Attese e ripetizioni (Bash)")
    A(f"- `sleep`: {S['n_sleep']} chiamate, {fmt_dur(S['sleep_s'])} di attese dichiarate")
    rep = [(c, n) for c, n in S["bash_cmds"].most_common(20) if n > 2]
    if rep:
        A("- comandi ripetuti piu' di 2 volte: " + "; ".join(
            f"`{c}`×{n}" for c, n in rep[:10]))
    A("")

    A("## Strumenti chiamati (main loop)")
    A("- " + ", ".join(f"{k}×{v}" for k, v in S["tools"].most_common(30)))
    A(f"- **comandi falliti** (tool_result is_error): {S['errors_total']} — "
      + (", ".join(f"{k}×{v}" for k, v in S["tool_errors"].most_common(10)) or "nessuno"))
    A("")
    A("## Token del main loop per modello (somma usage dei messaggi in periodo)")
    for mdl, n in S["models_main"].most_common(6):
        A(f"- `{mdl}`: {n} risposte")
    A("")
    return "\n".join(out)


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Estrae metadati (mai contenuti) dalle trascrizioni di Claude Code.")
    ap.add_argument("--da", required=True, help="data di inizio periodo (YYYY-MM-DD)")
    ap.add_argument("--a", default=None, help="data di fine periodo (esclusiva), default: ora")
    ap.add_argument("--out", default=".superpowers/retrospettiva")
    ap.add_argument("--projects", default=DEFAULT_PROJECTS)
    ap.add_argument("--pi", default=DEFAULT_PI,
                    help="cartella ~/.pi/agent/sessions (o equivalente); le sottocartelle "
                         "con 'budget' nel nome sono del progetto")
    ap.add_argument("--no-pi", action="store_true", help="non leggere le sessioni pi")
    ap.add_argument("--tz", default=os.environ.get("TZ") or "Europe/Rome")
    ap.add_argument("--db", default=os.environ.get("DATABASE_PATH")
                    or "/home/peter/DEV/budget/financial_analysis.db",
                    help="SQLite di progetto, letto SOLO in sola lettura per la lista "
                         "delle aziende da mascherare (se assente, si usa COMPANY_NAMES)")
    args = ap.parse_args(argv)

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(args.tz)
    except Exception:
        tz = _dt.timezone.utc

    da = _dt.datetime.fromtimestamp(
        _dt.datetime.strptime(args.da, "%Y-%m-%d").timestamp(), _dt.timezone.utc)

    if args.db and os.path.exists(args.db):
        try:
            import sqlite3
            con = sqlite3.connect(f"file:{args.db}?mode=ro&immutable=1", uri=True)
            names = [r[0] for r in con.execute("select distinct name from companies")]
            con.close()
            add_company_names(names)
            print(f"nomi azienda caricati dal DB (sola lettura): {len(names)}")
        except Exception:            # il DB non c'entra con l'analisi: serve solo da maschera
            print("DB aziende non letto: uso l'elenco nel sorgente")
    a_fine = (_dt.datetime.fromtimestamp(
        _dt.datetime.strptime(args.a, "%Y-%m-%d").timestamp(), _dt.timezone.utc)
        if args.a else _dt.datetime.now(_dt.timezone.utc))

    main_files = sorted(glob.glob(os.path.join(args.projects, "*.jsonl")))
    cards_dir = os.path.join(args.out, "schede")
    os.makedirs(cards_dir, exist_ok=True)

    sessions, tot_lines, tot_bad, tot_sub, skipped = [], 0, 0, 0, 0
    for p in main_files:
        # screening economico sul mtime, poi la verifica vera e' sui timestamp dei record
        if _dt.datetime.fromtimestamp(os.path.getmtime(p), _dt.timezone.utc) < da:
            skipped += 1
            continue
        S = scan_session(p, da, a_fine, tz)
        if not S["in_range_n"]:
            skipped += 1
            continue
        S["n_sub"] = sum(1 for a in S["agents"].values() if a.get("transcript"))
        tot_lines += S["n_lines"]
        tot_bad += S["n_bad"]
        tot_sub += S["n_sub"]
        card = None
        ladder = ((10 ** 9, 10 ** 9, 10 ** 9), (60, 45, 20), (45, 35, 15), (35, 28, 12),
                  (28, 22, 10), (22, 16, 8), (16, 12, 6), (12, 10, 6), (8, 8, 4))
        for caps in ladder:
            card = render_card(S, tz, da, *caps)
            if len(card.encode("utf-8")) <= CARD_BUDGET_BYTES:
                break
        raw = card.encode("utf-8")
        if len(raw) > CARD_BUDGET_BYTES:      # rete di sicurezza: mai oltre ~15 KB
            card = raw[:CARD_BUDGET_BYTES].decode("utf-8", "ignore") + \
                "\n… [scheda troncata al tetto di ~15 KB; tutto in aggregato.json]\n"
        with open(os.path.join(cards_dir, f"{S['id']}.md"), "w", encoding="utf-8") as fh:
            fh.write(card)
        sessions.append(S)

    # ---------------------------------------------------- sessioni pi (novità del periodo)
    pi_sessions, pi_lines, pi_bad, pi_skipped = [], 0, 0, 0
    if not args.no_pi and os.path.isdir(args.pi):
        for d in sorted(glob.glob(os.path.join(args.pi, "*"))):
            if not os.path.isdir(d) or "budget" not in os.path.basename(d):
                continue
            for p in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
                if _dt.datetime.fromtimestamp(os.path.getmtime(p), _dt.timezone.utc) < da:
                    pi_skipped += 1
                    continue
                P = scan_pi_session(p, da, a_fine, tz)
                if not P["in_range_n"]:
                    pi_skipped += 1
                    continue
                pi_lines += P["n_lines"]
                pi_bad += P["n_bad"]
                with open(os.path.join(cards_dir, f"pi-{P['id']}.md"),
                          "w", encoding="utf-8") as fh:
                    fh.write(render_pi_card(P, tz))
                pi_sessions.append(P)

    # ------------------------------------------------------------ aggregato
    rows = []
    per_model_main = defaultdict(Counter)   # usage dei messaggi del main loop
    per_model_tr = defaultdict(Counter)     # somme dalle trascrizioni dei subagenti
    per_work = defaultdict(Counter)
    per_model_cost = defaultdict(Counter)  # dal cost-state (include i subagenti)
    all_agents = []
    tot_cost_usd = 0.0
    for S in sessions:
        for mdl, n in S["tok_main"].items():
            per_model_main[model_family(mdl) or mdl]["main_in_out"] += n
        cs = S["cost_state"]
        if cs:
            tot_cost_usd += cs.get("totalCostUSD") or 0
            for mdl, u in (cs.get("modelUsage") or {}).items():
                pc = per_model_cost[model_family(mdl) or mdl]
                pc["costUSD"] += u.get("costUSD") or 0
                pc["input"] += u.get("inputTokens") or 0
                pc["output"] += u.get("outputTokens") or 0
                pc["thinking"] += u.get("thinkingTokens") or 0
                pc["cache_letto"] += u.get("cacheReadInputTokens") or 0
                pc["cache_creazione"] += u.get("cacheCreationInputTokens") or 0
                pc["voci_cost_state"] += 1
        for aid in S["agent_order"]:
            a = S["agents"][aid]
            tr = a.get("transcript") or {}
            if not (a.get("launched_at") or tr.get("first")):
                continue
            if not ((a.get("launched_at") or tr.get("first")) >= da):
                continue
            tipo, matched = classify(a.get("description") or "", a.get("subagent_type") or "",
                                     a.get("meta_name") or "")
            tok = a.get("notify_tokens")
            src = "notifica"
            if tok is None:
                tok = (tr.get("out", 0) + tr.get("in", 0) + tr.get("cache_read", 0)
                       + tr.get("cache_creation", 0))
                src = "somma usage trascrizione"
            dur_s = (a.get("notify_duration_ms") or 0) / 1000 or (
                (tr["last"] - tr["first"]).total_seconds()
                if tr.get("first") and tr.get("last") else 0)
            model = tr.get("model") or a.get("model_requested") or a.get("meta_model") or "?"
            fam = (model_family(model) or model_family(a.get("meta_model"))
                   or model_family(a.get("model_requested")) or "sconosciuto")
            all_agents.append({
                "sessione": S["id"], "esecutore": f"subagente Claude ({fam})",
                "agente": a.get("meta_agent_id") or aid,
                "descrizione": a.get("description"), "tipo_agente": a.get("subagent_type"),
                "nome": a.get("meta_name"), "model": model, "famiglia_modello": fam,
                "model_richiesto": a.get("model_requested"), "isolation": a.get("isolation"),
                "tipo_lavoro": tipo, "regex_matchata": matched,
                "token": tok, "token_fonte": src,
                "out_trascrizione": tr.get("out", 0), "in_trascrizione": tr.get("in", 0),
                "cache_letto_trascrizione": tr.get("cache_read", 0),
                "cache_creazione_trascrizione": tr.get("cache_creation", 0),
                "strumenti": a.get("notify_tool_uses") or tr.get("tool_calls") or 0,
                "durata_s": round(dur_s), "stato": a.get("status"),
                "riprese": a.get("resumes"), "notifiche": a.get("n_notifications"),
                "lanciato": fmt(a.get("launched_at") or tr.get("first"), tz),
                "finito": fmt(a.get("finished_at") or tr.get("last"), tz),
                "errori_api": tr.get("api_errors", 0),
                "rapporti": [os.path.basename(x) for x in (tr.get("reports") or [])],
                "file_scritti": sorted({os.path.basename(x) for x in (tr.get("files_written") or [])}),
            })
            for bucket in (per_model_tr[fam], per_work[tipo]):
                bucket["n"] += 1
                bucket["token_notifica"] += tok or 0
                bucket["con_notifica"] += 1 if a.get("notify_tokens") else 0
                bucket["out"] += tr.get("out", 0)
                bucket["in"] += tr.get("in", 0)
                bucket["cache_letto"] += tr.get("cache_read", 0)
                bucket["cache_creazione"] += tr.get("cache_creation", 0)
                bucket["durata_s"] += round(dur_s)
                bucket["strumenti"] += (a.get("notify_tool_uses") or tr.get("tool_calls") or 0)
                bucket["riprese"] += a.get("resumes") or 0
                bucket["errori_api"] += tr.get("api_errors", 0)
        rows.append({
            "sessione": S["id"], "esecutore": "Claude principale",
            "inizio": fmt(S["first"], tz), "fine": fmt(S["last"], tz),
            "estensione_s": int((S["last"] - S["first"]).total_seconds()) if S["first"] and S["last"] else 0,
            "attivo_s": int(S["active_s"]), "righe_lette": S["n_lines"],
            "righe_scartate": S["n_bad"], "messaggi_proprietario": S["owner_n"],
            "messaggi_proprietario_elenco": [
                {"ts": fmt(m["ts"], tz), "testo": m["text"]} for m in S["owner_msgs"]],
            "agenti": len([a for a in S["agents"].values()
                           if a.get("launched_at") or a.get("transcript")]),
            "subagenti_con_trascrizione": S["n_sub"],
            "riprese": len(S["resumes"]), "domande": len(S["questions"]),
            "domande_elenco": [
                {"ts": fmt(q["ts"], tz),
                 "domande": [x["question"] for x in q["questions"]],
                 "opzioni": [x["options"] for x in q["questions"]],
                 "risposta": q.get("answer")} for q in S["questions"]],
            "compattazioni": len(S["compactions"]),
            "interruzioni": len(S["interrupts"]), "errori_api": len(S["api_errors"]),
            "rifiuti_quota": len(S["quota_events"]),
            "commit": len(S["git_commits"]), "merge": len(S["git_merges"]),
            "slash": dict(Counter(c["cmd"] for c in S["slash_cmds"])),
            "sleep_s": S["sleep_s"], "n_sleep": S["n_sleep"],
            "bash_top_ripetuti": {c: n for c, n in S["bash_cmds"].most_common(8)},
            "strumenti": dict(S["tools"]), "comandi_falliti": S["errors_total"],
            "costo_usd_cost_state": round((S["cost_state"] or {}).get("totalCostUSD", 0), 4)
            if S["cost_state"] else None,
            "branch": dict(S["branches"]),
        })

    # ------------------------------------------------------------ esecutori e righe pi
    per_exec = defaultdict(Counter)
    for S in sessions:
        b = per_exec["Claude principale"]
        b["sessioni"] += 1
        b["durata_attiva_s"] += int(S["active_s"])
        b["strumenti"] += sum(S["tools"].values())
        b["comandi_falliti"] += S["errors_total"]
        b["commit"] += len(S["git_commits"])
        b["merge"] += len(S["git_merges"])
        b["messaggi_proprietario"] += S["owner_n"]
        b["compattazioni"] += len(S["compactions"])
        b["riprese"] += len(S["resumes"])
        for mdl, n in S["tok_main"].items():
            b["token_in_out"] += n
    for a in all_agents:
        b = per_exec[a["esecutore"]]
        b["agenti"] += 1
        b["token_notifica"] += a["token"] or 0
        b["out"] += a.get("out_trascrizione") or 0
        b["in"] += a.get("in_trascrizione") or 0
        b["cache_letto"] += a.get("cache_letto_trascrizione") or 0
        b["cache_creazione"] += a.get("cache_creazione_trascrizione") or 0
        b["strumenti"] += a["strumenti"] or 0
        b["durata_attiva_s"] += a["durata_s"] or 0
        b["riprese"] += a["riprese"] or 0
        b["errori_api"] += a["errori_api"] or 0
    pi_rows = []
    for P in pi_sessions:
        b = per_exec["pi"]
        b["sessioni"] += 1
        b["turni"] += P["turns"]
        b["durata_attiva_s"] += int(P["active_s"])
        b["strumenti"] += P["tool_calls"]
        b["comandi_falliti"] += P["errors_total"]
        b["commit"] += len(P["git_commits"])
        b["compattazioni"] += len(P["compactions"])
        b["aborti"] += P["aborts"]
        b["token_in_out"] += P["in"] + P["out"]
        pi_rows.append({
            "sessione": P["id"], "esecutore": "pi", "worktree": P["worktree"],
            "cwd": P["cwd"],
            "inizio": fmt(P["first"], tz), "fine": fmt(P["last"], tz),
            "estensione_s": int((P["last"] - P["first"]).total_seconds())
            if P["first"] and P["last"] else 0,
            "attivo_s": int(P["active_s"]), "turni": P["turns"],
            "strumenti": dict(P["tools"]), "strumenti_tot": P["tool_calls"],
            "comandi_falliti": P["errors_total"],
            "token_in": P["in"], "token_out": P["out"],
            "token_cache_lettura": P["cache_read"], "token_cache_scrittura": P["cache_write"],
            "token_totali": P["total_tokens"], "costo_dichiarato_usd": round(P["cost_sum"], 4),
            "modelli": dict(P["models"]), "provider": dict(P["providers"]),
            "compattazioni": len(P["compactions"]), "aborti": P["aborts"],
            "errori_api": P["api_errors"],
            "commit": len(P["git_commits"]),
            "commit_elenco": [{"ts": fmt(c["ts"], tz), "msg": c["msg"]}
                              for c in P["git_commits"]],
            "branch": dict(P["branches"]),
            "sleep_s": P["sleep_s"], "n_sleep": P["n_sleep"],
            "bash_top_ripetuti": {c: n for c, n in P["bash_cmds"].most_common(8)},
            "orca": dict(P["orca_types"]),
            "righe_lette": P["n_lines"], "righe_scartate": P["n_bad"],
        })

    agg = {
        "generato_il": fmt(_dt.datetime.now(_dt.timezone.utc), tz),
        "periodo": {"da": fmt(da, tz), "a": fmt(a_fine, tz)},
        "projects_dir": args.projects,
        "totali": {
            "sessioni": len(sessions), "subagenti": tot_sub, "sessioni_pi": len(pi_sessions),
            "righe_lette": tot_lines + pi_lines, "righe_scartate": tot_bad + pi_bad,
            "righe_lette_claude": tot_lines, "righe_lette_pi": pi_lines,
            "agenti_classificati": len(all_agents),
        },
        "regola_classificazione": [{"tipo": k, "regex": v} for k, v in WORK_RULES]
        + [{"tipo": "workflow (fan-out)", "regex": "subagent_type == workflow-subagent"},
           {"tipo": "altro", "regex": "(nessuna corrispondenza)"}],
        "per_sessione": rows,
        "costo_usd_totale_cost_state": round(tot_cost_usd, 4),
        "per_modello_cost_state": {k: dict(v) for k, v in sorted(per_model_cost.items())},
        "per_modello_trascrizioni": {k: dict(v) for k, v in sorted(per_model_tr.items())},
        "per_modello_main_loop": {k: dict(v) for k, v in sorted(per_model_main.items())},
        "per_tipo_lavoro": {k: dict(v) for k, v in sorted(per_work.items())},
        "per_esecutore": {k: dict(v) for k, v in sorted(per_exec.items())},
        "sessioni_pi": pi_rows,
        "agenti": all_agents,
    }
    with open(os.path.join(args.out, "aggregato.json"), "w", encoding="utf-8") as fh:
        json.dump(agg, fh, ensure_ascii=False, indent=1, default=str)

    md = ["# Aggregato sessioni Claude Code e pi", "",
          f"Periodo: **{fmt(da, tz)} → {fmt(a_fine, tz)}** · progetto: `{args.projects}`"
          + (f" · pi: `{args.pi}`" if pi_sessions else ""),
          "",
          f"- sessioni principali Claude: **{len(sessions)}**",
          f"- subagenti Claude con trascrizione: **{tot_sub}**",
          f"- sessioni pi: **{len(pi_sessions)}** (cartelle con `budget` nel nome, "
          f"fuori periodo: {pi_skipped})",
          f"- righe JSONL lette: **{tot_lines + pi_lines}** · scartate: **{tot_bad + pi_bad}**",
          ""]
    md.append("## Una riga per sessione")
    md.append("")
    md.append("| sessione | inizio | attivo | estensione | msg prop. | agenti | riprese | domande | "
              "compatt. | interr. | err.api | quota | commit | merge | falliti | USD(cost-state) |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append("| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r["sessione"][:8], r["inizio"][:16], fmt_dur(r["attivo_s"]), fmt_dur(r["estensione_s"]),
            r["messaggi_proprietario"], r["agenti"], r["riprese"], r["domande"],
            r["compattazioni"], r["interruzioni"], r["errori_api"], r["rifiuti_quota"],
            r["commit"], r["merge"], r["comandi_falliti"],
            r["costo_usd_cost_state"] if r["costo_usd_cost_state"] is not None else "—"))
    md.append("")
    md.append("## Totale per modello — costo e token dal `cost-state` (include i subagenti)")
    md.append("")
    md.append("| modello | USD | input | output | thinking | cache letto | cache creazione |")
    md.append("|---|---|---|---|---|---|---|")
    for k, v in sorted(per_model_cost.items(), key=lambda x: -x[1].get("costUSD", 0)):
        md.append("| `{}` | {:.2f} | {} | {} | {} | {} | {} |".format(
            k, v.get("costUSD", 0), human(v.get("input", 0)), human(v.get("output", 0)),
            human(v.get("thinking", 0)), human(v.get("cache_letto", 0)),
            human(v.get("cache_creazione", 0))))
    md.append(f"| **totale** | **{tot_cost_usd:.2f}** | | | | | | |")
    md.append("")
    md.append("## Totale per modello — dalle trascrizioni dei subagenti (somma degli usage per messaggio)")
    md.append("")
    md.append("| modello | agenti | con notifica | token notifica | output | input | cache letto | cache creazione | strumenti | durata | riprese | errori API |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, v in sorted(per_model_tr.items(), key=lambda x: -x[1].get("n", 0)):
        md.append("| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            k, v.get("n"), v.get("con_notifica"), human(v.get("token_notifica")),
            human(v.get("out")), human(v.get("in")), human(v.get("cache_letto")),
            human(v.get("cache_creazione")), human(v.get("strumenti")),
            fmt_dur(v.get("durata_s")), v.get("riprese"), v.get("errori_api")))
    md.append("")
    md.append("`token notifica` = `<subagent_tokens>` dichiarato dalla notifica di fine agente;"
              " le colonne output/input/cache vengono dalla trascrizione del subagente."
              " Sono due misurazioni diverse e non vanno sommate.")
    md.append("")
    md.append("## Totale per tipo di lavoro (classificazione dalla descrizione dell'agente)")
    md.append("")
    md.append("| tipo | agenti | token notifica | output | cache letto | strumenti | durata | riprese | errori API |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for k in WORK_TYPES + [x for x in per_work if x not in WORK_TYPES]:
        if k in per_work:
            v = per_work[k]
            md.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                k, v.get("n"), human(v.get("token_notifica")), human(v.get("out")),
                human(v.get("cache_letto")), human(v.get("strumenti")),
                fmt_dur(v.get("durata_s")), v.get("riprese"), v.get("errori_api")))
    md.append("")
    md.append("Regola di classificazione (implementata in `scripts/analisi_sessioni.py`;"
              " vince la parola che compare prima nel testo):")
    for r in agg["regola_classificazione"]:
        md.append(f"- **{r['tipo']}** ← `{r['regex']}`")
    md.append("")
    md.append("## Per esecutore")
    md.append("")
    md.append("| esecutore | sessioni | agenti | turni | token notifica | token main in+out "
              "| output | input | cache letto | cache creazione | strumenti | durata attiva | "
              "riprese | commit | falliti | compatt. |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k in sorted(per_exec, key=lambda x: (x != "Claude principale", x != "pi", x)):
        v = per_exec[k]
        md.append("| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            k, v.get("sessioni", 0), v.get("agenti", 0), v.get("turni", 0),
            human(v.get("token_notifica", 0)), human(v.get("token_in_out", 0)),
            human(v.get("out", 0)), human(v.get("in", 0)),
            human(v.get("cache_letto", 0)), human(v.get("cache_creazione", 0)),
            human(v.get("strumenti", 0)), fmt_dur(v.get("durata_attiva_s")),
            v.get("riprese", 0), v.get("commit", 0), v.get("comandi_falliti", 0),
            v.get("compattazioni", 0)))
    md.append("")
    md.append("Nota: le colonne token di `Claude principale` sono input+output dal main loop; "
              "quelle di `subagente Claude` vengono dalle trascrizioni dei subagenti (mai "
              "sommare alle notifiche); `pi` riporta il costo dichiarato nei messaggi (USD 0 su "
              "provider locale gx10: qui il conto lo paga il tempo).")
    md.append("")
    md.append("## Sessioni pi — una riga per run")
    md.append("")
    md.append("| sessione | worktree | inizio | attivo | estensione | turni | strumenti | "
              "falliti | token in/out | cache letta | compatt. | commit | modelli |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(pi_rows, key=lambda x: x["inizio"]):
        md.append("| `{}` | `{}` | {} | {} | {} | {} | {} | {} | {} / {} | {} | {} | {} | {} |".format(
            r["sessione"][:13], r["worktree"][:28], r["inizio"][:16], fmt_dur(r["attivo_s"]),
            fmt_dur(r["estensione_s"]), r["turni"], human(r["strumenti_tot"]),
            r["comandi_falliti"], human(r["token_in"]), human(r["token_out"]),
            human(r["token_cache_lettura"]), r["compattazioni"], r["commit"],
            ",".join(sorted(r["modelli"]))))
    md.append("")
    with open(os.path.join(args.out, "aggregato.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    print(f"sessioni principali lette: {len(sessions)} (scartate perche' fuori periodo: {skipped})")
    print(f"subagenti con trascrizione: {tot_sub}")
    print(f"sessioni pi lette: {len(pi_sessions)} (scartate perche' fuori periodo: {pi_skipped})")
    print(f"righe JSONL lette: {tot_lines + pi_lines} (Claude {tot_lines} · pi {pi_lines})")
    print(f"righe scartate (malformate/non-JSON): {tot_bad + pi_bad}")
    print(f"agenti classificati: {len(all_agents)}")
    print(f"schede in {os.path.join(cards_dir, '*.md')}")
    print(f"aggregati in {args.out}/aggregato.{{json,md}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
