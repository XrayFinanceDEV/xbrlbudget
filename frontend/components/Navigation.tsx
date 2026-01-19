"use client";

import { useApp } from "@/contexts/AppContext";
import { getSectorName } from "@/lib/formatters";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_TABS = [
  { href: "/", label: "🏠 Home", match: (path: string) => path === "/" },
  { href: "/import", label: "📥 Importazione Dati", match: (path: string) => path.startsWith("/import") },
  { href: "/budget", label: "📝 Input Ipotesi", match: (path: string) => path.startsWith("/budget") },
  { href: "/forecast/income", label: "💰 CE Previsionale", match: (path: string) => path.startsWith("/forecast/income") },
  { href: "/forecast/balance", label: "📊 SP Previsionale", match: (path: string) => path.startsWith("/forecast/balance") },
  { href: "/forecast/reclassified", label: "📋 Previsionale Riclassificato", match: (path: string) => path.startsWith("/forecast/reclassified") },
  { href: "/analysis", label: "📈 Indici", match: (path: string) => path.startsWith("/analysis") },
  { href: "/cashflow", label: "💵 Rendiconto Finanziario", match: (path: string) => path.startsWith("/cashflow") },
];

export function Navigation() {
  const {
    companies,
    selectedCompanyId,
    setSelectedCompanyId,
    years,
    selectedYear,
    setSelectedYear,
    selectedCompany,
  } = useApp();

  const pathname = usePathname();

  return (
    <div className="bg-white border-b border-gray-200">
      {/* Top Selection Bar */}
      <div className="bg-gray-50 border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Company Selector */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                🏢 Azienda
              </label>
              <select
                value={selectedCompanyId || ""}
                onChange={(e) => setSelectedCompanyId(Number(e.target.value) || null)}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {companies.length === 0 && (
                  <option value="">Nessuna azienda</option>
                )}
                {companies.map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name} ({company.tax_id})
                  </option>
                ))}
              </select>
            </div>

            {/* Year Selector */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                📅 Anno Fiscale
              </label>
              <select
                value={selectedYear || ""}
                onChange={(e) => setSelectedYear(Number(e.target.value) || null)}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                disabled={years.length === 0}
              >
                {years.length === 0 && (
                  <option value="">Seleziona azienda</option>
                )}
                {years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            {/* Sector Display */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Settore
              </label>
              <div className="px-3 py-2 text-sm bg-white border border-gray-300 rounded-md text-gray-700 font-medium">
                {selectedCompany ? getSectorName(selectedCompany.sector) : "N/A"}
              </div>
            </div>

            {/* Tax ID Display */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                P.IVA
              </label>
              <div className="px-3 py-2 text-sm bg-white border border-gray-300 rounded-md text-gray-700 font-medium">
                {selectedCompany?.tax_id || "N/A"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex space-x-1 overflow-x-auto" aria-label="Tabs">
          {NAV_TABS.map((tab) => {
            const isActive = tab.match(pathname);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`
                  whitespace-nowrap px-4 py-3 text-sm font-medium border-b-2 transition-colors
                  ${
                    isActive
                      ? "border-blue-500 text-blue-600"
                      : "border-transparent text-gray-600 hover:text-gray-800 hover:border-gray-300"
                  }
                `}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
