"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkles } from "lucide-react";

interface ReportAICommentProps {
  comment?: string;
  loading?: boolean;
}

export function ReportAIComment({ comment, loading }: ReportAICommentProps) {
  if (loading) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex items-start gap-3 py-4">
          <Sparkles className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!comment) return null;

  return (
    <Card className="border-dashed bg-muted/30">
      <CardContent className="flex items-start gap-3 py-4">
        <Sparkles className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
        <p className="text-sm italic text-muted-foreground leading-relaxed">
          {comment}
        </p>
      </CardContent>
    </Card>
  );
}
