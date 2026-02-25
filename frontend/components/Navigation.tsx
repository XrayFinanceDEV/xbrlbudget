"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Building2,
  Upload,
  FileSpreadsheet,
  TrendingUp,
  BarChart3,
  ClipboardList,
  PieChart,
  Wallet,
  FileText,
  ChevronDown,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const MAIN_TABS = [
  { href: "/aziende", label: "Aziende", icon: Building2, match: (path: string) => path.startsWith("/aziende") },
  { href: "/import", label: "Importazione", icon: Upload, match: (path: string) => path.startsWith("/import") },
  { href: "/budget", label: "Input Ipotesi", icon: FileSpreadsheet, match: (path: string) => path.startsWith("/budget") },
];

const FORECAST_TABS = [
  { href: "/forecast/income", label: "CE Previsionale", icon: TrendingUp },
  { href: "/forecast/balance", label: "SP Previsionale", icon: BarChart3 },
  { href: "/forecast/reclassified", label: "Riclassificato", icon: ClipboardList },
];

const ANALYSIS_TABS = [
  { href: "/analysis", label: "Indici", icon: PieChart, match: (path: string) => path.startsWith("/analysis") },
  { href: "/cashflow", label: "Rendiconto", icon: Wallet, match: (path: string) => path.startsWith("/cashflow") },
  { href: "/report", label: "Report", icon: FileText, match: (path: string) => path.startsWith("/report") },
];

export function Navigation() {
  const pathname = usePathname();
  const isForecastActive = pathname.startsWith("/forecast");

  // Hide navigation on homepage and infrannuale (has its own nav)
  if (pathname === "/" || pathname.startsWith("/infrannuale")) return null;

  return (
    <div className="border-b border-border bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Tabs">
          {MAIN_TABS.map((tab) => {
            const isActive = tab.match(pathname);
            const Icon = tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap px-3 py-3 text-sm font-medium border-b-2 transition-colors",
                  isActive
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </Link>
            );
          })}

          {/* Forecast Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap px-3 py-3 text-sm font-medium border-b-2 transition-colors",
                  isForecastActive
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <TrendingUp className="h-4 w-4" />
                Previsionale
                <ChevronDown className="h-3 w-3" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {FORECAST_TABS.map((tab) => {
                const Icon = tab.icon;
                return (
                  <DropdownMenuItem key={tab.href} asChild>
                    <Link href={tab.href} className="flex items-center gap-2">
                      <Icon className="h-4 w-4" />
                      {tab.label}
                    </Link>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>

          {ANALYSIS_TABS.map((tab) => {
            const isActive = tab.match(pathname);
            const Icon = tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap px-3 py-3 text-sm font-medium border-b-2 transition-colors",
                  isActive
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
