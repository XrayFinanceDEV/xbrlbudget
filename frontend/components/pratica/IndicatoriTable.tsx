"use client";

import { cn, getErrorMessage } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatEuro, formatPct } from "@/lib/pratica-format";
import {
  INDICATOR_DEFS,
  scoreDotColor,
  type SerieIndicatori,
} from "@/lib/pratica-indicators";
import { RATING_COLOR, vistaColonna } from "@/lib/pratica-crisi";
import { IndicatoriCharts } from "@/components/pratica/IndicatoriCharts";
import type { CrisiInfrannuale } from "@/types/api";

export const formatIndicatorValue = (value: number, format: "euro" | "pct" | "ratio") => {
  if (format === "euro") return formatEuro(value);
  if (format === "pct") return formatPct(value);
  return `${value.toFixed(2)}x`;
};

/**
 * Gli indicatori della crisi d'impresa come li calcola il server
 * (`GET .../infrannuale/crisi`): questo componente non calcola nulla. Il
 * rating di infrannuale e proiezione segue i segnali extracontabili spuntati
 * in pagina, anche prima del salvataggio (`vistaColonna`).
 */
export function IndicatoriTable({
  crisi,
  crisiError,
  extraAlerts,
  showRating = true,
  hideProiezione = false,
}: {
  crisi: CrisiInfrannuale | null;
  crisiError: unknown;
  extraAlerts: Record<string, boolean>;
  showRating?: boolean;
  hideProiezione?: boolean;
}) {
  if (crisiError) {
    return (
      <p className="text-sm text-destructive">
        Indicatori non disponibili: {getErrorMessage(crisiError)}
      </p>
    );
  }
  if (!crisi) {
    return <p className="text-sm text-muted-foreground">Calcolo degli indicatori...</p>;
  }

  const alertCount = Object.values(extraAlerts).filter(Boolean).length;
  const storico = vistaColonna(crisi.storico, 0)!;
  const infra = vistaColonna(crisi.infrannuale, alertCount)!;
  const proiezione = vistaColonna(crisi.proiezione, alertCount);

  const serieGrafici: SerieIndicatori[] = [
    { periodo: `Storico ${crisi.reference_year}`, indicatori: storico.indicatori },
    { periodo: `Infrann. ${crisi.period_months}M`, indicatori: infra.indicatori },
    {
      periodo: `Proiezione ${crisi.partial_year}`,
      indicatori: hideProiezione ? null : proiezione?.indicatori ?? null,
    },
  ];

  return (
    <div className="space-y-4">
      {/* Overall Rating Cards - only shown after "Calcola Rating" */}
      {showRating && (
        <div className={cn("grid gap-4", hideProiezione ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${crisi.reference_year}`, vista: storico },
            { label: `Infrann. ${crisi.period_months}M ${crisi.partial_year}`, vista: infra },
            ...(!hideProiezione ? [{ label: `Proiezione ${crisi.partial_year}`, vista: proiezione }] : []),
          ].map((col) => (
            <div key={col.label} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-xs text-muted-foreground">{col.label}</p>
                {col.vista ? (
                  <p className={cn("text-2xl font-bold", RATING_COLOR[col.vista.rating.livello])}>
                    {col.vista.rating.codice}
                  </p>
                ) : (
                  <p className="text-2xl font-bold text-muted-foreground">—</p>
                )}
              </div>
              <div className="text-right">
                {col.vista ? (
                  <>
                    <p className={cn("text-sm font-medium", RATING_COLOR[col.vista.rating.livello])}>
                      {col.vista.rating.etichetta}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {col.vista.rating.oltre}/14 oltre
                      {col.vista.rating.segnali > 0 ? ` + ${col.vista.rating.segnali} segn.` : ""}
                    </p>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Genera proiezione
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <IndicatoriCharts serie={serieGrafici} />

      {/* Indicator Detail Table */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Indicatore</TableHead>
            <TableHead className="text-right">
              Storico {crisi.reference_year}
            </TableHead>
            <TableHead className="text-right">
              Infrann. {crisi.period_months}M {crisi.partial_year}
            </TableHead>
            {!hideProiezione && (
              <TableHead className="text-right">
                Proiezione {crisi.partial_year}
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {INDICATOR_DEFS.map((def) => (
            <TableRow key={def.key}>
              <TableCell className="font-medium">{def.label}</TableCell>
              <TableCell className="text-right">
                <span className="inline-flex items-center gap-2">
                  <span className="text-muted-foreground">
                    {formatIndicatorValue(storico.indicatori[def.key], def.format)}
                  </span>
                  {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(storico.punteggi[def.key]))} />}
                </span>
              </TableCell>
              <TableCell className="text-right">
                <span className="inline-flex items-center gap-2">
                  <span>{formatIndicatorValue(infra.indicatori[def.key], def.format)}</span>
                  {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(infra.punteggi[def.key]))} />}
                </span>
              </TableCell>
              {!hideProiezione && (
                <TableCell className="text-right">
                  {proiezione ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="font-medium">
                        {formatIndicatorValue(proiezione.indicatori[def.key], def.format)}
                      </span>
                      {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(proiezione.punteggi[def.key]))} />}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
