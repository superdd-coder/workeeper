import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Plus, Loader2 } from "lucide-react"
import { createMeeting } from "@/api/client"
import { toast } from "sonner"

interface CreateMeetingButtonProps {
  onCreated: (meetingId: string) => void
}

export function CreateMeetingButton({ onCreated }: CreateMeetingButtonProps) {
  const [creating, setCreating] = useState(false)

  const handleCreate = async () => {
    setCreating(true)
    try {
      const title = new Date().toLocaleString("zh-CN", {
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
      }).replace(/\//g, "-")
      const meeting = await createMeeting(title)
      toast.success("Meeting created")
      onCreated(meeting.id)
    } catch (err) {
      toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setCreating(false)
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-6 w-6"
      onClick={handleCreate}
      disabled={creating}
    >
      {creating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
    </Button>
  )
}
