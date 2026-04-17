"use client";

import { Card, CardContent } from "@/components/ui/card";
import { getSectorName } from "@/lib/formatters";
import type { ScenarioAnalysis } from "@/types/api";

interface ReportCoverProps {
  data: ScenarioAnalysis;
}

export function ReportCover({ data }: ReportCoverProps) {
  const company = data.scenario.company;
  const allYears = [
    ...data.historical_years.map((y) => y.year),
    ...data.forecast_years.map((y) => y.year),
  ];
  const minYear = Math.min(...allYears);
  const maxYear = Math.max(...allYears);

  const infoRows: Array<[string, string | number]> = [
    ["Ragione Sociale", company.name],
    ["Codice Fiscale / P.IVA", company.tax_id || "N/D"],
    ["Settore", getSectorName(company.sector)],
    ["Scenario", data.scenario.name],
    ["Anno Base", data.scenario.base_year],
    ["Anni Previsionali", data.scenario.projection_years],
    ["Anni Storici", data.historical_years.map((y) => y.year).join(", ")],
    ["Anni Forecast", data.forecast_years.map((y) => y.year).join(", ")],
  ];

  return (
    <section id="cover">
      <Card>
        <CardContent className="py-4 print:py-2">
          <div className="text-center mb-3 print:mb-2">
            <h2 className="text-2xl font-bold text-foreground print:text-xl">{company.name}</h2>
            <p className="text-base text-muted-foreground print:text-sm">
              Relazione sullo Scenario Economico Finanziario — Anni {minYear} - {maxYear}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm print:text-xs print:gap-y-0.5">
            {infoRows.map(([label, value]) => (
              <div
                key={label}
                className="flex items-baseline justify-between border-b border-border/60 py-1 print:py-0.5"
              >
                <span className="font-medium text-muted-foreground pr-3">{label}</span>
                <span className="text-right">{value}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
