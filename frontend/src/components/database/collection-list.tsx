import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Plus, Trash2, Pencil } from "lucide-react"
import { cn } from "@/lib/utils"
import type { CollectionItem } from "@/stores/app-store"

interface CollectionListProps {
  collections: CollectionItem[]
  activeCollection: string  // Now stores ID
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
  onRename: (id: string) => void
}

export function CollectionList({ collections, activeCollection, onSelect, onCreate, onDelete, onRename }: CollectionListProps) {
  return (
    <div className="w-56 border-r border-border bg-sidebar-background flex flex-col shrink-0">
      <div className="flex items-center justify-between p-3 border-b border-border">
        <span className="text-sm font-medium">Collections</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onCreate}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {collections.map((col) => (
            <div
              key={col.id}
              className={cn(
                "group flex items-center gap-2 px-3 py-2 rounded-lg text-sm cursor-pointer hover:bg-accent transition-colors",
                activeCollection === col.id && "bg-accent font-medium"
              )}
              onClick={() => onSelect(col.id)}
            >
              <span className="flex-1 truncate">{col.name}</span>
              {col.points_count > 0 && (
                <span className="text-xs text-muted-foreground">{col.points_count}</span>
              )}
              <button
                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground"
                onClick={(e) => { e.stopPropagation(); onRename(col.id) }}
              >
                <Pencil className="h-3 w-3" />
              </button>
              <button
                className="opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive"
                onClick={(e) => { e.stopPropagation(); onDelete(col.id) }}
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
