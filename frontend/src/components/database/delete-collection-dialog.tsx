import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { deleteCollection } from "@/api/client"
import { toast } from "sonner"

interface DeleteCollectionDialogProps {
  name: string | null
  onOpenChange: (open: boolean) => void
  onDeleted: () => void
}

export function DeleteCollectionDialog({ name, onOpenChange, onDeleted }: DeleteCollectionDialogProps) {
  const [confirmName, setConfirmName] = useState("")
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    if (!name || confirmName !== name) return
    setDeleting(true)
    try {
      const res = await deleteCollection(name)
      if (res.error) toast.error(res.error)
      else {
        toast.success(res.message || "Project deleted")
        setConfirmName("")
        onDeleted()
      }
    } catch (err) {
      toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog open={!!name} onOpenChange={(v) => { if (!v) { setConfirmName(""); onOpenChange(false) } }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Project</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <p className="text-sm text-muted-foreground">
            Type <span className="font-mono font-medium text-foreground">{name}</span> to confirm deletion.
          </p>
          <Input
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            placeholder="Type database name"
          />
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => { setConfirmName(""); onOpenChange(false) }}>Cancel</Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={confirmName !== name || deleting}
          >
            {deleting ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
