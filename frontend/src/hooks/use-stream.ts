import { useAppStore, type Source } from "@/stores/app-store"

interface StreamMeta {
  type: "meta"
  sources: Source[]
  iterations: number
  query_used: string
  provider?: string
  model?: string
  search_mode?: string
  mode?: string
  agent_active?: boolean
}
interface StreamToken {
  type: "token"
  content: string
}
interface StreamStep {
  type: "step"
  step: string
  content: string
}
interface StreamDone {
  type: "done"
}
interface StreamError {
  type: "error"
  content: string
}
type StreamEvent = StreamMeta | StreamToken | StreamStep | StreamDone | StreamError

export function useStreamChat() {
  const {
    addMessage,
    appendToLastMessage,
    setLastMessageSources,
    setStreaming,
  } = useAppStore()

  const sendMessage = async (
    question: string,
    collections: string[],
    providerId?: string | null,
    model?: string | null,
    useAgent?: boolean,
    searchMode?: string,
    params?: { top_k?: number; use_reranker?: boolean; max_iterations?: number; min_score?: number; rerank_top_k?: number },
  ) => {
    const userId = crypto.randomUUID()
    const assistantId = crypto.randomUUID()

    addMessage({ id: userId, role: "user", content: question })
    addMessage({ id: assistantId, role: "assistant", content: "", isStreaming: true })
    setStreaming(true)

    try {
      const body: Record<string, unknown> = {
        question,
        collection: collections[0] || "default",
        use_agent: useAgent !== false,
      }
      if (providerId) body.provider_id = providerId
      if (model) body.model = model
      if (collections.length > 1) body.collections = collections
      if (searchMode) body.search_mode = searchMode
      if (params?.top_k) body.top_k = params.top_k
      if (params?.rerank_top_k) body.rerank_top_k = params.rerank_top_k
      if (params?.use_reranker !== undefined) body.use_reranker = params.use_reranker
      if (params?.max_iterations) body.max_iterations = params.max_iterations
      if (params?.min_score !== undefined && params.min_score > 0) body.min_score = params.min_score

      const res = await fetch("/api/query/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const text = await res.text()
        appendToLastMessage(`Error: ${res.status} - ${text}`)
        setStreaming(false)
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith("data: ")) continue

          let event: StreamEvent
          try {
            event = JSON.parse(trimmed.slice(6))
          } catch {
            continue
          }

          switch (event.type) {
            case "meta": {
              // Append metadata header (don't overwrite previous steps)
              const parts: string[] = []
              if (event.provider || event.model) {
                parts.push(`**Provider:** ${event.provider || "unknown"} / ${event.model || "unknown"}`)
              }
              if (event.search_mode) {
                parts.push(`**Search:** ${event.search_mode}`)
              }
              if (event.mode) {
                const modeLabel = event.mode === "agentic" ? "Agentic RAG" :
                  event.mode === "parent-child" ? "Parent-Child" : "Standard"
                parts.push(`**Mode:** ${modeLabel}`)
              }
              if (event.agent_active && event.iterations > 0) {
                parts.push(`**Iterations:** ${event.iterations}`)
              }
              if (parts.length > 0) {
                appendToLastMessage("\n\n" + parts.join(" | ") + "\n\n---\n\n")
              }
              setLastMessageSources(event.sources)
              break
            }
            case "step":
              // Show step progress in the message
              appendToLastMessage(`\n\n*${event.content}*`)
              break
            case "token":
              appendToLastMessage(event.content)
              break
            case "done":
              setStreaming(false)
              return
            case "error":
              appendToLastMessage(`\n\n**Error:** ${event.content}`)
              setStreaming(false)
              return
          }
        }
      }
    } catch (err) {
      appendToLastMessage(`\n\n**Error:** ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setStreaming(false)
    }
  }

  return { sendMessage }
}
