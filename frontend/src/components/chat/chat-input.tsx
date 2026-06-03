import { useState, useRef, useEffect, type KeyboardEvent } from "react"
import { Send, Paperclip, Layers, Bot, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { useAppStore } from "@/stores/app-store"
import { useStreamChat } from "@/hooks/use-stream"
import { uploadFiles, getCollections } from "@/api/client"
import { toast } from "sonner"

function persisted<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(`chat_${key}`)
    if (v === null) return fallback
    return JSON.parse(v) as T
  } catch {
    return fallback
  }
}

export function ChatInput() {
  const [input, setInput] = useState("")
  const [showCollections, setShowCollections] = useState(false)
  const [allCollections, setAllCollections] = useState<string[]>([])
  const [useAgent, setUseAgent] = useState(() => persisted("useAgent", true))
  const [searchMode, setSearchMode] = useState(() => persisted("searchMode", "dense"))
  const [topK, setTopK] = useState(() => persisted("topK", 5))
  const [useReranker, setUseReranker] = useState(() => persisted("useReranker", true))
  const [maxIterations, setMaxIterations] = useState(() => persisted("maxIterations", 3))
  const [rerankTopK, setRerankTopK] = useState(() => persisted("rerankTopK", 5))
  const [minScore, setMinScore] = useState(() => persisted("minScore", 0))
  const {
    isStreaming,
    activeCollection,
    selectedCollections,
    toggleCollection,
    activeProvider,
    activeModel,
    setActiveModel,
    providers,
  } = useAppStore()
  const { sendMessage } = useStreamChat()
  const fileRef = useRef<HTMLInputElement>(null)
  const collectionMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const cols = await getCollections()
        setAllCollections(cols.map(c => c.name))
      } catch {
        // ignore
      }
    }
    load()
  }, [])

  // Persist chat params to localStorage (skip NaN sentinel values)
  useEffect(() => { localStorage.setItem("chat_useAgent", JSON.stringify(useAgent)) }, [useAgent])
  useEffect(() => { localStorage.setItem("chat_searchMode", JSON.stringify(searchMode)) }, [searchMode])
  useEffect(() => { if (!isNaN(topK)) localStorage.setItem("chat_topK", JSON.stringify(topK)) }, [topK])
  useEffect(() => { localStorage.setItem("chat_useReranker", JSON.stringify(useReranker)) }, [useReranker])
  useEffect(() => { if (!isNaN(maxIterations)) localStorage.setItem("chat_maxIterations", JSON.stringify(maxIterations)) }, [maxIterations])
  useEffect(() => { if (!isNaN(rerankTopK)) localStorage.setItem("chat_rerankTopK", JSON.stringify(rerankTopK)) }, [rerankTopK])
  useEffect(() => { localStorage.setItem("chat_minScore", JSON.stringify(minScore)) }, [minScore])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (collectionMenuRef.current && !collectionMenuRef.current.contains(e.target as Node)) {
        setShowCollections(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const readyProviders = providers.filter((p) => p.status === "ready" || !p.status)
  const currentProvider = activeProvider
    ? readyProviders.find((p) => p.id === activeProvider)
    : readyProviders.find((p) => p.is_default) || readyProviders[0]
  const availableModels = currentProvider?.selected_models && currentProvider.selected_models.length > 0
    ? currentProvider.selected_models
    : currentProvider?.model ? [currentProvider.model] : []

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput("")
    const cols = selectedCollections.length > 0 ? selectedCollections : allCollections
    await sendMessage(text, cols, activeProvider, activeModel, useAgent, searchMode, {
      top_k: isNaN(topK) ? 5 : topK,
      use_reranker: useReranker,
      max_iterations: isNaN(maxIterations) ? 3 : maxIterations,
      min_score: minScore,
      rerank_top_k: isNaN(rerankTopK) ? 5 : rerankTopK,
    })
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileAttach = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files?.length) return
    try {
      const res = await uploadFiles(files, activeCollection)
      toast.success(res.message)
    } catch (err) {
      toast.error(`Upload failed: ${err instanceof Error ? err.message : String(err)}`)
    }
    if (fileRef.current) fileRef.current.value = ""
  }

  const collectionLabel = selectedCollections.length === 0
    ? "All databases"
    : `${selectedCollections.length} database${selectedCollections.length !== 1 ? "s" : ""}`

  return (
    <div className="border-t border-border bg-background p-4">
      <div className="max-w-3xl mx-auto space-y-2">
        {/* Main toolbar: essential controls only */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
          <div className="relative" ref={collectionMenuRef}>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => setShowCollections(!showCollections)}
            >
              <Layers className="h-3 w-3 mr-1" />
              {collectionLabel}
            </Button>
            {showCollections && (
              <div className="absolute z-50 bottom-full left-0 mb-1 w-56 rounded-md border bg-popover shadow-md p-2 space-y-1 max-h-60 overflow-y-auto">
                {allCollections.map((col) => (
                  <label key={col} className="flex items-center gap-2 text-sm cursor-pointer px-2 py-1 rounded hover:bg-accent">
                    <input
                      type="checkbox"
                      checked={selectedCollections.includes(col)}
                      onChange={() => toggleCollection(col)}
                      className="rounded"
                    />
                    {col}
                  </label>
                ))}
              </div>
            )}
          </div>

          <Button
            variant={useAgent ? "default" : "outline"}
            size="sm"
            className="h-7 text-xs"
            onClick={() => setUseAgent(!useAgent)}
            title={useAgent ? "Agentic RAG ON — uses LLM to analyze, route, and iterate" : "Agentic RAG OFF — direct retrieval"}
          >
            <Bot className="h-3 w-3 mr-1" />
            {useAgent ? "Agent" : "Direct"}
          </Button>

          <Button
            variant={useReranker ? "default" : "outline"}
            size="sm"
            className="h-7 text-xs"
            onClick={() => setUseReranker(!useReranker)}
            title="Toggle reranker"
          >
            Rerank
          </Button>

          {readyProviders.length > 0 && (
            <>
              <select
                className="h-7 rounded-md border border-input bg-background px-2 text-xs"
                value={activeProvider ?? ""}
                onChange={(e) => {
                  const val = e.target.value || null
                  useAppStore.getState().setActiveProvider(val)
                  const prov = readyProviders.find((p) => p.id === val)
                  const defaultM = prov?.default_model || prov?.selected_models?.[0] || prov?.model || null
                  setActiveModel(defaultM)
                }}
              >
                <option value="">Default provider</option>
                {readyProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.name || p.model}</option>
                ))}
              </select>

              {activeProvider && availableModels.length >= 1 && (
                <select
                  className="h-7 rounded-md border border-input bg-background px-2 text-xs"
                  value={activeModel ?? ""}
                  onChange={(e) => setActiveModel(e.target.value || null)}
                >
                  {availableModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              )}
            </>
          )}

          {/* Settings button */}
          <Sheet>
            <SheetTrigger render={<Button variant="ghost" size="sm" className="h-7 text-xs ml-auto" />}>
              <Settings className="h-3 w-3 mr-1" />
              Settings
            </SheetTrigger>
            <SheetContent side="right" className="sm:max-w-sm">
              <SheetHeader>
                <SheetTitle>Chat Settings</SheetTitle>
              </SheetHeader>
              <div className="px-4 pb-4 space-y-4 overflow-y-auto flex-1">
                {/* Search Mode */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium">Search Mode</label>
                  <select
                    className="w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                    value={searchMode}
                    onChange={(e) => setSearchMode(e.target.value)}
                  >
                    <option value="dense">Dense — vector similarity</option>
                    <option value="hybrid">Hybrid — vector + BM25 keyword</option>
                  </select>
                </div>

                {/* TopK */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium">Top K — chunks to retrieve</label>
                  <input
                    type="number" min={1} max={50} value={isNaN(topK) ? "" : topK}
                    onChange={(e) => {
                      const v = e.target.value
                      if (v === "") { setTopK(NaN); return }
                      const n = parseInt(v)
                      if (!isNaN(n)) setTopK(Math.max(1, Math.min(50, n)))
                    }}
                    onBlur={() => { if (isNaN(topK)) setTopK(5) }}
                    className="w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                  />
                </div>

                {/* Rerank Top K */}
                {useReranker && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium">Rerank Top K — results after reranking</label>
                    <input
                      type="number" min={1} max={50} value={isNaN(rerankTopK) ? "" : rerankTopK}
                      onChange={(e) => {
                        const v = e.target.value
                        if (v === "") { setRerankTopK(NaN); return }
                        const n = parseInt(v)
                        if (!isNaN(n)) setRerankTopK(Math.max(1, Math.min(50, n)))
                      }}
                      onBlur={() => { if (isNaN(rerankTopK)) setRerankTopK(5) }}
                      className="w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                    />
                  </div>
                )}

                {/* Similarity Threshold — hidden for hybrid mode */}
                {searchMode !== "hybrid" && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium">
                      Similarity Threshold — {minScore.toFixed(2)}
                    </label>
                    <input
                      type="range" min={0} max={1} step={0.05} value={minScore}
                      onChange={(e) => setMinScore(parseFloat(e.target.value))}
                      className="w-full"
                    />
                    <div className="flex justify-between text-[10px] text-muted-foreground">
                      <span>0.00 (all results)</span>
                      <span>1.00 (exact match)</span>
                    </div>
                  </div>
                )}

                {/* Max Iterations (agent only) */}
                {useAgent && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium">Max Iterations — agentic RAG loops</label>
                    <input
                      type="number" min={1} max={10} value={isNaN(maxIterations) ? "" : maxIterations}
                      onChange={(e) => {
                        const v = e.target.value
                        if (v === "") { setMaxIterations(NaN); return }
                        const n = parseInt(v)
                        if (!isNaN(n)) setMaxIterations(Math.max(1, Math.min(10, n)))
                      }}
                      onBlur={() => { if (isNaN(maxIterations)) setMaxIterations(3) }}
                      className="w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                    />
                  </div>
                )}

              </div>
            </SheetContent>
          </Sheet>
        </div>

        {/* Input area */}
        <div className="flex items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.txt,.md,.docx,.xlsx,.pptx"
            className="hidden"
            onChange={handleFileAttach}
          />
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 mb-1"
            onClick={() => fileRef.current?.click()}
            disabled={isStreaming}
          >
            <Paperclip className="h-4 w-4" />
          </Button>

          <textarea
            className="flex-1 resize-none rounded-xl border border-input bg-background px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring min-h-[44px] max-h-[160px]"
            placeholder="Ask a question..."
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />

          <Button
            size="icon"
            className="shrink-0 mb-1 rounded-xl"
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
