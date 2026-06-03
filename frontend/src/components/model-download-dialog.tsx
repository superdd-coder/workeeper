import { useState, useEffect, useCallback, useMemo } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Download, Loader2, Check, AlertCircle, Eye, EyeOff } from "lucide-react"
import { getModelStatus, downloadModels, type ModelStatus } from "@/api/client"
import { toast } from "sonner"

interface BundleDef {
  id: string
  label: string
  description: string
  modelIds: string[]
}

const BUNDLES: BundleDef[] = [
  {
    id: "file",
    label: "File Transcription",
    description: "SenseVoiceSmall + FSMN-VAD + CAM++ Speaker + CT-Punc",
    modelIds: ["transcription", "vad", "speaker", "punc"],
  },
  {
    id: "realtime",
    label: "Real-time Transcription",
    description: "Paraformer Streaming",
    modelIds: ["realtime"],
  },
]

interface ModelDownloadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onComplete: () => void
}

export function ModelDownloadDialog({ open, onOpenChange, onComplete }: ModelDownloadDialogProps) {
  const [models, setModels] = useState<ModelStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [hfToken, setHfToken] = useState("")
  const [showToken, setShowToken] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [selectedBundles, setSelectedBundles] = useState<Set<string>>(new Set())

  const modelMap = useMemo(() => {
    const map = new Map<string, ModelStatus>()
    for (const m of models) map.set(m.id, m)
    return map
  }, [models])

  // Compute selected model IDs from selected bundles (only non-downloaded)
  const selectedModelIds = useMemo(() => {
    const ids = new Set<string>()
    for (const b of BUNDLES) {
      if (selectedBundles.has(b.id)) {
        for (const mid of b.modelIds) {
          const m = modelMap.get(mid)
          if (m && !m.downloaded) ids.add(mid)
        }
      }
    }
    return ids
  }, [selectedBundles, modelMap])

  const bundleStates = useMemo(() => {
    return BUNDLES.map((b) => {
      const memberModels = b.modelIds.map((mid) => modelMap.get(mid)).filter(Boolean) as ModelStatus[]
      const allDone = memberModels.length > 0 && memberModels.every((m) => m.downloaded)
      const anyDownloading = memberModels.some((m) => m.status === "downloading")
      const anyError = memberModels.some((m) => m.status === "error")
      const totalSize = memberModels.reduce((sum, m) => sum + m.size_mb, 0)
      return { bundle: b, memberModels, allDone, anyDownloading, anyError, totalSize }
    })
  }, [modelMap])

  const allBundlesDone = bundleStates.every((b) => b.allDone)
  const isDownloading = models.some((m) => m.status === "downloading")
  const hasError = models.some((m) => m.status === "error")

  const fetchStatus = useCallback(async () => {
    try {
      const status = await getModelStatus()
      setModels(status)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      setLoading(true)
      setDownloading(false)
      fetchStatus().then(() => {
        // After loading, auto-select bundles with missing models
        setSelectedBundles(() => {
          const toSelect = new Set<string>()
          for (const b of BUNDLES) {
            const hasMissing = b.modelIds.some((mid) => {
              const m = modelMap.get(mid)
              return m && !m.downloaded
            })
            if (hasMissing) toSelect.add(b.id)
          }
          return toSelect
        })
      })
    }
  }, [open, fetchStatus])

  // Poll progress while downloading
  useEffect(() => {
    if (!downloading) return
    const interval = setInterval(async () => {
      try {
        const status = await getModelStatus()
        setModels(status)
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(interval)
  }, [downloading])

  // Auto-detect download completion and refresh
  useEffect(() => {
    if (!downloading || models.length === 0) return
    const stillActive = models.some((m) => m.status === "downloading")
    if (!stillActive) {
      setDownloading(false)
      // Refresh to get final state
      fetchStatus()
      const allDone = BUNDLES.every((b) =>
        b.modelIds.every((mid) => {
          const m = modelMap.get(mid)
          return m?.downloaded
        })
      )
      if (allDone) {
        toast.success("All models downloaded!")
      }
    }
  }, [models, downloading, modelMap, fetchStatus])

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const ids = Array.from(selectedModelIds)
      await downloadModels(hfToken || undefined, ids.length > 0 ? ids : undefined)
      toast.info("Download started...")
    } catch {
      toast.error("Failed to start download")
      setDownloading(false)
    }
  }

  const toggleBundle = (bundleId: string) => {
    setSelectedBundles((prev) => {
      const next = new Set(prev)
      if (next.has(bundleId)) next.delete(bundleId)
      else next.add(bundleId)
      return next
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="h-5 w-5" />
            Download Local Models
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : allBundlesDone ? (
          <div className="text-center py-6 space-y-3">
            <Check className="h-8 w-8 mx-auto text-green-500" />
            <p className="text-sm text-muted-foreground">All models are downloaded and ready.</p>
            <Button onClick={() => { onComplete(); onOpenChange(false) }}>Done</Button>
          </div>
        ) : (
          <div className="space-y-4">
            {/* HF Token */}
            <div>
              <label className="text-sm font-medium">HuggingFace Token (optional)</label>
              <p className="text-xs text-muted-foreground mb-1.5">
                Some models require authentication. Get yours at huggingface.co/settings/tokens
              </p>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    type={showToken ? "text" : "password"}
                    value={hfToken}
                    onChange={(e) => setHfToken(e.target.value)}
                    placeholder="hf_xxxxx"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                    onClick={() => setShowToken(!showToken)}
                  >
                    {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            </div>

            {/* Bundle list */}
            <div className="space-y-3">
              <label className="text-sm font-medium">Transcription Models</label>
              {bundleStates.map(({ bundle, memberModels, allDone, anyDownloading, anyError, totalSize }) => (
                <div
                  key={bundle.id}
                  className={`rounded-md border p-3 ${allDone ? "border-green-200 bg-green-50/30" : "border-border"}`}
                >
                  <div className="flex items-center gap-3">
                    {!allDone && (
                      <input
                        type="checkbox"
                        checked={selectedBundles.has(bundle.id)}
                        disabled={isDownloading}
                        onChange={() => toggleBundle(bundle.id)}
                        className="rounded"
                      />
                    )}
                    {allDone && <Check className="h-4 w-4 text-green-500 shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{bundle.label}</span>
                        {anyDownloading && (
                          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        )}
                        {anyError && (
                          <AlertCircle className="h-4 w-4 text-destructive" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {totalSize >= 1000 ? `${(totalSize / 1000).toFixed(1)}GB` : `${totalSize}MB`} · {bundle.description}
                      </p>
                    </div>
                  </div>

                  {/* Sub-models */}
                  <div className="mt-2 ml-8 space-y-0.5">
                    {memberModels.map((m) => (
                      <div key={m.id} className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="truncate">{m.display_name}</span>
                        <span>·</span>
                        <span className="shrink-0">{m.size_mb}MB</span>
                        {m.downloaded && <Check className="h-3 w-3 text-green-500 shrink-0" />}
                        {m.status === "downloading" && (
                          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground shrink-0" />
                        )}
                        {m.status === "error" && (
                          <span className="text-destructive shrink-0">{m.message}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Error message */}
            {hasError && (
              <div className="text-xs text-destructive p-2 rounded bg-destructive/10">
                {models
                  .filter((m) => m.status === "error")
                  .map((m) => (
                    <p key={m.id}>{m.display_name}: {m.message}</p>
                  ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              {!isDownloading && (
                <Button variant="outline" onClick={() => { onComplete(); onOpenChange(false) }}>
                  Skip
                </Button>
              )}
              <Button
                onClick={handleDownload}
                disabled={selectedModelIds.size === 0 || isDownloading}
                className="flex-1"
              >
                {isDownloading ? (
                  <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Downloading...</>
                ) : (
                  <><Download className="h-4 w-4 mr-2" />Download ({selectedBundles.size})</>
                )}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
