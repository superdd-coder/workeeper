import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Star, Plug, Loader2, Power, Download } from "lucide-react"
import { toast } from "sonner"

export type LoadState = "unloaded" | "loading" | "loaded" | "error"

interface LocalModelCardProps {
  id: string
  name: string
  model: string
  isDefault: boolean
  loadState: LoadState
  isDownloaded: boolean
  onTest: () => Promise<{ success: boolean; message?: string; error?: string }>
  onSetDefault: () => Promise<void>
  onToggleLoad: () => Promise<void>
  onDownload: () => void
}

export function LocalModelCard({
  name,
  model,
  isDefault,
  loadState,
  isDownloaded,
  onTest,
  onSetDefault,
  onToggleLoad,
  onDownload,
}: LocalModelCardProps) {
  const [testing, setTesting] = useState(false)
  const [status, setStatus] = useState<"unknown" | "ready" | "error">("unknown")
  const [toggling, setToggling] = useState(false)

  const statusColor = status === "ready" ? "bg-emerald-500" : status === "error" ? "bg-red-500" : "bg-muted-foreground/40"

  const isLoaded = loadState === "loaded"
  const isLoading = loadState === "loading"

  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await onTest()
      setStatus(res.success ? "ready" : "error")
      if (res.success) toast.success(res.message || "Test passed")
      else toast.error(res.error || "Test failed")
    } catch {
      setStatus("error")
      toast.error("Test failed")
    } finally {
      setTesting(false)
    }
  }

  const handleToggle = async () => {
    setToggling(true)
    try {
      await onToggleLoad()
      toast.success(isLoaded ? "Unloaded" : "Loading...")
    } catch {
      toast.error("Failed")
    } finally {
      setToggling(false)
    }
  }

  const loadBadge = () => {
    switch (loadState) {
      case "loading":
        return (
          <Badge variant="outline" className="text-[10px] font-medium uppercase tracking-[0.1em] border-indigo-300 text-indigo-700 bg-indigo-50 dark:border-indigo-700 dark:text-indigo-300 dark:bg-indigo-900/30">
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />Loading...
          </Badge>
        )
      case "loaded":
        return (
          <Badge className="text-[10px] font-medium uppercase tracking-[0.1em] bg-emerald-50 text-emerald-700 hover:bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-400">
            Loaded
          </Badge>
        )
      case "error":
        return (
          <Badge variant="outline" className="text-[10px] font-medium uppercase tracking-[0.1em] border-red-300 text-red-700 bg-red-50 dark:border-red-700 dark:text-red-300 dark:bg-red-900/30">
            Error
          </Badge>
        )
      default:
        return (
          <Badge variant="outline" className="text-[10px] font-medium uppercase tracking-[0.1em]">
            Unloaded
          </Badge>
        )
    }
  }

  return (
    <div className="border border-border/50 rounded-lg p-4 flex flex-col h-full">
      {/* Row 1: Name + status + badges */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-[350] uppercase tracking-[0.08em] text-muted-foreground">{name}</span>
          <div className={`h-2 w-2 rounded-full shrink-0 ${statusColor}`} />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isDefault && (
            <Badge className="text-[10px] font-medium uppercase tracking-[0.1em] bg-emerald-50 text-emerald-700 hover:bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-400"><Star className="h-3 w-3 mr-1" />Default</Badge>
          )}
          {loadBadge()}
        </div>
      </div>

      {/* Row 2: Model */}
      <div className="mt-1 min-h-[1.25rem]">
        <p className="font-normal text-[12px] text-muted-foreground/80">{model}</p>
      </div>

      {/* Row 3: URL (reserved for uniform height) */}
      <div className="min-h-[1rem]" />

      {/* Row 4: Buttons */}
      <div className="flex gap-2 mt-auto pt-3">
        <Button variant="outline" size="sm" onClick={handleTest} disabled={testing || !isLoaded} className="font-medium uppercase tracking-[0.1em] text-[10px]">
          {testing ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Plug className="h-3 w-3 mr-1" />}
          Test
        </Button>
        <Button variant="outline" size="sm" onClick={onSetDefault} disabled={isDefault || !isLoaded || !isDownloaded} className="font-medium uppercase tracking-[0.1em] text-[10px]">
          <Star className="h-3 w-3 mr-1" />Default
        </Button>
        {isDownloaded ? (
          <Button
            variant={isLoaded ? "outline" : "default"}
            size="sm"
            onClick={handleToggle}
            disabled={toggling || isLoading}
            className="font-medium uppercase tracking-[0.1em] text-[10px]"
          >
            {toggling || isLoading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Power className="h-3 w-3 mr-1" />}
            {isLoaded ? "Unload" : "Load"}
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={onDownload} className="font-medium uppercase tracking-[0.1em] text-[10px]">
            <Download className="h-3 w-3 mr-1" />Download first
          </Button>
        )}
      </div>
    </div>
  )
}
