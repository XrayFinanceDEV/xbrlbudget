"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ReportNotes() {
  return (
    <section id="notes">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Note Metodologiche</CardTitle>
        </CardHeader>
        <CardContent className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground">
          <p>
            <strong>Altman Z-Score:</strong> Modello di previsione della probabilita
            di default aziendale sviluppato dal Prof. Edward Altman. Per le aziende
            manifatturiere (settore 1) si utilizza il modello a 5 componenti; per
            tutti gli altri settori il modello a 4 componenti.
            Z &gt; 2,60 = Sicurezza; 1,10 &lt; Z &lt; 2,60 = Zona grigia;
            Z &lt; 1,10 = Rischio.
          </p>
          <p>
            <strong>EM-Score:</strong> Mappatura dello Z-Score su una scala di
            rating creditizio da AAA a D, calibrata sul modello a 4 componenti.
            Per le aziende manifatturiere lo Z-Score viene ricalcolato con la
            formula servizi prima del lookup.
          </p>
          <p>
            <strong>FGPMI:</strong> Rating per le Piccole e Medie Imprese basato
            su 7 indicatori finanziari con punteggi settoriali specifici. Il
            punteggio massimo varia per settore. Bonus di +2 punti se il fatturato
            supera i 500.000 euro.
          </p>
          <p>
            <strong>Break Even Point:</strong> Analisi del punto di pareggio con
            ripartizione dei costi in fissi (40%) e variabili (60%) dei costi
            operativi. Il margine di sicurezza indica la distanza percentuale tra
            il fatturato attuale e il punto di pareggio.
          </p>
          <p>
            <strong>Rendiconto Finanziario:</strong> Metodo indiretto conforme
            all&apos;OIC 10. I flussi sono suddivisi in attivita operativa, di
            investimento e di finanziamento.
          </p>
          <p>
            <strong>Previsioni:</strong> Gli anni contrassegnati con (P) sono
            previsioni basate sulle ipotesi di budget inserite dall&apos;utente.
            Le previsioni non costituiscono garanzia di risultati futuri.
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
