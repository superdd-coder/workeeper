import { useEffect, useRef } from "react"
import { useAppStore } from "@/stores/app-store"
import { MessageBubble } from "./message-bubble"
import { ChatInput } from "./chat-input"
import { MessageSquare } from "lucide-react"
import { getLLMProviders } from "@/api/client"

export function ChatView() {
  const { messages, setProviders, setActiveProvider, setActiveModel, activeProvider, activeModel } = useAppStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const loadProviders = async () => {
      try {
        const list = await getLLMProviders()
        setProviders(list)
        if (!activeProvider) {
          const defaultP = list.find((p) => p.is_default) || list[0]
          if (defaultP) {
            setActiveProvider(defaultP.id)
            if (!activeModel) {
              setActiveModel(defaultP.default_model || defaultP.selected_models?.[0] || defaultP.model || null)
            }
          }
        }
      } catch {
        // ignore
      }
    }
    loadProviders()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-4 py-20">
            <MessageSquare className="h-12 w-12 opacity-30" />
            <p className="text-lg font-medium">Ask a question about your documents</p>
            <p className="text-sm">Upload documents first, then start chatting</p>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto py-4 px-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <ChatInput />
    </div>
  )
}
