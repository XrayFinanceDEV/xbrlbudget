"use client";

import { usePathname } from "next/navigation";
import { BarChart3, CalendarClock } from "lucide-react";
import { ModeToggle } from "@/components/mode-toggle";

export function AppHeader() {
  const pathname = usePathname();
  const isInfrannuale = pathname.startsWith("/infrannuale");

  const title = isInfrannuale
    ? "Situazione Contabile Infrannuale"
    : "Simulatore di Scenari Economici Finanziari";

  const subtitle = isInfrannuale
    ? "Proiezione da bilancio parziale a 12 mesi"
    : "Sistema di Rating - Principi OIC";

  const Icon = isInfrannuale ? CalendarClock : BarChart3;

  return (
    <header className="border-b border-border bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Icon className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-xl font-bold text-foreground">
              {title}
            </h1>
            <p className="text-xs text-muted-foreground">
              {subtitle}
            </p>
          </div>
        </div>
        <ModeToggle />
      </div>
    </header>
  );
}
