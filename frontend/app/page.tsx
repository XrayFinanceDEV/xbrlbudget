"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  CalendarRange,
  CalendarClock,
  Rocket,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useApp } from "@/contexts/AppContext";

export default function Home() {
  const router = useRouter();
  const { setStartupMode, setSelectedCompanyId } = useApp();

  // Landing on the home page always exits startup mode.
  useEffect(() => {
    setStartupMode(false);
  }, [setStartupMode]);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Card
          className="cursor-pointer transition-colors hover:border-primary/50"
          onClick={() => {
            setStartupMode(false);
            router.push("/aziende");
          }}
        >
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <CalendarRange className="h-6 w-6 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">Budget Pluriennale (3-5 Anni)</CardTitle>
                <CardDescription>
                  Analisi e previsione pluriennale completa
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Importa bilanci storici, definisci le ipotesi di crescita e genera
              previsioni a 3-5 anni con analisi completa degli indici, Altman Z-Score
              e rating FGPMI.
            </p>
            <Button variant="outline" className="w-full">
              Vai al Budget
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </CardContent>
        </Card>

        <Card
          className="cursor-pointer transition-colors hover:border-primary/50"
          onClick={() => {
            setStartupMode(false);
            router.push("/infrannuale");
          }}
        >
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <CalendarClock className="h-6 w-6 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">Situazione Contabile Infrannuale</CardTitle>
                <CardDescription>
                  Proiezione da bilancio parziale a 12 mesi
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Importa un bilancio infrannuale (es. 30/09), confronta con lo storico,
              proietta automaticamente a 12 mesi ed esegui l&apos;analisi completa
              sulla proiezione.
            </p>
            <Button variant="outline" className="w-full">
              Vai alla Situazione Infrannuale
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </CardContent>
        </Card>

        <Card
          className="cursor-pointer transition-colors hover:border-primary/50"
          onClick={() => {
            // Startup: no historical bilancio → enter startup mode and clear the
            // company selection so /budget shows the from-zero business-plan wizard.
            setStartupMode(true);
            setSelectedCompanyId(null);
            router.push("/budget");
          }}
        >
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <Rocket className="h-6 w-6 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">Business Plan Startup</CardTitle>
                <CardDescription>
                  Previsione da zero, senza bilancio storico
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Per una nuova attività senza storico: inserisci capitale di partenza
              e driver economici attesi (ricavi, margine, personale) e genera la
              proiezione a 3-5 anni con analisi completa, Altman Z-Score e rating
              FGPMI.
            </p>
            <Button variant="outline" className="w-full">
              Crea Business Plan
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
