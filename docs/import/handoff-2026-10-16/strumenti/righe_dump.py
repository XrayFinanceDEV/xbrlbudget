import sys, re, fitz
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AM = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d{1,3})?-?\)?$|^\(?-?\d+(?:,\d{1,3})?-?\)?$")
def righe(path, maxp=3):
    d = fitz.open(path)
    for pg in d[:maxp]:
        ws = sorted(pg.get_text("words"), key=lambda w: ((w[1]+w[3])/2, w[0]))
        gr = []
        for w in ws:
            c = (w[1]+w[3])/2
            if gr and abs(c - gr[-1][0]) <= 3: gr[-1][1].append(w)
            else: gr.append([c, [w]])
        for c, g in gr:
            g.sort(key=lambda w: w[0])
            toks = [w[4] for w in g]
            k = len(toks)
            while k > 0 and (AM.match(toks[k-1]) or toks[k-1] in ("€", "�")): k -= 1
            lab = " ".join(toks[:k]); am = [(w[4], round(w[2])) for w in g[k:] if w[4] not in ("€","�")]
            print(f"p{pg.number+1} {lab[:70]:70} {am}")
righe(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2)
