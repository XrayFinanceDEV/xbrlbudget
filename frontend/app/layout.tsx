import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "@/contexts/AppContext";
import { ThemeProvider } from "@/components/theme-provider";
import { Navigation } from "@/components/Navigation";
import { ModeToggle } from "@/components/mode-toggle";
import { Toaster } from "@/components/ui/sonner";
import { BarChart3 } from "lucide-react";

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
    <html lang="it" suppressHydrationWarning>
      <body className="antialiased" suppressHydrationWarning>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <AppProvider>
            <div className="min-h-screen flex flex-col bg-background">
              {/* Header */}
              <header className="border-b border-border bg-background">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <BarChart3 className="h-6 w-6 text-primary" />
                    <div>
                      <h1 className="text-xl font-bold text-foreground">
                        Analisi Finanziaria
                      </h1>
                      <p className="text-xs text-muted-foreground">
                        Sistema di Rating - Principi OIC
                      </p>
                    </div>
                  </div>
                  <ModeToggle />
                </div>
              </header>

              {/* Navigation */}
              <Navigation />

              {/* Main Content */}
              <main className="flex-1">
                {children}
              </main>
            </div>
            <Toaster />
          </AppProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
