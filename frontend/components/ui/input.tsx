import * as React from "react"

import { numeroIncollato } from "@/lib/numero-incollato"
import { cn } from "@/lib/utils"

/**
 * Incollare un importo italiano («45.600,74») in un campo numerico: il browser tiene il punto
 * come decimale e scrive 45,6. Qui, in un punto solo, vale per ogni `type="number"` dell'app.
 *
 * Il valore si scrive col setter nativo e un evento `input`, non assegnando `value`: è l'unico
 * modo perché React veda la modifica e chiami `onChange` come per una digitazione. L'importo
 * incollato SOSTITUISCE il contenuto del campo — su un campo numerico il browser non espone la
 * posizione del cursore, e incollare accanto a uno «0» già presente darebbe «045600.74».
 */
export function incollaNumeroItaliano(event: React.ClipboardEvent<HTMLInputElement>) {
  const valore = numeroIncollato(event.clipboardData.getData("text"))
  if (valore === null) return
  event.preventDefault()
  const campo = event.currentTarget
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set
  setter?.call(campo, valore)
  campo.dispatchEvent(new Event("input", { bubbles: true }))
}

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, onPaste, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className
        )}
        ref={ref}
        onPaste={(event) => {
          onPaste?.(event)
          if (type === "number" && !event.defaultPrevented) incollaNumeroItaliano(event)
        }}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
