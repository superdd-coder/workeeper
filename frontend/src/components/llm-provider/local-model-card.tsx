import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
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

  const statusColor = status === "ready" ? "bg-green-500" : status === "error" ? "bg-red-500" : "bg-gray-400"

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
          <Badge variant="outline" className="text-xs border-blue-300 text-blue-700 bg-blue-50 dark:border-blue-700 dark:text-blue-300 dark:bg-blue-900/30">
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />Loading...
          </Badge>
        )
      case "loaded":
        return (
          <Badge className="text-xs bg-green-100 text-green-700 hover:bg-green-100 dark:bg-green-900/30 dark:text-green-400">
            Loaded
          </Badge>
        )
      case "error":
        return (
          <Badge variant="outline" className="text-xs border-red-300 text-red-700 bg-red-50 dark:border-red-700 dark:text-red-300 dark:bg-red-900/30">
            Error
          </Badge>
        )
      default:
        return (
          <Badge variant="outline" className="text-xs">
            Unloaded
          </Badge>
        )
    }
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{name}</span>
              <div className={`h-2 w-2 rounded-full ${statusColor}`} />
            </div>
            <p className="text-sm text-muted-foreground">{model}</p>
          </div>
          <div className="flex items-center gap-2">
            {isDefault && (
              <Badge className="text-xs bg-green-100 text-green-700 hover:bg-green-100 dark:bg-green-900/30 dark:text-green-400"><Star className="h-3 w-3 mr-1" />Default</Badge>
            )}
            {loadBadge()}
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <Button variant="outline" size="sm" onClick={handleTest} disabled={testing || !isLoaded}>
            {testing ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Plug className="h-3 w-3 mr-1" />}
            Test
          </Button>
          <Button variant="outline" size="sm" onClick={onSetDefault} disabled={isDefault || !isLoaded || !isDownloaded}>
            <Star className="h-3 w-3 mr-1" />Default
          </Button>
          {isDownloaded ? (
            <Button
              variant={isLoaded ? "outline" : "default"}
              size="sm"
              onClick={handleToggle}
              disabled={toggling || isLoading}
            >
              {toggling || isLoading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Power className="h-3 w-3 mr-1" />}
              {isLoaded ? "Unload" : "Load"}
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={onDownload}>
              <Download className="h-3 w-3 mr-1" />Download first
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
