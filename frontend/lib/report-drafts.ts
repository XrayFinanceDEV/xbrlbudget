export interface ReportDraftBucket { values: Record<string, string>; dirty: Record<string, boolean> }
export type ReportDraftBuckets = Record<string, ReportDraftBucket>;

export function syncReportDrafts(store: ReportDraftBuckets, scope: string, notes: Array<{ id: string; text: string }>): void {
  const bucket = store[scope] ?? { values: {}, dirty: {} };
  for (const note of notes) if (!bucket.dirty[note.id]) bucket.values[note.id] = note.text;
  store[scope] = bucket;
}

export function editReportDraft(store: ReportDraftBuckets, scope: string, id: string, text: string): void {
  const bucket = store[scope] ?? { values: {}, dirty: {} };
  bucket.values[id] = text;
  bucket.dirty[id] = true;
  store[scope] = bucket;
}

export function acknowledgeReportDraft(store: ReportDraftBuckets, scope: string, id: string, submitted: string): void {
  const bucket = store[scope];
  if (bucket && bucket.values[id]?.trim() === submitted.trim()) bucket.dirty[id] = false;
}
