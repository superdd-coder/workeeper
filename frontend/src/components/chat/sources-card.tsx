import { useState } from "react"
import { ChevronDown, ChevronUp, FileText, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Source } from "@/stores/app-store"

interface SourcesCardProps {
  sources: Source[]
  onSelectSource?: (source: Source) => void
  selectedSourceId?: string | null
}

export function SourcesCard({ sources, onSelectSource, selectedSourceId }: SourcesCardProps) {
  const [expanded, setExpanded] = useState(false)

  if (!sources.length) return null

  return (
    <Card className="mt-3 border-border/50 bg-muted/30">
      <Button
        variant="ghost"
        size="sm"
        className="w-full justify-between px-3 py-2 h-auto text-xs font-medium text-muted-foreground hover:text-foreground"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="flex items-center gap-2">
          <FileText className="h-3.5 w-3.5" />
          Sources ({sources.length})
        </span>
        {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </Button>

      {expanded && (
        <div className="px-3 pb-3 space-y-1.5">
          {[...sources].sort((a, b) => b.score - a.score).map((s, i) => {
            const sourceName = (s.metadata?.source as string) || ""
            const collection = (s.metadata?.collection as string) || ""
            const chunkId = (s.metadata?.id as string) || ""
            const isSelected = selectedSourceId === chunkId

            return (
              <button
                key={chunkId || i}
                type="button"
                onClick={() => onSelectSource?.(s)}
                className={`w-full text-left text-xs border-l-2 pl-3 py-1.5 pr-2 rounded-r transition-colors ${
                  isSelected
                    ? "border-primary bg-primary/5 hover:bg-primary/10"
                    : "border-primary/30 hover:bg-accent/50"
                }`}
                title="Click to view source details"
              >
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="font-medium text-foreground">{i + 1}.</span>
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    {(s.score * 100).toFixed(0)}%
                  </Badge>
                  {collection && (
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                      {collection}
                    </Badge>
                  )}
                  {sourceName && (
                    <span className="text-muted-foreground truncate max-w-[160px]" title={sourceName}>
                      {sourceName}
                    </span>
                  )}
                  {isSelected && <ExternalLink className="h-3 w-3 text-primary shrink-0 ml-auto" />}
                </div>
                <p className="text-muted-foreground leading-relaxed line-clamp-2">{s.text}</p>
              </button>
            )
          })}
        </div>
      )}
    </Card>
  )
}
