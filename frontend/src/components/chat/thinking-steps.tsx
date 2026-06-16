import { useState, useEffect, useCallback } from "react"
import {
  ChevronRight,
  ChevronDown,
  Check,
  Loader2,
  Cpu,
  Search,
  SlidersHorizontal,
  RotateCcw,
  Puzzle,
  Sparkles,
  Layers,
} from "lucide-react"
import type { ThinkingIteration, MetaInfo } from "@/stores/app-store"
import { cn } from "@/lib/utils"

interface ThinkingStepsProps {
  steps: ThinkingIteration[]
  metaInfo?: MetaInfo
  isStreaming: boolean
}

const STEP_ICONS: Record<string, typeof Search> = {
  retrieving: Search,
  grading: SlidersHorizontal,
  rewriting: RotateCcw,
  decomposing: Puzzle,
  synthesizing: Sparkles,
  generating: Sparkles,
  assembling: Layers,
}

function getStepIcon(label: string) {
  const lower = label.toLowerCase()
  for (const [key, Icon] of Object.entries(STEP_ICONS)) {
    if (lower.includes(key)) return Icon
  }
  return Cpu
}

export function ThinkingSteps({ steps, metaInfo, isStreaming }: ThinkingStepsProps) {
  const totalSteps = steps.reduce((acc, g) => acc + g.steps.length, 0)

  // Top-level collapse: expanded during streaming, collapsed after
  const [topExpanded, setTopExpanded] = useState(true)
  // Which iterations are expanded (by iteration number)
  const [expandedIters, setExpandedIters] = useState<Set<number>>(new Set())

  // Auto-expand current iteration, collapse previous during streaming
  useEffect(() => {
    if (!isStreaming) {
      // After streaming: collapse everything
      setTopExpanded(false)
      return
    }
    // During streaming: expand the latest iteration
    if (steps.length > 0) {
      const latestIter = steps[steps.length - 1].iteration
      setExpandedIters(new Set([latestIter]))
      setTopExpanded(true)
    }
  }, [steps.length, isStreaming])

  const toggleIter = useCallback((iter: number) => {
    setExpandedIters(prev => {
      const next = new Set(prev)
      if (next.has(iter)) next.delete(iter)
      else next.add(iter)
      return next
    })
  }, [])

  if (totalSteps === 0) return null

  return (
    <div className="mb-3">
      {/* Meta info bar */}
      {metaInfo && (metaInfo.provider || metaInfo.model) && (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground/60 mb-2 flex-wrap">
          {metaInfo.provider && metaInfo.model && (
            <span>{metaInfo.provider} / {metaInfo.model}</span>
          )}
          {metaInfo.search_mode && (
            <>
              <span className="text-border">·</span>
              <span>{metaInfo.search_mode}</span>
            </>
          )}
          {metaInfo.mode && (
            <>
              <span className="text-border">·</span>
              <span>{metaInfo.mode === "agentic" ? "Agentic RAG" : metaInfo.mode}</span>
            </>
          )}
          {metaInfo.max_iterations && (
            <>
              <span className="text-border">·</span>
              <span>max {metaInfo.max_iterations} iterations</span>
            </>
          )}
        </div>
      )}

      {/* Thinking steps container */}
      <div className="border border-border/40 rounded-lg bg-muted/15 overflow-hidden">
        {/* Top-level toggle */}
        <button
          type="button"
          onClick={() => setTopExpanded(!topExpanded)}
          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {topExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          )}
          {isStreaming && (
            <Loader2 className="h-3 w-3 animate-spin shrink-0" />
          )}
          <span className="font-medium">
            {isStreaming ? "Thinking..." : `Steps (${totalSteps})`}
          </span>
        </button>

        {/* Iteration groups */}
        {topExpanded && (
          <div className="px-2 pb-2 space-y-1">
            {steps.map((group) => {
              const isIterExpanded = expandedIters.has(group.iteration)
              const isPhase2 = group.iteration === 0

              return (
                <div key={group.iteration}>
                  {/* Iteration header */}
                  <button
                    type="button"
                    onClick={() => toggleIter(group.iteration)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 text-[11px] text-muted-foreground/80 hover:text-foreground transition-colors rounded"
                  >
                    {isIterExpanded ? (
                      <ChevronDown className="h-3 w-3 shrink-0" />
                    ) : (
                      <ChevronRight className="h-3 w-3 shrink-0" />
                    )}
                    <span className="font-medium">
                      {isPhase2 ? "Decompose" : `Iteration ${group.iteration}`}
                    </span>
                    <span className="text-muted-foreground/50">
                      ({group.steps.length} step{group.steps.length !== 1 ? "s" : ""})
                    </span>
                  </button>

                  {/* Steps within iteration */}
                  {isIterExpanded && (
                    <div className="ml-4 space-y-0.5">
                      {group.steps.map((step, si) => {
                        const Icon = getStepIcon(step.label)
                        const isActive = step.status === "active"

                        return (
                          <div key={si}>
                            {/* Step row */}
                            <div
                              className={cn(
                                "flex items-start gap-2 px-2 py-1 text-[11px] rounded",
                                isActive
                                  ? "text-muted-foreground"
                                  : "text-muted-foreground/60"
                              )}
                            >
                              {isActive ? (
                                <Loader2 className="h-3 w-3 animate-spin shrink-0 mt-0.5" />
                              ) : (
                                <Check className="h-3 w-3 shrink-0 mt-0.5 text-green-500/60" />
                              )}
                              <Icon className="h-3 w-3 shrink-0 mt-0.5 opacity-50" />
                              <span className="leading-relaxed">{step.label}</span>
                            </div>

                            {/* Details (indented) */}
                            {step.details && step.details.length > 0 && (
                              <div className="ml-9 space-y-0.5">
                                {step.details.map((d, di) => (
                                  <div
                                    key={di}
                                    className="text-[10px] text-muted-foreground/45 leading-relaxed px-2 py-0.5"
                                  >
                                    {d}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
