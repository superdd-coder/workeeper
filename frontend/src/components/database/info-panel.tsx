import { useState, useEffect, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Loader2, FileWarning, BookOpen, Mic, RefreshCw } from "lucide-react"
import { toast } from "sonner"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useAppStore } from "@/stores/app-store"
import {
  getCollectionSummary,
  getProjectDescription,
  getCollectionConflicts,
  triggerConsolidation,
  getMeetingLog,
  getActiveCollectionTasks,
  type ConflictItem,
  type MeetingLogItem,
} from "@/api/client"
import { ConflictViewerDialog } from "./conflict-viewer-dialog"
import { NotesCard } from "./notes-card"

interface InfoPanelProps {
  collection: string
}

export function InfoPanel({ collection }: InfoPanelProps) {
  // Summary state
  const [summary, setSummary] = useState<string | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [consolidating, setConsolidating] = useState(false)
  const [consolidatingCollection, setConsolidatingCollection] = useState<string | null>(null)

  // Project description state
  const [projectDescription, setProjectDescription] = useState<string | null>(null)

  // Conflicts state
  const [conflicts, setConflicts] = useState<ConflictItem[]>([])
  const [conflictsLoading, setConflictsLoading] = useState(false)
  const [selectedConflict, setSelectedConflict] = useState<ConflictItem | null>(null)

  // Meeting log state
  const [meetings, setMeetings] = useState<MeetingLogItem[]>([])
  const [meetingsLoading, setMeetingsLoading] = useState(false)

  const { setSidebarView, setActiveMeeting, setPendingOpenFile } = useAppStore()

  // Reset state when collection changes — but keep consolidating if from active-task check
  useEffect(() => {
    setSummary(null)
    setProjectDescription(null)
    setConflicts([])
    setMeetings([])
    setConsolidating(false)
    setConsolidatingCollection(null)
    setSelectedConflict(null)
    // Check if consolidation is already running for this collection
    getActiveCollectionTasks(collection).then((res) => {
      if (res.consolidating) {
        setConsolidating(true)
        setConsolidatingCollection(collection)
      }
    }).catch((err) => {
      console.warn("Failed to check active tasks:", err)
    })
  }, [collection])

  // Poll for consolidation completion when consolidating state is active
  useEffect(() => {
    if (!consolidating || consolidatingCollection !== collection) return
    const poll = setInterval(async () => {
      try {
        const res = await getActiveCollectionTasks(collection)
        if (!res.consolidating) {
          clearInterval(poll)
          setConsolidating(false)
          setConsolidatingCollection(null)
          // Refresh data
          fetchSummary()
          fetchProjectDescription()
          fetchConflicts()
          fetchMeetings()
        }
      } catch {
        // ignore polling errors
      }
    }, 2000)
    return () => clearInterval(poll)
  }, [consolidating, consolidatingCollection, collection])

  const fetchSummary = useCallback(async () => {
    if (!collection) return
    setSummaryLoading(true)
    try {
      const res = await getCollectionSummary(collection)
      setSummary(res?.content ?? null)
    } catch {
      setSummary(null)
    } finally {
      setSummaryLoading(false)
    }
  }, [collection])

  const fetchConflicts = useCallback(async () => {
    if (!collection) return
    setConflictsLoading(true)
    try {
      const res = await getCollectionConflicts(collection)
      setConflicts(res.conflicts ?? [])
    } catch {
      setConflicts([])
    } finally {
      setConflictsLoading(false)
    }
  }, [collection])

  const fetchMeetings = useCallback(async () => {
    if (!collection) return
    setMeetingsLoading(true)
    try {
      const res = await getMeetingLog(collection)
      setMeetings(res.meetings ?? [])
    } catch {
      setMeetings([])
    } finally {
      setMeetingsLoading(false)
    }
  }, [collection])

  useEffect(() => {
    fetchSummary()
    fetchProjectDescription()
    fetchConflicts()
    fetchMeetings()
  }, [fetchSummary, fetchConflicts, fetchMeetings])

  const fetchProjectDescription = useCallback(async () => {
    if (!collection) return
    try {
      const res = await getProjectDescription(collection)
      setProjectDescription(res?.content ?? null)
    } catch {
      setProjectDescription(null)
    }
  }, [collection])

  const handleConsolidate = async () => {
    setConsolidating(true)
    setConsolidatingCollection(collection)
    try {
      const res = await triggerConsolidation(collection)
      toast.info(`Consolidation started for ${collection}...`)

      // Poll task status until completion
      const taskId = res.task?.id
      const targetCollection = collection // capture for callback
      if (taskId) {
        const poll = setInterval(async () => {
          try {
            const { getTask } = await import("@/api/client")
            const task = await getTask(taskId)
            if (task.status === "completed" || task.status === "failed") {
              clearInterval(poll)
              setConsolidating(false)
              setConsolidatingCollection(null)
              if (task.status === "completed") {
                toast.success(`Consolidation complete for ${targetCollection}`)
                // Only refresh if user is still viewing the same collection
                if (collection === targetCollection) {
                  fetchSummary()
                  fetchProjectDescription()
                  fetchConflicts()
                  fetchMeetings()
                }
              } else {
                toast.error(`Consolidation failed: ${task.error || "unknown error"}`)
              }
            }
          } catch {
            // ignore polling errors
          }
        }, 2000)
      } else {
        setConsolidating(false)
        setConsolidatingCollection(null)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      toast.error(msg || "Consolidation failed")
      setConsolidating(false)
      setConsolidatingCollection(null)
    }
  }

  const handleMeetingClick = (meeting: MeetingLogItem) => {
    setActiveMeeting(meeting.id)
    setSidebarView("meeting")
  }

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="space-y-4">
      {/* Project Description */}
      {consolidating ? (
        <blockquote className="border-l-4 border-primary/30 pl-4 py-1 text-sm text-muted-foreground italic flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
          Updating...
        </blockquote>
      ) : projectDescription && (
        <blockquote className="border-l-4 border-primary/30 pl-4 py-1 text-sm text-muted-foreground italic">
          {projectDescription}
        </blockquote>
      )}

      {/* Summary Section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            Summary
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={handleConsolidate}
            disabled={consolidating && consolidatingCollection === collection}
          >
            {consolidating ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1.5" />
            )}
            Consolidate
          </Button>
        </CardHeader>
        <CardContent>
          {consolidating ? (
            <div className="flex flex-col items-center justify-center py-8 gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <p className="text-sm">Consolidating collection summary...</p>
            </div>
          ) : summaryLoading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading summary...
            </div>
          ) : summary ? (
            <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-pre:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {summary}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No summary yet. Upload files and consolidate.</p>
          )}
        </CardContent>
      </Card>

      {/* Conflicts Section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <FileWarning className="h-4 w-4" />
            Conflicts
          </CardTitle>
        </CardHeader>
        <CardContent>
          {consolidating ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Updating conflicts...
            </div>
          ) : conflictsLoading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading conflicts...
            </div>
          ) : conflicts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No conflicts detected.</p>
          ) : (
            <div className="space-y-2">
              {conflicts.map((conflict, i) => (
                <button
                  key={i}
                  className="w-full text-left border border-border rounded-lg p-3 hover:bg-accent/50 transition-colors"
                  onClick={() => setSelectedConflict(conflict)}
                >
                  <div className="flex items-start gap-2 text-sm">
                    <span className="flex-1 min-w-0">
                      <span className="text-amber-600 dark:text-amber-400">{conflict.content1}</span>
                      <span className="text-muted-foreground"> ({conflict.source1})</span>
                    </span>
                    <span className="text-muted-foreground shrink-0">vs</span>
                    <span className="flex-1 min-w-0">
                      <span className="text-amber-600 dark:text-amber-400">{conflict.content2}</span>
                      <span className="text-muted-foreground"> ({conflict.source2})</span>
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Separator />

      {/* Notes Section */}
      <NotesCard collection={collection} />

      <Separator />

      {/* Meeting Log Section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Mic className="h-4 w-4" />
            Meeting Log
          </CardTitle>
        </CardHeader>
        <CardContent>
          {meetingsLoading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading meetings...
            </div>
          ) : meetings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No meetings linked.</p>
          ) : (
            <div className="space-y-1">
              {meetings.map((meeting) => (
                <div key={meeting.id} className="rounded-lg border border-border p-2">
                  <button
                    className="w-full text-left flex items-center gap-3 hover:bg-accent/50 transition-colors text-sm rounded"
                    onClick={() => handleMeetingClick(meeting)}
                  >
                    <Mic className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="flex-1 truncate font-medium">{meeting.title}</span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {formatDate(meeting.created_at)}
                    </span>
                  </button>
                  {meeting.file_ids && meeting.file_ids.length > 0 && (
                    <div className="ml-7 mt-1 space-y-0.5">
                      {meeting.file_ids.map((fid) => (
                        <button
                          key={fid}
                          className="block text-xs text-muted-foreground hover:text-primary hover:underline truncate w-full text-left"
                          onClick={() => {
                            setPendingOpenFile(fid)
                          }}
                        >
                          {fid}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConflictViewerDialog
        conflict={selectedConflict}
        collection={collection}
        onOpenChange={(v) => !v && setSelectedConflict(null)}
      />
    </div>
  )
}
