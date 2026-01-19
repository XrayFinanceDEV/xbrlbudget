import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "@/contexts/AppContext";
import { Navigation } from "@/components/Navigation";

export const metadata: Metadata = {
  title: "XBRL Budget - Analisi Finanziaria",
  description: "Italian GAAP Compliant Financial Analysis & Credit Rating System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="it">
      <body className="antialiased bg-gray-50" suppressHydrationWarning>
        <AppProvider>
          <div className="min-h-screen flex flex-col">
            {/* Header */}
            <header className="bg-white shadow-sm">
              <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
                <h1 className="text-2xl font-bold text-blue-600">
                  📊 Analisi Finanziaria - Sistema di Rating
                </h1>
                <p className="text-sm text-gray-600 mt-1">
                  Analisi di bilancio secondo i principi contabili italiani (OIC)
                </p>
              </div>
            </header>

            {/* Navigation */}
            <Navigation />

            {/* Main Content */}
            <main className="flex-1">
              {children}
            </main>
          </div>
        </AppProvider>
      </body>
    </html>
  );
}
