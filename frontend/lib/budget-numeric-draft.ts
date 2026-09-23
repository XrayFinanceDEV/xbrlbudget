/** A numeric draft may be unfinished while the user is typing a negative value. */
export function numericDraftState(raw: string, allowNegative: boolean): "invalid" | "partial" | "complete" {
  const sign = allowNegative ? "-?" : "";
  const draft = new RegExp(`^${sign}(?:\\d*(?:[.,]\\d*)?)$`);
  if (!draft.test(raw)) return "invalid";
  const complete = new RegExp(`^${sign}(?:\\d+(?:[.,]\\d*)?|[.,]\\d+)$`);
  return complete.test(raw) ? "complete" : "partial";
}
