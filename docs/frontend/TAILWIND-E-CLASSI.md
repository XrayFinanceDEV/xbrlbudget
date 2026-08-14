# Tailwind: dove possono vivere i nomi di classe

> Regola in una riga: **una classe Tailwind scritta in un file che `content` non scandisce non
> viene generata.** Nessun errore, nessun warning — solo un elemento senza stile.

## Il meccanismo

Tailwind non conosce il CSS che ti serve: lo *deduce* leggendo i file elencati in
`content` (`frontend/tailwind.config.ts`) e cercandovi stringhe che somigliano a nomi di
classe. Quello che non legge non esiste. Il fallimento è quindi **silenzioso per
costruzione**: il build passa, TypeScript passa, i test passano, e l'elemento in pagina
resta trasparente.

`content` deve elencare **ogni cartella che contiene letterali di classe**, non solo
quelle che contengono JSX:

```ts
content: [
  "./pages/**/*.{js,ts,jsx,tsx,mdx}",
  "./components/**/*.{js,ts,jsx,tsx,mdx}",
  "./app/**/*.{js,ts,jsx,tsx,mdx}",
  "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  "./hooks/**/*.{js,ts,jsx,tsx,mdx}",
  "./contexts/**/*.{js,ts,jsx,tsx,mdx}",
],
```

## Il caso che ha reso la regola necessaria (2026-08-14)

La decomposizione di `app/pratica/page.tsx` ha spostato le funzioni pure in `lib/`, e con
esse `scoreDotColor` e `ratingColor` (`lib/pratica-indicators.ts`) — due funzioni che
**restituiscono nomi di classe**:

```ts
export function scoreDotColor(score: number): string {
  if (score >= 0.67) return "bg-green-500";
  if (score >= 0.33) return "bg-yellow-500";
  return "bg-red-500";
}
```

`content` non elencava `lib/`. Risultato: `bg-green-500`, `bg-yellow-500` e `bg-red-500`
non venivano mai emesse, e **tutti e 42 i pallini di valutazione** — nella tab Indicatori e
nel PDF della Stampa — erano trasparenti. Con essi spariva `text-orange-600`, il colore
della fascia di rating "C".

Perché nessuno se n'era accorto prima: le tre classi *sembrano* comunissime. Lo sono, ma
nella forma con opacità (`bg-green-500/10`) usata altrove, che è una classe **diversa** e
non implica la generazione di quella piena.

## Come si verifica (e come NON si verifica)

Questo controllo è **sbagliato** e risponde di sì anche quando la classe manca:

```bash
grep "\.bg-green-500" foglio.css     # trova .bg-green-500\/10 e .dark\:bg-green-500\/15
```

Questo è corretto — cerca la regola esatta, cioè il nome seguito da `{` o `,`:

```bash
curl -s http://localhost:3000/_next/static/css/app/layout.css > foglio.css
grep -E "\.bg-green-500[[:space:]]*[{,]" foglio.css
```

La prova definitiva resta il browser, che non si fa ingannare da nessuna sottostringa:

```js
getComputedStyle(document.querySelector("span.bg-green-500")).backgroundColor
// "rgba(0, 0, 0, 0)"  -> la regola non esiste
// "rgb(34, 197, 94)"  -> generata
```

Durante la diagnosi il primo controllo per sottostringa disse che verde e rosso c'erano; il
browser disse che erano trasparenti. Aveva ragione il browser.

## La rete

`frontend/lib/tailwind-content.test.ts` fissa l'**invariante generale**, non i tre nomi del
caso: scandisce `lib/`, `hooks/`, `contexts/`, `app/`, `components/` e fallisce se una
cartella contiene letterali di classe pur non essendo in `content`. Vale quindi anche per
la prossima funzione che restituirà un colore da un modulo nuovo.

## Conseguenza di progetto

Una funzione che restituisce nomi di classe è codice di presentazione ospitato in un modulo
puro. Va bene — è la ragione per cui `lib/` è in `content` — ma va ricordato che sposta
l'informazione di stile fuori dai file dove ci si aspetta di trovarla. Se un colore non
compare, il primo sospetto non è il CSS: è `content`.
