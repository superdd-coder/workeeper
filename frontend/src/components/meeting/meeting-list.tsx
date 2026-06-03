import { ScrollArea } from "@/components/ui/scroll-area"
import { Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { CreateMeetingButton } from "./create-meeting-dialog"
import type { Meeting } from "@/api/client"

interface MeetingListProps {
  meetings: Meeting[]
  activeMeeting: string | null
  onSelect: (id: string) => void
  onCreated: (meetingId: string) => void
  onDelete: (id: string) => void
}

export function MeetingList({ meetings, activeMeeting, onSelect, onCreated, onDelete }: MeetingListProps) {
  return (
    <div className="w-64 border-r border-border bg-sidebar-background flex flex-col shrink-0">
      <div className="flex items-center justify-between p-3 border-b border-border">
        <span className="text-sm font-medium">Meetings</span>
        <CreateMeetingButton onCreated={onCreated} />
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {meetings.map((m) => (
            <div
              key={m.id}
              className={cn(
                "group flex items-start gap-2 px-3 py-2 rounded-lg text-sm cursor-pointer hover:bg-accent transition-colors",
                activeMeeting === m.id && "bg-accent font-medium"
              )}
              onClick={() => onSelect(m.id)}
            >
              <span className="flex-1 line-clamp-2 break-words leading-snug">{m.title}</span>
              <button
                className="opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive"
                onClick={(e) => { e.stopPropagation(); onDelete(m.id) }}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          {meetings.length === 0 && (
            <p className="text-xs text-muted-foreground px-3 py-4 text-center">No meetings yet</p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

