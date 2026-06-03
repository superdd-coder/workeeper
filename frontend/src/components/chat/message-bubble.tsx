import { memo } from "react"
import { Avatar } from "@/components/ui/avatar"
import { Bot, User } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { SourcesCard } from "./sources-card"
import type { Message } from "@/stores/app-store"
import { cn } from "@/lib/utils"

interface MessageBubbleProps {
  message: Message
}

export const MessageBubble = memo(function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user"

  return (
    <div className={cn("flex gap-3 py-4 px-4", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <Avatar className="h-8 w-8 shrink-0 bg-primary/10 flex items-center justify-center">
          <Bot className="h-4 w-4 text-primary" />
        </Avatar>
      )}

      <div className={cn("max-w-[75%] space-y-1", isUser && "order-first")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-sm leading-relaxed",
            isUser
              ? "bg-primary text-primary-foreground rounded-br-md"
              : "bg-muted rounded-bl-md"
          )}
        >
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-pre:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content || (message.isStreaming ? "..." : "")}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {!isUser && message.sources && message.sources.length > 0 && (
          <SourcesCard sources={message.sources} />
        )}
      </div>

      {isUser && (
        <Avatar className="h-8 w-8 shrink-0 bg-secondary flex items-center justify-center">
          <User className="h-4 w-4 text-secondary-foreground" />
        </Avatar>
      )}
    </div>
  )
})
