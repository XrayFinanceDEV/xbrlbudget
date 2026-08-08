"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, CheckCircle2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PageHeader } from "@/components/page-header";
import { ImportPanel } from "@/components/import/ImportPanel";

export default function ImportPage() {
  const router = useRouter();
  const [lastImportOk, setLastImportOk] = useState(false);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Importazione Dati"
        description="Importa bilanci da file PDF, XBRL o CSV"
        icon={<Upload className="h-6 w-6" />}
      />

      <ImportPanel periodMonths={null} fixedCompanyId={null} onSuccess={() => setLastImportOk(true)} />

      {lastImportOk && (
        <Alert className="mt-4">
          <CheckCircle2 className="h-4 w-4" />
          <AlertDescription className="flex items-center justify-between gap-4">
            <span>Importazione completata. Prosegui con una pratica guidata dalla home.</span>
            <Button size="sm" onClick={() => router.push("/")}>
              Vai alla home <ArrowRight className="h-4 w-4" />
            </Button>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
