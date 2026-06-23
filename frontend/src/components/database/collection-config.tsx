import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Lock } from "lucide-react"
import { getCollectionConfig, updateCollectionConfig, getConfig, getEmbeddingProviders, type EmbeddingProvider } from "@/api/client"
import { useAppStore } from "@/stores/app-store"
import { toast } from "sonner"
import { TooltipLabel } from "@/components/shared/tooltip-label"

interface CollectionConfigProps {
  collection: string
}

export function CollectionConfig({ collection }: CollectionConfigProps) {
  const { providers } = useAppStore()
  const [chunkMode, setChunkMode] = useState("normal")
  const [chunkSize, setChunkSize] = useState("")
  const [chunkOverlap, setChunkOverlap] = useState("")
  const [bufferRatio, setBufferRatio] = useState("")
  const [parentStrategy, setParentStrategy] = useState("paragraph")
  const [parentChunkSize, setParentChunkSize] = useState("")
  const [parentChunkOverlap, setParentChunkOverlap] = useState("")
  const [childChunkSize, setChildChunkSize] = useState("")
  const [childChunkOverlap, setChildChunkOverlap] = useState("")
  const [contextualEnabled, setContextualEnabled] = useState(true)
  const [contextualWindow, setContextualWindow] = useState("1")
  const [embeddingDimensions, setEmbeddingDimensions] = useState("")
  const [embeddingModel, setEmbeddingModel] = useState("")
  const [globalEmbModel, setGlobalEmbModel] = useState("")
  const [embeddingProviderId, setEmbeddingProviderId] = useState("")
  const [embeddingProviders, setEmbeddingProviders] = useState<EmbeddingProvider[]>([])
  const [allowedTypes, setAllowedTypes] = useState<string[]>([])
  const [saving, setSaving] = useState(false)

  const FILE_TYPES = [
    { ext: "pdf", label: "PDF" },
    { ext: "txt", label: "TXT" },
    { ext: "md", label: "Markdown" },
    { ext: "docx", label: "Word" },
    { ext: "xlsx", label: "Excel" },
    { ext: "pptx", label: "PowerPoint" },
    { ext: "csv", label: "CSV" },
  ]

  // Enriching LLM config (stores provider ID)
  const [enrichingLlmProvider, setEnrichingLlmProvider] = useState("")
  const [enrichingLlmModel, setEnrichingLlmModel] = useState("")

  // Cloud parsing (MinerU)
  const [cloudParsing, setCloudParsing] = useState(false)
  const [mineruGloballyEnabled, setMineruGloballyEnabled] = useState(false)

  const readyProviders = providers.filter((p) => p.status === "ready" || !p.status)
  const enrichingProvider = enrichingLlmProvider
    ? readyProviders.find((p) => p.id === enrichingLlmProvider)
    : null
  const enrichingModels = enrichingProvider?.selected_models && enrichingProvider.selected_models.length > 0
    ? enrichingProvider.selected_models
    : enrichingProvider?.model ? [enrichingProvider.model] : []

  useEffect(() => {
    const load = async () => {
      try {
        const cfg = await getCollectionConfig(collection) as Record<string, unknown>
        if (cfg.error) return

        // Fetch global embedding model for dropdown
        try {
          const globalCfg = await getConfig()
          const emb = globalCfg.embedding as Record<string, unknown> | undefined
          if (emb?.model) setGlobalEmbModel(String(emb.model))
          // Check if MinerU is globally enabled
          const mineru = globalCfg.mineru as Record<string, unknown> | undefined
          setMineruGloballyEnabled(!!mineru?.enabled)
        } catch { /* ignore */ }

        // Fetch embedding providers for selector
        try {
          const providers = await getEmbeddingProviders()
          setEmbeddingProviders(providers)
        } catch { /* ignore */ }

        setEmbeddingDimensions(String(cfg.dimensions ?? "1024"))
        setChunkMode(String(cfg.chunk_mode ?? "normal"))
        setChunkSize(String(cfg.chunk_size ?? ""))
        setChunkOverlap(String(cfg.chunk_overlap ?? ""))
        setBufferRatio(String(cfg.buffer_ratio ?? "0.5"))
        setParentStrategy(String(cfg.parent_strategy ?? "paragraph"))
        setParentChunkSize(String(cfg.parent_chunk_size ?? ""))
        setParentChunkOverlap(String(cfg.parent_chunk_overlap ?? ""))
        setChildChunkSize(String(cfg.child_chunk_size ?? ""))
        setChildChunkOverlap(String(cfg.child_chunk_overlap ?? ""))

        setContextualEnabled(Boolean(cfg.contextual_enabled ?? true))
        setContextualWindow(String(cfg.contextual_window ?? 1))
        setEmbeddingModel(String(cfg.embedding_model ?? ""))
        setEmbeddingProviderId(String(cfg.embedding_provider_id ?? ""))

        // Allowed file types
        const aft = cfg.allowed_file_types
        setAllowedTypes(Array.isArray(aft) ? aft.map(String) : [])

        // Enriching LLM config
        setEnrichingLlmProvider(String(cfg.enriching_llm_provider ?? ""))
        setEnrichingLlmModel(String(cfg.enriching_llm_model ?? ""))

        // Cloud parsing
        setCloudParsing(Boolean(cfg.cloud_parsing ?? false))
      } catch {
        // ignore
      }
    }
    load()
  }, [collection])

  const handleSave = async () => {
    setSaving(true)
    try {
      const config: Record<string, unknown> = {}
      if (bufferRatio) config.buffer_ratio = parseFloat(bufferRatio)
      if (chunkMode === "normal") {
        if (chunkSize) config.chunk_size = parseInt(chunkSize)
        if (chunkOverlap) config.chunk_overlap = parseInt(chunkOverlap)
      } else {
        config.parent_strategy = parentStrategy
        if (parentChunkSize) config.parent_chunk_size = parseInt(parentChunkSize)
        if (parentChunkOverlap) config.parent_chunk_overlap = parseInt(parentChunkOverlap)
        if (childChunkSize) config.child_chunk_size = parseInt(childChunkSize)
        if (childChunkOverlap) config.child_chunk_overlap = parseInt(childChunkOverlap)
      }
      config.contextual_enabled = contextualEnabled
      if (contextualWindow) config.contextual_window = parseInt(contextualWindow)
      if (embeddingModel) config.embedding_model = embeddingModel
      config.embedding_provider_id = embeddingProviderId || null

      // Allowed file types (empty array = allow all)
      config.allowed_file_types = allowedTypes

      // Enriching LLM config (always send to allow clearing)
      config.enriching_llm_provider = enrichingLlmProvider || null
      config.enriching_llm_model = enrichingLlmModel || null

      // Cloud parsing
      config.cloud_parsing = cloudParsing

      const res = await updateCollectionConfig(collection, config)
      if (res.error) toast.error(res.error)
      else toast.success(res.message || "Config updated")
    } catch (err) {
      toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dimensions & Mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <TooltipLabel label="Dimensions" tooltip="Vector dimensions for embeddings. This is locked at creation time and cannot be changed." />
              <div className="flex items-center gap-2">
                <Input value={embeddingDimensions} disabled className="flex-1" />
                <Lock className="h-4 w-4 text-muted-foreground" />
              </div>
            </div>
            <div className="space-y-1.5">
              <TooltipLabel label="Chunk Mode" tooltip="Locked at creation time. Cannot be changed after." />
              <div className="flex items-center gap-2">
                <Input value={chunkMode === "parent_child" ? "Parent-Child" : "Normal"} disabled className="flex-1" />
                <Lock className="h-4 w-4 text-muted-foreground" />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chunking</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <TooltipLabel label="Buffer Ratio" tooltip="Controls how aggressively paragraphs are merged. 0.5 = merge until 50% of max_tokens." />
              <Input value={bufferRatio} onChange={(e) => setBufferRatio(e.target.value)} placeholder="0.5" />
            </div>
            {chunkMode === "parent_child" && (
              <div className="space-y-1.5">
                <TooltipLabel label="Parent Strategy" tooltip="How parent chunks are created: paragraph (by paragraphs), fixed_token (by token count), heading (by markdown headings)." />
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={parentStrategy}
                  onChange={(e) => setParentStrategy(e.target.value)}
                >
                  <option value="paragraph">Paragraph</option>
                  <option value="fixed_token">Fixed Token</option>
                  <option value="heading">Heading</option>
                </select>
              </div>
            )}
          </div>
          {chunkMode === "normal" ? (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <TooltipLabel label="Chunk Size" tooltip="Number of tokens per chunk. Larger = more context per chunk, fewer chunks. Smaller = more precise retrieval." />
                <Input value={chunkSize} onChange={(e) => setChunkSize(e.target.value)} placeholder="512" />
              </div>
              <div className="space-y-1.5">
                <TooltipLabel label="Chunk Overlap" tooltip="Number of overlapping tokens between adjacent chunks. Helps maintain context across chunk boundaries." />
                <Input value={chunkOverlap} onChange={(e) => setChunkOverlap(e.target.value)} placeholder="64" />
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <TooltipLabel label="Parent Chunk Size" tooltip="Size of parent chunks in parent-child mode. Parent chunks provide context for child chunks." />
                  <Input value={parentChunkSize} onChange={(e) => setParentChunkSize(e.target.value)} placeholder="1024" />
                </div>
                <div className="space-y-1.5">
                  <TooltipLabel label="Parent Chunk Overlap" tooltip="Overlap between parent chunks for context continuity." />
                  <Input value={parentChunkOverlap} onChange={(e) => setParentChunkOverlap(e.target.value)} placeholder="128" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <TooltipLabel label="Child Chunk Size" tooltip="Size of child chunks used for matching. Smaller = more precise matching." />
                  <Input value={childChunkSize} onChange={(e) => setChildChunkSize(e.target.value)} placeholder="128" />
                </div>
                <div className="space-y-1.5">
                  <TooltipLabel label="Child Chunk Overlap" tooltip="Overlap between child chunks for context continuity." />
                  <Input value={childChunkOverlap} onChange={(e) => setChildChunkOverlap(e.target.value)} placeholder="32" />
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Embedding Model</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <TooltipLabel label="Provider" tooltip="Select an embedding provider for this collection. Configured in Settings > Embedding Models." />
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={embeddingProviderId}
              onChange={(e) => setEmbeddingProviderId(e.target.value)}
            >
              <option value="">Global default{globalEmbModel ? ` (${globalEmbModel})` : ""}</option>
              {embeddingProviders.map((p) => (
                <option key={p.id} value={p.id}>{p.name || p.model}</option>
              ))}
            </select>
          </div>
          {embeddingModel && (
            <div className="space-y-1.5">
              <TooltipLabel label="Model (legacy)" tooltip="Legacy field. Prefer using the Provider selector above." />
              <Input value={embeddingModel} onChange={(e) => setEmbeddingModel(e.target.value)} placeholder="text-embedding-3-small" />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Allowed File Types</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="font-normal text-[12px] text-muted-foreground/80 leading-relaxed">Restrict which file types can be uploaded. Leave empty to allow all.</p>
          <div className="flex flex-wrap gap-2">
            {FILE_TYPES.map((ft) => (
              <label
                key={ft.ext}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs cursor-pointer transition-colors ${
                  allowedTypes.includes(ft.ext) ? "bg-primary text-primary-foreground border-primary" : "bg-background border-input hover:bg-accent"
                }`}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={allowedTypes.includes(ft.ext)}
                  onChange={() =>
                    setAllowedTypes((prev) =>
                      prev.includes(ft.ext) ? prev.filter((t) => t !== ft.ext) : [...prev, ft.ext]
                    )
                  }
                />
                {ft.label}
              </label>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Contextual Enrichment</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center gap-2 text-[14px] font-[350] uppercase tracking-[0.08em] text-muted-foreground cursor-pointer">
            <input type="checkbox" checked={contextualEnabled} onChange={(e) => setContextualEnabled(e.target.checked)} className="rounded" />
            Enable Contextual Enrichment
          </label>
          {contextualEnabled && (
            <>
              <div className="space-y-1.5">
                <TooltipLabel label="Context Window" tooltip="Number of surrounding chunks on EACH SIDE used for context. 1 = previous + next chunk (2 total). 2 = 2 before + 2 after (4 total)." />
                <Input value={contextualWindow} onChange={(e) => setContextualWindow(e.target.value)} placeholder="1" />
              </div>
              <Separator />
              <p className="font-normal text-[12px] text-muted-foreground/80 leading-relaxed">
                Contextual enrichment generates background information for each chunk using an LLM, improving retrieval quality.
              </p>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Enriching LLM</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="font-normal text-[12px] text-muted-foreground/80 leading-relaxed mb-2">
            LLM used for contextual enrichment during document ingestion. Leave empty to use the global default.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[14px] font-[350] uppercase tracking-[0.08em] text-muted-foreground">Provider</label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={enrichingLlmProvider}
                onChange={(e) => {
                  setEnrichingLlmProvider(e.target.value)
                  const prov = readyProviders.find((p) => p.id === e.target.value)
                  const defaultM = prov?.default_model || prov?.selected_models?.[0] || prov?.model || ""
                  setEnrichingLlmModel(defaultM)
                }}
              >
                <option value="">Global default</option>
                {readyProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.name || p.model}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-[14px] font-[350] uppercase tracking-[0.08em] text-muted-foreground">Model</label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={enrichingLlmModel}
                onChange={(e) => setEnrichingLlmModel(e.target.value)}
                disabled={!enrichingLlmProvider}
              >
                <option value="">Select model</option>
                {enrichingModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {mineruGloballyEnabled && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cloud Parsing (MinerU)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="font-normal text-[12px] text-muted-foreground/80 leading-relaxed">
              Use MinerU cloud API for document parsing. Produces higher quality Markdown output with better table, formula, and layout preservation.
              Configure MinerU API token in Settings.
            </p>
            <label className="flex items-center gap-2 text-[14px] font-[350] uppercase tracking-[0.08em] text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={cloudParsing} onChange={(e) => setCloudParsing(e.target.checked)} className="rounded" />
              Enable Cloud Parsing for this Collection
            </label>
            {cloudParsing && (
              <p className="font-normal text-[12px] text-muted-foreground/80 leading-relaxed">
                When enabled, uploaded documents will be parsed by MinerU's cloud API and chunked using a Markdown-aware strategy that preserves tables, code blocks, and heading structure.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Config"}
        </Button>
      </div>
    </div>
  )
}
