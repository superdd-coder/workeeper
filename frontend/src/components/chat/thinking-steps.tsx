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
  const [topExpanded, setTopExpanded] = useState(true)
  const [expandedIters, setExpandedIters] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (!isStreaming) {
      setTopExpanded(false)
      return
    }
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
    <div
      className="mt-5 pt-3.5 border-t border-t border-dashed border-border"
    >
      {/* Meta info */}
      {metaInfo && (metaInfo.provider || metaInfo.model) && (
        <div
          className="flex items-center gap-2 text-[10px] mb-2 flex-wrap text-muted-foreground"
        >
          {metaInfo.provider && metaInfo.model && (
            <span>{metaInfo.provider} / {metaInfo.model}</span>
          )}
          {metaInfo.search_mode && (
            <>
              <span style={{ opacity: 0.3 }}>·</span>
              <span>{metaInfo.search_mode}</span>
            </>
          )}
          {metaInfo.mode && (
            <>
              <span style={{ opacity: 0.3 }}>·</span>
              <span>{metaInfo.mode === "agentic" ? "Agentic RAG" : metaInfo.mode}</span>
            </>
          )}
        </div>
      )}

      {/* Toggle */}
      <button
        type="button"
        onClick={() => setTopExpanded(!topExpanded)}
        className="flex items-center gap-1.5 mb-2 cursor-pointer"
      >
        {isStreaming ? (
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
        ) : topExpanded ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
        )}
        <span
          className="text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground"
        >
          {isStreaming ? "Reasoning" : `Steps · ${totalSteps}`}
        </span>
      </button>

      {/* Steps */}
      {topExpanded && (
        <div>
          {steps.map((group) => {
            const isIterExpanded = expandedIters.has(group.iteration)
            const isPhase2 = group.iteration === 0

            return (
              <div key={group.iteration}>
                <button
                  type="button"
                  onClick={() => toggleIter(group.iteration)}
                  className="flex items-center gap-1.5 py-0.5 cursor-pointer w-full text-left"
                >
                  {isIterExpanded ? (
                    <ChevronDown className="h-2.5 w-2.5 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-2.5 w-2.5 text-muted-foreground" />
                  )}
                  <span
                    className="text-[10px] font-medium text-foreground"
                  >
                    {isPhase2 ? "Decompose" : `Iteration ${group.iteration}`}
                  </span>
                  <span className="text-[10px] text-muted-foreground" style={{ opacity: 0.5 }}>
                    ({group.steps.length})
                  </span>
                </button>

                {isIterExpanded && (
                  <div className="ml-4">
                    {group.steps.map((step, si) => {
                      const Icon = getStepIcon(step.label)
                      const isActive = step.status === "active"

                      return (
                        <div key={si}>
                          <div
                            className={`flex items-center gap-2 py-0.5 text-[11px] ${isActive ? "text-foreground" : "text-muted-foreground"}`}
                          >
                            {isActive ? (
                              <Loader2 className="h-3 w-3 animate-spin shrink-0 text-primary" />
                            ) : (
                              <Check className="h-3 w-3 shrink-0 text-primary" style={{ opacity: 0.6 }} />
                            )}
                            <Icon className="h-3 w-3 shrink-0 opacity-40" />
                            <span>{step.label}</span>
                          </div>

                          {step.details && step.details.length > 0 && (
                            <div className="ml-7">
                              {step.details.map((d, di) => (
                                <div
                                  key={di}
                                  className="text-[10px] leading-relaxed py-0.5 text-muted-foreground"
                                  style={{ opacity: 0.5 }}
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
  )
}
