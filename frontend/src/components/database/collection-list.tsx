import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Plus, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { CollectionInfoItem } from "./database-view"

interface CollectionListProps {
  collections: CollectionInfoItem[]
  activeCollection: string
  onSelect: (name: string) => void
  onCreate: () => void
  onDelete: (name: string) => void
}

export function CollectionList({ collections, activeCollection, onSelect, onCreate, onDelete }: CollectionListProps) {
  return (
    <div className="w-56 border-r border-border bg-sidebar-background flex flex-col shrink-0">
      <div className="flex items-center justify-between p-3 border-b border-border">
        <span className="text-sm font-medium">Databases</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onCreate}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {collections.map((col) => (
            <div
              key={col.name}
              className={cn(
                "group flex items-center gap-2 px-3 py-2 rounded-lg text-sm cursor-pointer hover:bg-accent transition-colors",
                activeCollection === col.name && "bg-accent font-medium"
              )}
              onClick={() => onSelect(col.name)}
            >
              <span className="flex-1 truncate">{col.name}</span>
              {col.points_count > 0 && (
                <span className="text-xs text-muted-foreground">{col.points_count}</span>
              )}
              <button
                className="opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive"
                onClick={(e) => { e.stopPropagation(); onDelete(col.name) }}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
