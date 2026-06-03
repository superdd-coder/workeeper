import { useState } from "react"
import { ChevronDown, ChevronUp, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Source } from "@/stores/app-store"

interface SourcesCardProps {
  sources: Source[]
}

export function SourcesCard({ sources }: SourcesCardProps) {
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
        <div className="px-3 pb-3 space-y-2">
          {sources.map((s, i) => {
            const source = (s.metadata?.source as string) || ""
            const collection = (s.metadata?.collection as string) || ""
            return (
              <div key={i} className="text-xs border-l-2 border-primary/30 pl-3 py-1">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="font-medium text-foreground">{i + 1}.</span>
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    {(s.score * 100).toFixed(0)}%
                  </Badge>
                  {collection && (
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                      {collection}
                    </Badge>
                  )}
                  {source && (
                    <span className="text-muted-foreground truncate max-w-[200px]" title={source}>
                      {source}
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground leading-relaxed line-clamp-3">{s.text}</p>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
