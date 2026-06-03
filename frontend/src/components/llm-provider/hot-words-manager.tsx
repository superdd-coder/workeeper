import { useState, useEffect, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Plus, Trash2, BookOpen, Save } from "lucide-react"
import {
  getHotWordsLibraries, getHotWordsLibrary, createHotWordsLibrary,
  updateHotWordsLibrary, deleteHotWordsLibrary,
  type HotWordsLibrary, type HotWordsLibrarySummary, type HotWordItem,
} from "@/api/client"
import { toast } from "sonner"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function HotWordsManager({ open, onOpenChange }: Props) {
  const [libraries, setLibraries] = useState<HotWordsLibrarySummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedLib, setSelectedLib] = useState<HotWordsLibrary | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const fetchList = useCallback(async () => {
    try {
      setLibraries(await getHotWordsLibraries())
    } catch { /* ignore */ }
  }, [])

  const fetchLibrary = useCallback(async (id: string) => {
    try {
      const lib = await getHotWordsLibrary(id)
      setSelectedLib(lib)
      setIsDirty(false)
    } catch { toast.error("Failed to load library") }
  }, [])

  useEffect(() => {
    if (open) fetchList()
  }, [open, fetchList])

  useEffect(() => {
    if (selectedId) fetchLibrary(selectedId)
    else setSelectedLib(null)
  }, [selectedId, fetchLibrary])

  const handleNew = async () => {
    try {
      const lib = await createHotWordsLibrary({ name: "New Library" })
      await fetchList()
      setSelectedId(lib.id)
    } catch { toast.error("Failed to create library") }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteHotWordsLibrary(id)
      if (selectedId === id) { setSelectedId(null); setSelectedLib(null) }
      setDeleteConfirmId(null)
      await fetchList()
      toast.success("Library deleted")
    } catch { toast.error("Failed to delete") }
  }

  const handleSave = async () => {
    if (!selectedId || !selectedLib) return
    setIsSaving(true)
    try {
      const updated = await updateHotWordsLibrary(selectedId, {
        name: selectedLib.name,
        description: selectedLib.description,
        words: selectedLib.words,
      })
      setSelectedLib(updated)
      setIsDirty(false)
      toast.success("Saved")
      await fetchList()
    } catch { toast.error("Failed to save") }
    finally { setIsSaving(false) }
  }

  const updateField = (field: "name" | "description", value: string) => {
    if (!selectedLib) return
    setSelectedLib({ ...selectedLib, [field]: value })
    setIsDirty(true)
  }

  const updateWord = (index: number, field: keyof HotWordItem, value: string | number) => {
    if (!selectedLib) return
    const words = [...selectedLib.words]
    words[index] = { ...words[index], [field]: value }
    setSelectedLib({ ...selectedLib, words })
    setIsDirty(true)
  }

  const addWord = () => {
    if (!selectedLib) return
    setSelectedLib({
      ...selectedLib,
      words: [...selectedLib.words, { text: "", weight: 4, lang: "" }],
    })
    setIsDirty(true)
  }

  const removeWord = (index: number) => {
    if (!selectedLib) return
    const words = selectedLib.words.filter((_, i) => i !== index)
    setSelectedLib({ ...selectedLib, words })
    setIsDirty(true)
  }

  const handleSwitchLibrary = (id: string) => {
    if (isDirty && selectedId && selectedId !== id) {
      if (!confirm("You have unsaved changes. Discard them?")) return
    }
    setSelectedId(id)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-6xl h-[80vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-0 shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Hot Words Management
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-1 min-h-0 px-6 pb-6 pt-4 gap-4">
          {/* Left panel: library list */}
          <div className="w-56 shrink-0 flex flex-col border border-border rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-muted/50">
              <span className="text-sm font-medium">Libraries</span>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleNew} title="New library">
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-1">
                {libraries.map((lib) => (
                  <div
                    key={lib.id}
                    className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-sm ${
                      selectedId === lib.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted"
                    }`}
                    onClick={() => handleSwitchLibrary(lib.id)}
                  >
                    <div className="truncate flex-1 min-w-0">
                      <div className="truncate">{lib.name}</div>
                      <div className="text-xs text-muted-foreground">{lib.word_count} words</div>
                    </div>
                    {deleteConfirmId === lib.id ? (
                      <div className="flex items-center gap-1 shrink-0 ml-1">
                        <Button
                          variant="ghost" size="icon"
                          className="h-5 w-5 text-destructive"
                          onClick={(e) => { e.stopPropagation(); handleDelete(lib.id) }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost" size="icon"
                          className="h-5 w-5"
                          onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(null) }}
                        >
                          ×
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="ghost" size="icon"
                        className="h-5 w-5 opacity-0 group-hover:opacity-100 shrink-0 ml-1"
                        style={{ opacity: undefined }}
                        onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(lib.id) }}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                ))}
                {libraries.length === 0 && (
                  <p className="text-xs text-muted-foreground p-2 text-center">
                    No libraries yet. Click + to create one.
                  </p>
                )}
              </div>
            </ScrollArea>
          </div>

          {/* Right panel: library details */}
          <div className="flex-1 min-w-0 flex flex-col border border-border rounded-lg overflow-hidden">
            {selectedLib ? (
              <>
                <div className="px-4 py-3 border-b border-border space-y-3 shrink-0">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Name</label>
                    <Input
                      value={selectedLib.name}
                      onChange={(e) => updateField("name", e.target.value)}
                      className="h-8 mt-1"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Description</label>
                    <Textarea
                      value={selectedLib.description}
                      onChange={(e) => updateField("description", e.target.value)}
                      className="h-16 mt-1 resize-none"
                    />
                  </div>
                </div>

                {/* Word list */}
                <div className="flex-1 min-h-0 flex flex-col">
                  <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted/30 shrink-0">
                    <span className="text-sm font-medium">
                      Words ({selectedLib.words.length})
                    </span>
                    <Button variant="outline" size="sm" onClick={addWord}>
                      <Plus className="h-3 w-3 mr-1" /> Add Word
                    </Button>
                  </div>
                  <ScrollArea className="flex-1">
                    <div className="divide-y divide-border">
                      {selectedLib.words.map((word, i) => (
                        <div key={i} className="flex items-center gap-2 px-4 py-2">
                          <Input
                            value={word.text}
                            onChange={(e) => updateWord(i, "text", e.target.value)}
                            placeholder="Hot word"
                            className="h-8 flex-1 min-w-0"
                          />
                          <div className="flex items-center gap-1 shrink-0">
                            <label className="text-xs text-muted-foreground">W:</label>
                            <Input
                              type="number"
                              min={1} max={10}
                              value={isNaN(word.weight) ? "" : word.weight}
                              onChange={(e) => {
                                const v = e.target.value
                                if (v === "") { updateWord(i, "weight", NaN); return }
                                const n = parseInt(v)
                                if (!isNaN(n)) updateWord(i, "weight", Math.max(1, Math.min(10, n)))
                              }}
                              onBlur={() => {
                                if (isNaN(word.weight)) updateWord(i, "weight", 4)
                              }}
                              className="h-8 w-14 text-center"
                            />
                          </div>
                          <Input
                            value={word.lang || ""}
                            onChange={(e) => updateWord(i, "lang", e.target.value)}
                            placeholder="lang"
                            className="h-8 w-16"
                          />
                          <Button
                            variant="ghost" size="icon"
                            className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
                            onClick={() => removeWord(i)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ))}
                      {selectedLib.words.length === 0 && (
                        <p className="text-xs text-muted-foreground p-4 text-center">
                          No words. Click "Add Word" to add one.
                        </p>
                      )}
                    </div>
                  </ScrollArea>
                </div>

                {/* Save bar */}
                <div className="flex items-center justify-between px-4 py-2 border-t border-border bg-muted/30 shrink-0">
                  <span className="text-xs text-muted-foreground">
                    {isDirty ? "Unsaved changes" : "Saved"}
                  </span>
                  <Button size="sm" onClick={handleSave} disabled={!isDirty || isSaving}>
                    <Save className="h-3.5 w-3.5 mr-1" />
                    {isSaving ? "Saving..." : "Save"}
                  </Button>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                  <BookOpen className="h-10 w-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">Select a library or create one</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
