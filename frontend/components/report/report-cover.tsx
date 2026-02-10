"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@/components/ui/table";
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

  return (
    <section id="cover">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Dati Aziendali</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center mb-6">
            <h2 className="text-3xl font-bold text-foreground">{company.name}</h2>
            <p className="text-lg text-muted-foreground mt-1">
              Relazione Analisi Indici &amp; Rating
            </p>
            <p className="text-muted-foreground">
              Anni {minYear} - {maxYear}
            </p>
          </div>

          <Table>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium w-1/3">Ragione Sociale</TableCell>
                <TableCell>{company.name}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Codice Fiscale / P.IVA</TableCell>
                <TableCell>{company.tax_id || "N/D"}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Settore</TableCell>
                <TableCell>{getSectorName(company.sector)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Scenario</TableCell>
                <TableCell>{data.scenario.name}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Anno Base</TableCell>
                <TableCell>{data.scenario.base_year}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Anni Previsionali</TableCell>
                <TableCell>{data.scenario.projection_years}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Anni Storici</TableCell>
                <TableCell>
                  {data.historical_years.map((y) => y.year).join(", ")}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Anni Forecast</TableCell>
                <TableCell>
                  {data.forecast_years.map((y) => y.year).join(", ")}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  );
}
