import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Normalize an unknown error (typically an Axios error) into a plain string
 * suitable for toast/Alert rendering.
 *
 * The backend returns FastAPI `detail` in several shapes:
 *  - a plain string ("Filename is required")
 *  - an ImportError object ({ success, error, error_type, details })
 *  - a validation array ([{ loc, msg, type }, ...])
 * Passing any non-string value straight to a React child throws
 * "Objects are not valid as a React child", so always funnel errors through here.
 */
export function getErrorMessage(error: unknown, fallback = "Si è verificato un errore"): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const fromDetail = normalizeDetail(detail)
  if (fromDetail) return fromDetail

  if (error instanceof Error && error.message) return error.message
  if (typeof error === "string" && error) return error
  return fallback
}

function normalizeDetail(detail: unknown): string | null {
  if (!detail) return null
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean)
    return msgs.length ? msgs.join("; ") : null
  }
  if (typeof detail === "object") {
    const obj = detail as { error?: unknown; details?: unknown; message?: unknown }
    const main = obj.error ?? obj.message
    if (typeof main === "string" && main) {
      return typeof obj.details === "string" && obj.details ? `${main}: ${obj.details}` : main
    }
  }
  return null
}
