import { useState, useRef, useCallback, useMemo, useEffect } from "react"
import { cn } from "@/lib/utils"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

interface MarkdownEditorProps {
  value: string
  onChange: (value: string) => void
  className?: string
  minHeight?: string
  placeholder?: string
  /** "block" = Typora-style per-block editing (default). "plain" = simple textarea + preview overlay. */
  variant?: "block" | "plain"
}

function listPrefix(block: string): string {
  const m = /^([-*+]\s|(\d+)\.\s|[-*]\s\[[ x]\]\s)/m.exec(block.trimStart())
  return m ? m[0].replace(/^\d+/, "0") : ""
}

function splitBlocks(text: string): string[] {
  if (!text.trim()) return [text]
  const raw = text.split(/\n\n+/)
  const merged: string[] = []
  for (const block of raw) {
    const trimmed = block.trim()
    if (!trimmed) {
      merged.push(block)
      continue
    }
    const prev = merged[merged.length - 1]
    const curPrefix = listPrefix(trimmed)
    const prevPrefix = prev ? listPrefix(prev.trim()) : ""
    if (curPrefix && curPrefix === prevPrefix) {
      merged[merged.length - 1] = prev + "\n" + block
    } else {
      merged.push(block)
    }
  }
  return merged
}

// ─── Plain variant (simple textarea + preview overlay) ──────────────────────

function PlainEditor({ value, onChange, className, minHeight, placeholder }: MarkdownEditorProps) {
  const [focused, setFocused] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleFocus = () => setFocused(true)
  const handleBlur = () => setFocused(false)

  const isEmpty = !value.trim()

  return (
    <div className={cn("md-editor", className)} style={{ minHeight }}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={handleFocus}
        onBlur={handleBlur}
        className={cn("md-editor-textarea", focused && "md-editor-textarea-focused")}
        placeholder={placeholder}
      />
      {!focused && !isEmpty && (
        <div className="md-editor-overlay" onClick={() => textareaRef.current?.focus()}>
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
          </div>
        </div>
      )}
      {!focused && isEmpty && (
        <div className="md-editor-overlay" onClick={() => textareaRef.current?.focus()}>
          <span className="text-muted-foreground italic text-sm">
            {placeholder || "Nothing to preview"}
          </span>
        </div>
      )}
    </div>
  )
}

// ─── Block variant (Typora-style per-block editing) ─────────────────────────

function BlockEditor({ value, onChange, className, minHeight, placeholder }: MarkdownEditorProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const editingTextRef = useRef<string>("")
  const blockRefs = useRef<Map<number, HTMLTextAreaElement>>(new Map())
  const snapshotRef = useRef<string[]>([])
  const prevValueRef = useRef(value)
  const internalChangeRef = useRef(false)

  const blocks = useMemo(() => splitBlocks(value), [value])
  const isEmpty = !value.trim()

  const displayBlocks = editingIndex !== null ? snapshotRef.current : blocks

  // Only reset editing on external value changes
  useEffect(() => {
    if (prevValueRef.current !== value) {
      if (internalChangeRef.current) {
        internalChangeRef.current = false
      } else if (editingIndex !== null) {
        setEditingIndex(null)
      }
    }
    prevValueRef.current = value
  }, [value, editingIndex])

  const handleBlockClick = useCallback(
    (index: number) => {
      // Freeze current blocks as snapshot
      snapshotRef.current = splitBlocks(value)
      editingTextRef.current = snapshotRef.current[index] || ""
      setEditingIndex(index)
      requestAnimationFrame(() => {
        const ta = blockRefs.current.get(index)
        if (ta) {
          ta.focus()
          ta.setSelectionRange(ta.value.length, ta.value.length)
        }
      })
    },
    [value],
  )

  const handleBlockChange = useCallback(
    (newRaw: string) => {
      editingTextRef.current = newRaw
      const rebuilt = [...snapshotRef.current]
      if (editingIndex !== null) {
        rebuilt[editingIndex] = newRaw
      }
      internalChangeRef.current = true
      onChange(rebuilt.join("\n\n"))
    },
    [editingIndex, onChange],
  )

  const handleBlockBlur = useCallback(() => {
    // Finalize: let blocks re-split from the new value
    setEditingIndex(null)
    snapshotRef.current = []
  }, [])

  const handleBlockKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Escape") {
        setEditingIndex(null)
        snapshotRef.current = []
      }
    },
    [],
  )

  if (isEmpty && editingIndex === null) {
    return (
      <div
        className={cn("md-editor flex items-center justify-center", className)}
        style={{ minHeight }}
        onClick={() => {
          snapshotRef.current = [""]
          editingTextRef.current = ""
          setEditingIndex(0)
          requestAnimationFrame(() => {
            const ta = blockRefs.current.get(0)
            if (ta) ta.focus()
          })
        }}
      >
        {editingIndex === 0 ? (
          <textarea
            ref={(el) => {
              if (el) blockRefs.current.set(0, el)
              else blockRefs.current.delete(0)
            }}
            className="md-block-textarea w-full"
            style={{ minHeight }}
            value={editingTextRef.current}
            onChange={(e) => {
              editingTextRef.current = e.target.value
              internalChangeRef.current = true
              onChange(e.target.value)
            }}
            onBlur={handleBlockBlur}
            onKeyDown={handleBlockKeyDown}
            placeholder={placeholder || "Write something..."}
          />
        ) : (
          <span className="text-muted-foreground italic text-sm cursor-text">
            {placeholder || "Click to start writing..."}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className={cn("md-editor", className)} style={{ minHeight }}>
      <div className="p-3 space-y-3">
        {displayBlocks.map((block, i) => {
          const isEditing = editingIndex === i
          const blockTrimmed = block.trim()

          if (isEditing) {
            return (
              <textarea
                key={i}
                ref={(el) => {
                  if (el) blockRefs.current.set(i, el)
                  else blockRefs.current.delete(i)
                }}
                className="md-block-textarea"
                value={editingTextRef.current}
                onChange={(e) => handleBlockChange(e.target.value)}
                onBlur={handleBlockBlur}
                onKeyDown={handleBlockKeyDown}
                rows={Math.max(1, (editingTextRef.current || block).split("\n").length + 1)}
              />
            )
          }

          return (
            <div
              key={i}
              className="md-block-rendered cursor-text rounded-sm -mx-1 px-1 py-0.5 hover:bg-muted/50 transition-colors"
              onClick={() => handleBlockClick(i)}
            >
              <div className="prose prose-sm max-w-none prose-p:my-1 prose-pre:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-headings:my-2 prose-hr:my-2">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {blockTrimmed || " "}
                </ReactMarkdown>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Public component ───────────────────────────────────────────────────────

export function MarkdownEditor(props: MarkdownEditorProps) {
  const { variant = "block" } = props
  if (variant === "plain") return <PlainEditor {...props} />
  return <BlockEditor {...props} />
}
