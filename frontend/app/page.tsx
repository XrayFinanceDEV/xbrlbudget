"use client";

import { useRouter } from "next/navigation";
import {
  CalendarRange,
  CalendarClock,
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

export default function Home() {
  const router = useRouter();

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card
          className="cursor-pointer transition-colors hover:border-primary/50"
          onClick={() => router.push("/aziende")}
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
          onClick={() => router.push("/infrannuale")}
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
      </div>
    </div>
  );
}
