import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/providers";
import { AuthProvider } from "@/contexts/AuthContext";
import { AppProvider } from "@/contexts/AppContext";
import { ThemeProvider } from "@/components/theme-provider";
import { Navigation } from "@/components/Navigation";
import { AppHeader } from "@/components/AppHeader";
import { Toaster } from "@/components/ui/sonner";

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
        <QueryProvider>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <AuthProvider>
          <AppProvider>
            <div className="min-h-screen flex flex-col bg-background">
              {/* Header */}
              <AppHeader />

              {/* Navigation */}
              <Navigation />

              {/* Main Content */}
              <main className="flex-1">
                {children}
              </main>
            </div>
            <Toaster />
          </AppProvider>
          </AuthProvider>
        </ThemeProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
