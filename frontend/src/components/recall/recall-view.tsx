import { useState, useEffect, useRef, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Search, Loader2, FlaskConical, Trash2, Wand2, Play, RotateCw,
  CheckCircle, XCircle, Clock, BarChart3, ChevronDown, ChevronRight,
} from "lucide-react"
import { useAppStore } from "@/stores/app-store"
import {
  getCollections, recallSearch, type RecallResult,
  getEvalCases, deleteEvalCase, generateEvalCases,
  runEval, getEvalHistory, getRerankProviders, getChunkContent,
  type EvalTestCase, type EvalReport, type RerankProvider, type ChunkContent,
} from "@/api/client"
import { toast } from "sonner"
import { ResultList } from "./result-list"
import { TooltipLabel } from "@/components/shared/tooltip-label"


// ── Search Tab (existing) ──────────────────────────────────

function SearchTab() {
  const { selectedCollections, setSelectedCollections, removeDeletedCollection } = useAppStore()
  const [allCollections, setAllCollections] = useState<string[]>([])
  const [query, setQuery] = useState("")
  const [topK, setTopK] = useState("10")
  const [rerankTopK, setRerankTopK] = useState("5")
  const [searchMode, setSearchMode] = useState("dense")
  const [useReranker, setUseReranker] = useState(false)
  const [useAgent, setUseAgent] = useState(false)
  const [minScore, setMinScore] = useState(0)
  const [rerankProviderId, setRerankProviderId] = useState("")
  const [rerankProviders, setRerankProviders] = useState<RerankProvider[]>([])
  const [results, setResults] = useState<RecallResult[]>([])
  const [timeMs, setTimeMs] = useState(0)
  const [searching, setSearching] = useState(false)
  const [showCollections, setShowCollections] = useState(false)
  const collectionMenuRef = useRef<HTMLDivElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const cols = await getCollections()
        setAllCollections(cols.map(c => c.name))
        for (const c of selectedCollections) {
          if (!cols.some(col => col.name === c)) removeDeletedCollection(c)
        }
      } catch { /* ignore */ }
      try {
        const providers = await getRerankProviders()
        setRerankProviders(providers)
      } catch { /* ignore */ }
    }
    load()
    const onFocus = () => load()
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        collectionMenuRef.current && !collectionMenuRef.current.contains(e.target as Node) &&
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node)
      ) {
        setShowCollections(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const toggleCollection = (name: string) => {
    const exists = selectedCollections.includes(name)
    const next = exists ? selectedCollections.filter((c) => c !== name) : [...selectedCollections, name]
    setSelectedCollections(next)
  }

  const handleSearch = async () => {
    if (!query.trim()) return
    const collections = selectedCollections.length > 0 ? selectedCollections : ["default"]
    setResults([])
    setSearching(true)
    try {
      const res = await recallSearch({
        query: query.trim(), collections, search_mode: searchMode,
        top_k: parseInt(topK) || 10, rerank_top_k: parseInt(rerankTopK) || 5,
        use_reranker: useReranker, use_agent: useAgent,
        min_score: minScore,
        rerank_provider_id: useReranker && rerankProviderId ? rerankProviderId : undefined,
      })
      setResults(res.results)
      setTimeMs(res.time_ms)
    } catch (err) {
      toast.error(`Search failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex gap-3">
            <div className="flex-1">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="Search query..."
                disabled={searching}
              />
            </div>
            <Button onClick={handleSearch} disabled={searching || !query.trim()}>
              {searching ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}
              Search
            </Button>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <div className="relative" ref={collectionMenuRef}>
              <Button variant="outline" size="sm" onClick={() => setShowCollections(!showCollections)}>
                Databases ({selectedCollections.length})
              </Button>
              {showCollections && (
                <div ref={dropdownRef} className="fixed z-50 mt-1 w-56 rounded-md border bg-popover shadow-md p-2 space-y-1 max-h-60 overflow-y-auto" style={{ top: collectionMenuRef.current ? collectionMenuRef.current.getBoundingClientRect().bottom + 4 : 0, left: collectionMenuRef.current ? collectionMenuRef.current.getBoundingClientRect().left : 0 }}>
                  {allCollections.map((col) => (
                    <label key={col} className="flex items-center gap-2 text-sm cursor-pointer px-2 py-1 rounded hover:bg-accent">
                      <input type="checkbox" checked={selectedCollections.includes(col)} onChange={() => toggleCollection(col)} className="rounded" />
                      {col}
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              <TooltipLabel label="Search Mode" tooltip="dense: vector similarity only. hybrid: vector + BM25 keyword matching." />
              <select className="h-8 rounded-md border border-input bg-background px-2 text-xs" value={searchMode} onChange={(e) => setSearchMode(e.target.value)}>
                <option value="dense">Dense</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </div>

            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={useReranker || useAgent}
                disabled={useAgent}
                onChange={(e) => setUseReranker(e.target.checked)}
                className="rounded"
              />
              <TooltipLabel label="Use Reranker" tooltip={useAgent ? "Reranker is required for Agentic RAG" : "Apply a reranker model to re-score retrieved results for better precision."} />
            </label>

            {useReranker && rerankProviders.length > 0 && (
              <select
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                value={rerankProviderId}
                onChange={(e) => setRerankProviderId(e.target.value)}
              >
                <option value="">Default</option>
                {rerankProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.name || p.model}</option>
                ))}
              </select>
            )}

            <div className="flex items-center gap-2">
              <TooltipLabel label="Top K" tooltip="Number of top results to retrieve." />
              <Input className="w-16 h-8" value={topK} onChange={(e) => setTopK(e.target.value)} />
            </div>

            {searchMode !== "hybrid" && (
              <div className="flex items-center gap-2">
                <TooltipLabel label="Threshold" tooltip="Minimum similarity score (0-1). Results below this are filtered out." />
                <input
                  type="range" min={0} max={1} step={0.05} value={minScore}
                  onChange={(e) => setMinScore(parseFloat(e.target.value))}
                  className="w-20"
                />
                <span className="text-xs text-muted-foreground w-8">{minScore.toFixed(2)}</span>
              </div>
            )}

            {useReranker && (
              <div className="flex items-center gap-2">
                <TooltipLabel label="Rerank Top K" tooltip="Number of results after reranking." />
                <Input className="w-16 h-8" value={rerankTopK} onChange={(e) => setRerankTopK(e.target.value)} />
              </div>
            )}
          </div>

          <Separator />
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
              <input
                type="checkbox"
                checked={useAgent}
                onChange={(e) => {
                  const next = e.target.checked
                  setUseAgent(next)
                  if (next) setUseReranker(true)  // agentic requires reranker
                }}
                className="rounded"
              />
              <TooltipLabel label="Agentic RAG" tooltip="Uses LLM agent to analyze queries, route to relevant databases, and iteratively improve results. Reranker is required." />
            </label>
          </div>
        </CardContent>
      </Card>

      {results.length > 0 && (
        <>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span>{results.length} results</span>
            <span>in {timeMs}ms</span>
            <Badge variant="outline">{searchMode}</Badge>
            {useReranker && <Badge variant="secondary">Reranked</Badge>}
            {useAgent && <Badge variant="secondary">Agentic</Badge>}
          </div>
          <ResultList results={results} />
        </>
      )}

      {results.length === 0 && !searching && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Search className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p>Enter a query to search your databases</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Evaluate Tab ───────────────────────────────────────────

const EVAL_RUNNING_PREFIX = "eval_running_"
const GEN_RUNNING_PREFIX = "gen_running_"

function EvaluateTab() {
  const { selectedCollections, setSelectedCollections } = useAppStore()
  const [allCollections, setAllCollections] = useState<string[]>([])
  const collection = selectedCollections[0] || ""
  const [cases, setCases] = useState<EvalTestCase[]>([])
  const [loading, setLoading] = useState(false)
  const [evalTopK, setEvalTopK] = useState("10")
  const [evalSearchMode, setEvalSearchMode] = useState("dense")
  const [evalUseReranker, setEvalUseReranker] = useState(false)
  const [evalRerankTopK, setEvalRerankTopK] = useState("5")
  const [evalMinScore, setEvalMinScore] = useState(0)
  const [evalRerankProviderId, setEvalRerankProviderId] = useState("")
  const [evalRerankProviders, setEvalRerankProviders] = useState<RerankProvider[]>([])
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState<EvalReport | null>(null)
  const [history, setHistory] = useState<EvalReport[]>([])
  const [expandedQuery, setExpandedQuery] = useState<string | null>(null)
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null)
  const [expandedChunk, setExpandedChunk] = useState<ChunkContent | null>(null)
  const [chunkLoading, setChunkLoading] = useState(false)
  const autoRecovered = useRef<Set<string>>(new Set())

  useEffect(() => {
    getCollections().then(cols => setAllCollections(cols.map(c => c.name))).catch(() => {})
    getRerankProviders().then(setEvalRerankProviders).catch(() => {})
  }, [])

  // Auto-recover in-flight eval after refresh / tab switch
  useEffect(() => {
    if (!collection || autoRecovered.current.has(collection)) return
    const key = EVAL_RUNNING_PREFIX + collection
    const saved = localStorage.getItem(key)
    if (!saved) return
    try {
      const data = JSON.parse(saved)
      if (data.running && data.params) {
        autoRecovered.current.add(collection)
        // Restore params
        if (data.params.top_k) setEvalTopK(String(data.params.top_k))
        if (data.params.search_mode) setEvalSearchMode(data.params.search_mode)
        if (data.params.use_reranker !== undefined) setEvalUseReranker(data.params.use_reranker)
        if (data.params.rerank_top_k) setEvalRerankTopK(String(data.params.rerank_top_k))
        if (data.params.min_score !== undefined) setEvalMinScore(data.params.min_score)
        if (data.params.rerank_provider_id) setEvalRerankProviderId(data.params.rerank_provider_id)
        setRunning(true)
        setReport(null)
        runEval(collection, data.params)
          .then(res => { setReport(res); loadHistory() })
          .catch(err => toast.error(`Evaluation failed: ${err instanceof Error ? err.message : String(err)}`))
          .finally(() => { setRunning(false); localStorage.removeItem(key) })
      }
    } catch { localStorage.removeItem(key) }
  }, [collection])

  // Auto-recover in-flight case generation after refresh / tab switch
  useEffect(() => {
    if (!collection || autoRecovered.current.has(`gen_${collection}`)) return
    const key = GEN_RUNNING_PREFIX + collection
    const saved = localStorage.getItem(key)
    if (!saved) return
    try {
      const data = JSON.parse(saved)
      if (data.running) {
        autoRecovered.current.add(`gen_${collection}`)
        setLoading(true)
        generateEvalCases(collection, data.regenerate ?? false)
          .then(res => { toast.success(res.message); loadCases() })
          .catch(err => toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`))
          .finally(() => { setLoading(false); localStorage.removeItem(key) })
      }
    } catch { localStorage.removeItem(key) }
  }, [collection])

  const loadCases = useCallback(async () => {
    if (!collection) return
    try {
      const res = await getEvalCases(collection)
      setCases(res.cases)
    } catch { /* ignore */ }
  }, [collection])

  const loadHistory = useCallback(async () => {
    if (!collection) return
    try {
      const res = await getEvalHistory(collection)
      setHistory(res.history)
    } catch { /* ignore */ }
  }, [collection])

  useEffect(() => {
    loadCases()
    loadHistory()
  }, [loadCases, loadHistory])

  const handleDeleteCase = async (id: string) => {
    if (!collection) return
    try {
      await deleteEvalCase(collection, id)
      loadCases()
    } catch { /* ignore */ }
  }

  const handleGenerate = async (regenerate = false) => {
    if (!collection) return
    if (regenerate && !confirm("This will delete all existing test cases and generate fresh ones. Continue?")) return
    const key = GEN_RUNNING_PREFIX + collection
    localStorage.setItem(key, JSON.stringify({ running: true, regenerate, ts: Date.now() }))
    setLoading(true)
    try {
      const res = await generateEvalCases(collection, regenerate)
      toast.success(res.message)
      loadCases()
    } catch (err) {
      toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setLoading(false)
      localStorage.removeItem(key)
    }
  }

  const handleRun = async () => {
    if (!collection || cases.length === 0) return
    const params = {
      top_k: parseInt(evalTopK) || 10,
      search_mode: evalSearchMode,
      use_reranker: evalUseReranker,
      rerank_top_k: parseInt(evalRerankTopK) || 5,
      min_score: evalMinScore,
      rerank_provider_id: evalUseReranker && evalRerankProviderId ? evalRerankProviderId : undefined,
    }
    const key = EVAL_RUNNING_PREFIX + collection
    localStorage.setItem(key, JSON.stringify({ running: true, params, ts: Date.now() }))
    setRunning(true)
    setReport(null)
    try {
      const res = await runEval(collection, params)
      setReport(res)
      loadHistory()
    } catch (err) {
      toast.error(`Evaluation failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setRunning(false)
      localStorage.removeItem(key)
    }
  }

  if (!collection) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground space-y-4">
          <FlaskConical className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p>Select a database to evaluate</p>
          <div className="flex justify-center">
            <select
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value=""
              onChange={(e) => {
                if (e.target.value) setSelectedCollections([e.target.value])
              }}
            >
              <option value="">Choose a database...</option>
              {allCollections.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Config bar */}
      <Card>
        <CardContent className="p-3">
          <div className="flex items-center gap-4 flex-wrap">
            <select
              className="h-8 rounded-md border border-input bg-background px-2 text-xs font-medium"
              value={collection}
              onChange={(e) => {
                if (e.target.value) setSelectedCollections([e.target.value])
              }}
            >
              {allCollections.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
            <div className="flex items-center gap-2">
              <TooltipLabel label="Search Mode" tooltip="dense or hybrid" />
              <select className="h-8 rounded-md border border-input bg-background px-2 text-xs" value={evalSearchMode} onChange={(e) => setEvalSearchMode(e.target.value)}>
                <option value="dense">Dense</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="checkbox" checked={evalUseReranker} onChange={(e) => setEvalUseReranker(e.target.checked)} className="rounded" />
              Reranker
            </label>
            {evalUseReranker && evalRerankProviders.length > 0 && (
              <select
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                value={evalRerankProviderId}
                onChange={(e) => setEvalRerankProviderId(e.target.value)}
              >
                <option value="">Default</option>
                {evalRerankProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.name || p.model}</option>
                ))}
              </select>
            )}
            <div className="flex items-center gap-2">
              <TooltipLabel label="Top K" tooltip="Results to retrieve per query" />
              <Input className="w-16 h-8" value={evalTopK} onChange={(e) => setEvalTopK(e.target.value)} />
            </div>
            {evalUseReranker && (
              <div className="flex items-center gap-2">
                <TooltipLabel label="Rerank Top K" tooltip="Number of results after reranking." />
                <Input className="w-16 h-8" value={evalRerankTopK} onChange={(e) => setEvalRerankTopK(e.target.value)} />
              </div>
            )}
            {evalSearchMode !== "hybrid" && (
              <div className="flex items-center gap-2">
                <TooltipLabel label="Threshold" tooltip="Minimum similarity score (0-1). Filter retrieved chunks below this. Same as the slider in Search tab." />
                <input
                  type="range" min={0} max={1} step={0.05} value={evalMinScore}
                  onChange={(e) => setEvalMinScore(parseFloat(e.target.value))}
                  className="w-20"
                />
                <span className="text-xs text-muted-foreground w-8">{evalMinScore.toFixed(2)}</span>
              </div>
            )}
            <div className="flex-1" />
            <Button onClick={handleRun} disabled={running || cases.length === 0}>
              {running ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
              Run Evaluation ({cases.length} cases)
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Test Cases */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Test Cases ({cases.length})</CardTitle>
            <div className="flex gap-2">
              {cases.length === 0 ? (
                <Button variant="outline" size="sm" onClick={() => handleGenerate(false)} disabled={loading}>
                  {loading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Wand2 className="h-3 w-3 mr-1" />}
                  Auto-generate
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => handleGenerate(true)} disabled={loading}>
                  {loading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <RotateCw className="h-3 w-3 mr-1" />}
                  Regenerate All
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating test cases...
            </div>
          ) : cases.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center">
              No test cases. Click "Auto-generate" to create cases from indexed files.
            </p>
          ) : (
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {cases.map((c) => (
                <div key={c.id}>
                  <div
                    className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent group cursor-pointer"
                    onClick={async () => {
                      if (expandedCaseId === c.id) {
                        setExpandedCaseId(null)
                        setExpandedChunk(null)
                        return
                      }
                      setExpandedCaseId(c.id)
                      setExpandedChunk(null)
                      if (c.target_chunk_id) {
                        setChunkLoading(true)
                        try {
                          const chunk = await getChunkContent(collection, c.target_chunk_id)
                          setExpandedChunk(chunk)
                        } catch { /* chunk not found */ }
                        setChunkLoading(false)
                      }
                    }}
                  >
                    {expandedCaseId === c.id ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
                    <span className="flex-1 truncate">{c.query}</span>
                    <span className="text-muted-foreground shrink-0 truncate max-w-[200px]" title={c.target_source}>
                      → {c.target_source?.split("/").pop()}
                    </span>
                    <Button variant="ghost" size="sm" className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100" onClick={(e) => { e.stopPropagation(); handleDeleteCase(c.id) }}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                  {expandedCaseId === c.id && (
                    <div className="pl-8 pb-3 space-y-2 text-xs border-l-2 border-muted ml-1 mt-1">
                      <div>
                        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">Query</div>
                        <div className="text-foreground/90 whitespace-pre-wrap">{c.query}</div>
                      </div>
                      <div className="flex gap-4 text-[10px] text-muted-foreground">
                        <span>Target chunk: <span className="font-mono text-foreground/70">{c.target_chunk_id}</span></span>
                        <span>Source: <span className="text-foreground/70">{c.target_source?.split("/").pop()}</span></span>
                      </div>
                      <div>
                        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">Target Chunk Content</div>
                        {chunkLoading ? (
                          <div className="flex items-center gap-2 text-muted-foreground py-2">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Loading...
                          </div>
                        ) : expandedChunk ? (
                          <div className="text-foreground/80 text-[11px] whitespace-pre-wrap bg-muted/30 p-2 rounded max-h-48 overflow-y-auto">
                            {expandedChunk.text}
                          </div>
                        ) : (
                          <div className="text-muted-foreground italic text-[11px]">Chunk not found (may have been deleted)</div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* History */}
      {history.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Evaluation History</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {history.map((h, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 text-xs py-1.5 px-2 rounded hover:bg-accent cursor-pointer"
                  onClick={() => setReport(h)}
                >
                  <Clock className="h-3 w-3 text-muted-foreground" />
                  <span className="text-muted-foreground">
                    {h.timestamp
                      ? new Date(h.timestamp).toLocaleString()
                      : `Run ${i + 1}`}
                  </span>
                  <Badge variant="outline" className="text-[10px]">{h.total_cases} cases</Badge>
                  <span>Recall: {((h.avg_recall ?? h.avg_hard_recall ?? 0) * 100).toFixed(0)}%</span>
                  <span className={`font-mono ${qualityColor(h.avg_quality_score ?? 0)}`}>Q: {formatSigned(h.avg_quality_score ?? 0)}</span>
                  <span className="text-muted-foreground">{(h.avg_time_ms ?? 0).toFixed(0)}ms</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results Dashboard */}
      {report && (
        <>
          <div className="grid grid-cols-4 gap-3">
            <MetricCard label="Recall" value={`${((report.avg_recall ?? 0) * 100).toFixed(1)}%`} icon={<CheckCircle className="h-4 w-4" />} tooltip="target in K OR LLM holistic 'can answer correctly'. The two query-level signals OR'd together." />
            <MetricCard label="Hard Recall" value={`${((report.avg_hard_recall ?? 0) * 100).toFixed(1)}%`} icon={<CheckCircle className="h-4 w-4" />} tooltip="Target chunk id found in top K (deterministic)" />
            <MetricCard label="Quality" value={formatSigned(report.avg_quality_score ?? 0)} icon={<BarChart3 className="h-4 w-4" />} tooltip="Coverage-dominant on per-chunk judgments. Useful info present ≈ high. Noise-only ≈ low. Range [-1, 1]." />
            <MetricCard label="MRR" value={(report.avg_mrr ?? 0).toFixed(3)} icon={<BarChart3 className="h-4 w-4" />} tooltip="Mean reciprocal rank of target chunk" />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Per-Query Results</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {report.per_query.map((r) => (
                  <div key={r.test_case_id}>
                    <div
                      className="flex items-center gap-2 text-xs py-2 px-2 rounded hover:bg-accent cursor-pointer"
                      onClick={() => setExpandedQuery(expandedQuery === r.test_case_id ? null : r.test_case_id)}
                    >
                      {expandedQuery === r.test_case_id ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
                      {r.recalled ? <CheckCircle className="h-3 w-3 text-green-500 shrink-0" /> : <XCircle className="h-3 w-3 text-red-500 shrink-0" />}
                      <span className="flex-1 truncate">{r.query}</span>
                      {r.hard_recall ? (
                        <Badge className="text-[10px] px-1 bg-green-600">target</Badge>
                      ) : r.holistic_can_answer ? (
                        <Badge variant="secondary" className="text-[10px] px-1">holistic</Badge>
                      ) : (
                        <Badge variant="destructive" className="text-[10px] px-1">miss</Badge>
                      )}
                      <span className={`w-14 text-right font-mono ${qualityColor(r.quality_score ?? 0)}`}>
                        Q:{formatSigned(r.quality_score ?? 0)}
                      </span>
                      <span className="text-muted-foreground w-12 text-right">{r.time_ms}ms</span>
                    </div>
                    {expandedQuery === r.test_case_id && (
                      <div className="pl-8 pb-3 space-y-2 text-xs border-l-2 border-muted ml-1">
                        <div className="flex gap-3 text-muted-foreground flex-wrap">
                          <span>Recall: <span className={r.recalled ? "text-green-600 font-medium" : "text-red-500"}>{r.recalled ? "✓" : "✗"}</span></span>
                          <span>Hard: <span className={r.hard_recall ? "text-green-600 font-medium" : "text-red-500"}>{r.hard_recall ? "✓" : "✗"}</span></span>
                          <span>Holistic: <span className={r.holistic_can_answer ? "text-blue-600 font-medium" : "text-muted-foreground"}>{r.holistic_can_answer ? "✓" : "✗"}</span></span>
                          <span>Quality: <span className={`font-mono ${qualityColor(r.quality_score ?? 0)}`}>{formatSigned(r.quality_score ?? 0)}</span> <span className="text-[10px]">[-1, 1]</span></span>
                          <span>MRR: {(r.mrr ?? 0).toFixed(3)}</span>
                          {(r.target_position ?? 0) > 0 && <span className="text-green-600">target @ #{r.target_position}</span>}
                        </div>
                        {r.holistic_reason && (
                          <div className="text-foreground/80 italic text-[11px] bg-blue-50 dark:bg-blue-950/20 px-2 py-1.5 rounded border-l-2 border-blue-400">
                            <span className="font-medium text-blue-700 dark:text-blue-300 not-italic">Holistic: </span>
                            "{r.holistic_reason}"
                          </div>
                        )}
                        {(r.chunk_judgments || []).length > 0 ? (
                          <div className="mt-2 space-y-1.5">
                            <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                              Retrieved Chunks — LLM Judgment
                            </div>
                            {r.chunk_judgments.map((j, i) => {
                              const judgmentStyles: Record<string, { border: string; bg: string; badge: string; label: string }> = {
                                "1": { border: "border-l-green-500", bg: "bg-green-50 dark:bg-green-950/30", badge: "bg-green-600", label: "+1" },
                                "0": { border: "border-l-gray-400", bg: "", badge: "bg-gray-500", label: "0" },
                                "-1": { border: "border-l-red-500", bg: "bg-red-50 dark:bg-red-950/20", badge: "bg-red-600", label: "-1" },
                              }
                              const judgmentColors = judgmentStyles[String(j.judgment)] || judgmentStyles["0"]
                              const text = r.retrieved_chunks?.[i]?.text || ""
                              return (
                                <div key={j.id || i} className={`border-l-4 ${judgmentColors.border} ${judgmentColors.bg} pl-2 py-1.5`}>
                                  <div className="flex items-center gap-2 text-[10px] flex-wrap">
                                    <span className="font-mono text-muted-foreground">#{i + 1}</span>
                                    <span className={`px-1.5 py-0.5 rounded text-white font-bold ${judgmentColors.badge}`}>
                                      {judgmentColors.label}
                                    </span>
                                    {j.is_target ? (
                                      <span className="px-1.5 py-0.5 rounded bg-purple-600 text-white font-medium">
                                        TARGET
                                      </span>
                                    ) : null}
                                    <span className="text-muted-foreground">ret_score={j.score?.toFixed(3)}</span>
                                    <span className="text-muted-foreground">idx={j.chunk_index}</span>
                                    <span className="text-foreground/70 truncate">
                                      {j.source?.split("/").pop()}
                                    </span>
                                  </div>
                                  {j.reason && (
                                    <div className="mt-1 text-foreground/80 italic text-[11px]">
                                      "{j.reason}"
                                    </div>
                                  )}
                                  {text ? (
                                    <details className="mt-1" open={j.is_target}>
                                      <summary className="text-[10px] text-muted-foreground cursor-pointer hover:text-foreground select-none">
                                        {j.is_target ? "Show target chunk text" : "Show chunk text"}
                                      </summary>
                                      <div className="mt-1 text-foreground/70 text-[11px] whitespace-pre-wrap bg-muted/30 p-2 rounded max-h-64 overflow-y-auto">
                                        {text}
                                      </div>
                                    </details>
                                  ) : (
                                    <div className="mt-1 text-[10px] text-muted-foreground italic">
                                      (no chunk text available)
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <div className="text-muted-foreground italic text-[11px]">
                            (Older run — no per-chunk data. Re-run evaluation to see chunk-level judgments.)
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function formatSigned(n: number, digits = 2): string {
  if (n > 0) return `+${n.toFixed(digits)}`
  if (n < 0) return n.toFixed(digits)
  return "0.00"
}

function qualityColor(n: number): string {
  if (n >= 0.7) return "text-green-600"
  if (n > 0.2) return "text-green-500"
  if (n > -0.2) return "text-muted-foreground"
  if (n > -0.6) return "text-red-500"
  return "text-red-600"
}

function MetricCard({ label, value, icon, tooltip }: { label: string; value: string; icon: React.ReactNode; tooltip?: string }) {
  return (
    <Card>
      <CardContent className="p-3 text-center">
        <div className="flex items-center justify-center gap-1 text-muted-foreground mb-1">
          {icon}
          {tooltip ? <TooltipLabel label={label} tooltip={tooltip} /> : <span className="text-xs">{label}</span>}
        </div>
        <div className="text-lg font-semibold">{value}</div>
      </CardContent>
    </Card>
  )
}

// ── Main View ──────────────────────────────────────────────

export function RecallView() {
  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Search className="h-6 w-6" />
            Recall
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Search and evaluate retrieval quality
          </p>
        </div>

        <Tabs defaultValue="search">
          <TabsList>
            <TabsTrigger value="search">Search</TabsTrigger>
            <TabsTrigger value="evaluate">
              <FlaskConical className="h-3 w-3 mr-1" />
              Evaluate
            </TabsTrigger>
          </TabsList>
          <TabsContent value="search" className="mt-4">
            <SearchTab />
          </TabsContent>
          <TabsContent value="evaluate" className="mt-4">
            <EvaluateTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
