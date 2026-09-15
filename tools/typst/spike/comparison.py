"""Publishable, self-contained comparison with actual vector probe outputs."""
from __future__ import annotations

import json
from pathlib import Path

from tools.typst.spike.packages import HERE


def build_comparison(output: Path) -> Path:
    results = json.loads((output / "results.json").read_text())
    probes = json.loads((output / "probes.json").read_text())
    for row in probes:
        if not row["exit_code"]:
            row["svg"] = (output / "probes" / f"{row['candidate']}-{row['chart']}" / "chart.svg").read_text()
    payload = json.dumps({"results": results, "probes": probes}, ensure_ascii=False).replace("<", "\\u003c")
    template = '''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>M2-00 · Confronto renderer</title><style>
    *{box-sizing:border-box}body{margin:0;background:#edf1f3;color:#183d4a;font:14px system-ui,sans-serif}main{max-width:1320px;padding:40px 24px;margin:auto}h1{font:36px Georgia,serif;margin:12px 0}p{line-height:1.7;color:#56717d}a{color:#183d4a}.tag{font-size:11px;letter-spacing:2px;color:#a77937}.decision{background:#183d4a;color:white;padding:22px 28px;margin:28px 0;border-radius:6px}.decision p{color:#d8e5eb;margin-bottom:0}.table{overflow:auto}table{border-collapse:collapse;width:100%;background:white;font-size:13px}th,td{padding:14px 16px;text-align:left;border-bottom:1px solid #dce5e9}th{background:#f7f9fa}select{font:inherit;padding:10px;border:1px solid #bccfd7;border-radius:5px;color:#183d4a;background:#fff}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:20px 0}.card{background:#fff;border:1px solid #dce5e9;min-width:0;border-radius:5px;overflow:hidden}.card h3{padding:18px 18px 8px;margin:0;font:22px Georgia,serif}.metric{padding:0 18px;font-size:11px;color:#6b838e}.graphic svg{width:100%;height:auto}.graphic{padding:0 8px}.error{padding:24px 18px;color:#9a4c43;line-height:1.7;overflow-wrap:anywhere;font-size:12px}.note{font-size:12px;border-left:3px solid #b28646;padding:12px 16px;background:#f8f4ed}details{margin:25px 0}pre{white-space:pre-wrap;font:11px monospace;line-height:1.6;color:#56717d}.sources{font-size:12px}@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:25px 16px}h1{font-size:29px}.graphic{max-height:750px;overflow:hidden}}</style></head><body><main>
    <div class="tag">M2-00 / SPIKE TECNICO / DATI SINTETICI</div><h1>Confronto dei renderer grafici</h1><p>Stessi snapshot M1 a 1, 3 e 5 anni. Tutti i processi sono eseguiti in un namespace Linux senza rete, con Typst 0.15.1, un solo job e font di sistema esclusi.</p>
    <div class="decision"><strong>Scelta tecnica proposta: primitive native Typst.</strong><p>Coprono i sei grafici, null e negativi, con meno tempo e memoria. CeTZ è una valida alternativa. Primaviz 0.10.0 richiede un adapter aggiuntivo per le serie parziali e una correzione del dominio delle barre negative.</p></div>
    <div class="table"><table><thead><tr><th>Candidato</th><th>Report validi</th><th>Tempo osservato</th><th>Picco RSS</th><th>Grafica</th><th>Dipendenze</th></tr></thead><tbody id="summary"></tbody></table></div>
    <h2>Grafici reali del confronto</h2><p>Gli SVG qui sotto provengono dai PDF compilati dai singoli candidati. Un errore resta visibile: nessun dato mancante viene sostituito con zero.</p>
    <label for="chart">Grafico </label><select id="chart"></select><div class="grid" id="samples"></div>
    <div class="note" id="finding"></div><details><summary>Errori di compilazione del grafico selezionato</summary><pre id="errors"></pre></details>
    <p class="sources">Versioni e licenze: <a href="https://typst.app/universe/package/cetz-plot/">CeTZ-Plot 0.1.4</a> + CeTZ 0.5.2 (LGPL-3.0-or-later), oxifmt 1.0.0 (MIT o Apache-2.0); <a href="https://typst.app/universe/package/primaviz/">Primaviz 0.10.0</a> (MIT). La scelta native aggiunge zero pacchetti.</p>
    <p class="sources">PDF/A-2u: il compilatore accetta il profilo per native e CeTZ. Non è una certificazione: la verifica formale veraPDF resta da eseguire. Le misure sono locali, non un benchmark di produzione. Riproduzione locale completata; review indipendente prevista dal piano ancora da svolgere.</p>
    </main><script id="data" type="application/json">PAYLOAD</script><script>
    const data=JSON.parse(document.getElementById('data').textContent),candidates=['native','cetz','primaviz'],names={native:'Primitive native',cetz:'CeTZ-Plot',primaviz:'Primaviz'},esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    document.getElementById('summary').innerHTML=candidates.map(c=>{const rows=data.results.results.filter(x=>x.candidate===c),ok=rows.filter(x=>x.exit_code===0),times=rows.map(x=>x.seconds),rss=Math.max(...rows.map(x=>x.peak_rss_kib))/1024;return `<tr><td><strong>${names[c]}</strong></td><td>${ok.length}/12</td><td>${ok.length?Math.min(...times).toFixed(2)+'–'+Math.max(...times).toFixed(2)+' s':'interrotto sui null'}</td><td>${rss.toFixed(1)} MiB</td><td>${ok.length?'Vettoriale · 0 raster':'4/8 probe compilano'}</td><td>${c==='native'?'0':c==='cetz'?'3 pacchetti + WASM':'1 pacchetto'}</td></tr>`}).join('');
    const charts=[...new Set(data.probes.map(x=>x.chart))],select=document.getElementById('chart');select.innerHTML=charts.map(c=>`<option value="${c}">${c.replaceAll('_',' ')}</option>`).join('');select.value='margins';
    function render(){const rows=data.probes.filter(x=>x.chart===select.value);document.getElementById('samples').innerHTML=rows.map(r=>`<article class="card"><h3>${names[r.candidate]}</h3><div class="metric">${r.exit_code===0?'Compilato · '+r.seconds.toFixed(3)+' s · '+(r.peak_rss_kib/1024).toFixed(1)+' MiB':'Compilazione fallita'}</div>${r.svg?'<div class="graphic">'+r.svg+'</div>':'<div class="error">Il candidato non accetta i valori non disponibili presenti nella serie. Errore: '+esc(r.stderr.split('\\n')[0])+'</div>'}</article>`).join('');document.getElementById('errors').textContent=rows.filter(r=>r.exit_code).map(r=>names[r.candidate]+'\\n'+r.stderr).join('\\n\\n')||'Nessun errore di compilazione.';document.getElementById('finding').textContent=['margins','working_capital_days','coverage','all_null'].includes(select.value)?'Native e CeTZ mantengono i null e le interruzioni. Primaviz passa none a calc.min/calc.max e interrompe la compilazione.':'I tre candidati compilano questa serie completa. Per le barre negative Primaviz mantiene il minimo dell’asse a zero: i valori negativi cadono sotto il dominio del grafico e possono interferire con le etichette degli anni.';}
    select.addEventListener('change',render);render();</script></body></html>'''
    path = output / "confronto-renderer.html"
    path.write_text(template.replace("PAYLOAD", payload), encoding="utf-8")
    print(path, path.stat().st_size, "bytes")
    return path


if __name__ == "__main__":
    build_comparison(HERE / "output")
