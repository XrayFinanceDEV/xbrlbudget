"use client";

import { useState } from "react";
import { numericDraftState } from "@/lib/budget-numeric-draft";

/** Keeps incomplete decimal drafts visible while a controlled value changes. */
export function NumericDraftInput({
  value, displayValue, onRawChange, allowNegative = false, className, disabled, placeholder, title, id, ariaLabel,
}: {
  value: string | number | null | undefined;
  /** Optional locale-formatted text shown only while the field is not being edited. */
  displayValue?: string;
  onRawChange: (raw: string) => void;
  allowNegative?: boolean;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  title?: string;
  id?: string;
  ariaLabel?: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <input
      id={id}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      aria-label={ariaLabel}
      className={className}
      disabled={disabled}
      placeholder={placeholder}
      title={title}
      value={draft ?? displayValue ?? (value == null ? "" : String(value))}
      onFocus={(event) => {
        const input = event.currentTarget;
        setDraft(value == null ? "" : String(value));
        input.select();
        if (displayValue !== undefined) {
          requestAnimationFrame(() => {
            if (document.activeElement === input) input.select();
          });
        }
      }}
      onChange={(event) => {
        const raw = event.currentTarget.value;
        const state = numericDraftState(raw, allowNegative);
        if (state === "invalid") return;
        setDraft(raw);
        if (state === "complete") onRawChange(raw);
      }}
      onBlur={() => {
        if (draft === "") onRawChange("");
        setDraft(null);
      }}
    />
  );
}

export const PercentInput = NumericDraftInput;
