"use client";

import { usePathname } from "next/navigation";
import { BarChart3, CalendarClock } from "lucide-react";
import { ModeToggle } from "@/components/mode-toggle";
import { useAuth } from "@/contexts/AuthContext";

export function AppHeader() {
  const pathname = usePathname();
  const { logoUrl, userName } = useAuth();
  const isPratica = pathname.startsWith("/pratica");

  const title = isPratica
    ? "Analisi Infrannuale / Consuntivo"
    : "Simulatore di Scenari a 3/5 anni";

  const subtitle = isPratica
    ? "Proiezione da bilancio parziale a 12 mesi"
    : "Sistema di Rating - Principi OIC";

  const Icon = isPratica ? CalendarClock : BarChart3;

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
        <div className="flex items-center gap-3">
          {(logoUrl || userName) && (
            <div className="flex items-center gap-2 max-w-[260px]">
              {logoUrl && (
                <img
                  src={logoUrl}
                  alt="Logo"
                  className="h-8 w-auto object-contain"
                />
              )}
              {userName && (
                <span className="text-xs font-medium text-muted-foreground leading-tight truncate">
                  {userName}
                </span>
              )}
            </div>
          )}
          <ModeToggle />
        </div>
      </div>
    </header>
  );
}
