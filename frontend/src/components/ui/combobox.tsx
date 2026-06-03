import { useState, useRef, useEffect, useCallback } from "react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { Check } from "lucide-react"

interface ComboboxProps {
  value: string
  onChange: (value: string) => void
  options: string[]
  placeholder?: string
  disabled?: boolean
  className?: string
}

export function Combobox({ value, onChange, options, placeholder, disabled, className }: ComboboxProps) {
  const [open, setOpen] = useState(false)
  const [highlightIdx, setHighlightIdx] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = options.filter((o) =>
    o.toLowerCase().includes((value || "").toLowerCase())
  )

  const select = useCallback(
    (v: string) => {
      onChange(v)
      setOpen(false)
      setHighlightIdx(-1)
    },
    [onChange],
  )

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setHighlightIdx(-1)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { setOpen(true); e.preventDefault() }
      return
    }
    if (e.key === "Escape") { setOpen(false); setHighlightIdx(-1); return }
    if (e.key === "Enter") {
      e.preventDefault()
      if (highlightIdx >= 0 && highlightIdx < filtered.length) {
        select(filtered[highlightIdx])
      } else {
        setOpen(false)
        setHighlightIdx(-1)
      }
      return
    }
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setHighlightIdx((p) => (p + 1 >= filtered.length ? 0 : p + 1))
      return
    }
    if (e.key === "ArrowUp") {
      e.preventDefault()
      setHighlightIdx((p) => (p - 1 < 0 ? filtered.length - 1 : p - 1))
      return
    }
  }

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
          setHighlightIdx(-1)
        }}
        onFocus={() => { if (filtered.length > 0) setOpen(true) }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md max-h-48 overflow-y-auto">
          {filtered.map((opt, i) => (
            <button
              key={opt}
              type="button"
              className={cn(
                "flex w-full items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent",
                i === highlightIdx && "bg-accent",
                opt === value && "font-medium",
              )}
              onMouseDown={(e) => { e.preventDefault(); select(opt) }}
              onMouseEnter={() => setHighlightIdx(i)}
            >
              <span className="flex-1 text-left truncate">{opt}</span>
              {opt === value && <Check className="h-3.5 w-3.5 shrink-0 opacity-60" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
