import { useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Upload, RotateCw, CheckCircle2, XCircle, Clock, Loader2, StopCircle, RefreshCw } from "lucide-react"
import { type TaskInfo } from "@/api/client"

interface UploadSectionProps {
  hasActiveTasks: boolean
  tasks: TaskInfo[]
  allowedFileTypes?: string[]
  onUpload: (files: FileList | null) => void
  onClearCompleted: () => Promise<{ message: string }>
  onRefreshTasks: () => void
  onCancelTask?: (taskId: string) => void
  onRetryTask?: (taskId: string) => void
}

function TaskStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Clock className="h-4 w-4 text-muted-foreground" />
    case "processing":
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500" />
    default:
      return null
  }
}

const ALL_FILE_TYPES = ["pdf", "txt", "md", "docx", "xlsx", "pptx", "csv"]

export function UploadSection({ hasActiveTasks, tasks, allowedFileTypes, onUpload, onClearCompleted, onRefreshTasks, onCancelTask, onRetryTask }: UploadSectionProps) {
  const fileRef = useRef<HTMLInputElement>(null)

  const effectiveTypes = allowedFileTypes && allowedFileTypes.length > 0 ? allowedFileTypes : ALL_FILE_TYPES
  const acceptAttr = effectiveTypes.map(t => `.${t}`).join(",")
  const typesLabel = effectiveTypes.map(t => t.toUpperCase()).join(", ")

  const handleClearCompleted = async () => {
    try {
      await onClearCompleted()
      onRefreshTasks()
    } catch {
      // ignore
    }
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Upload className="h-4 w-4" />
            Upload Files
          </CardTitle>
        </CardHeader>
        <CardContent>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={acceptAttr}
            className="hidden"
            onChange={(e) => { onUpload(e.target.files); if (fileRef.current) fileRef.current.value = "" }}
          />
          <div
            className="border-2 border-dashed border-border rounded-lg p-4 text-center cursor-pointer hover:border-primary/50 transition-colors"
            onClick={() => fileRef.current?.click()}
            onDrop={(e) => { e.preventDefault(); onUpload(e.dataTransfer.files) }}
            onDragOver={(e) => e.preventDefault()}
          >
            <Upload className="h-5 w-5 mx-auto mb-1 text-muted-foreground" />
            <p className="text-sm font-medium">
              {hasActiveTasks ? "Processing... Upload more" : "Click or drag files here"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">{typesLabel}</p>
          </div>
        </CardContent>
      </Card>

      {tasks.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <RotateCw className="h-4 w-4" />
                Upload Queue
                {hasActiveTasks && (
                  <Badge variant="secondary" className="ml-2">
                    {tasks.filter((t) => t.status === "processing").length} processing
                  </Badge>
                )}
              </CardTitle>
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearCompleted}
                disabled={!tasks.some((t) => t.status === "completed" || t.status === "failed")}
              >
                Clear Completed
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {tasks.map((task) => (
                <div key={task.id} className="space-y-2">
                  <div className="flex items-center gap-3">
                    <TaskStatusIcon status={task.status} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{task.filename}</p>
                      <p className="text-xs text-muted-foreground">{task.message}</p>
                    </div>
                    {task.status === "completed" && task.result && (
                      <Badge variant="outline" className="text-xs shrink-0">
                        {task.result.chunks_count} chunks
                      </Badge>
                    )}
                    {task.status === "processing" && onCancelTask && (
                      <Button
                        variant="ghost" size="icon" className="h-7 w-7 shrink-0"
                        onClick={() => onCancelTask(task.id)}
                        title="Stop processing"
                      >
                        <StopCircle className="h-4 w-4 text-red-500" />
                      </Button>
                    )}
                    {task.status === "failed" && onRetryTask && (
                      <Button
                        variant="ghost" size="icon" className="h-7 w-7 shrink-0"
                        onClick={() => onRetryTask(task.id)}
                        title="Retry"
                      >
                        <RefreshCw className="h-4 w-4 text-blue-500" />
                      </Button>
                    )}
                  </div>
                  {task.status === "processing" && (
                    <Progress value={task.progress} className="h-1" />
                  )}
                  {task.status === "failed" && task.error && (
                    <p className="text-xs text-red-500 pl-7">{task.error}</p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
