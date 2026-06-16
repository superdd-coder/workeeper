import { create } from "zustand"

function loadPersisted<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(`rag_${key}`)
    return v !== null ? JSON.parse(v) : fallback
  } catch {
    return fallback
  }
}

export type SidebarView = "chat" | "database" | "recall" | "meeting" | "llm_provider"

export interface Source {
  text: string
  score: number
  metadata: Record<string, unknown>
}

export interface ThinkingStep {
  label: string
  status: "active" | "done"
  details?: string[]
}

export interface ThinkingIteration {
  iteration: number
  steps: ThinkingStep[]
}

export interface MetaInfo {
  provider?: string
  model?: string
  search_mode?: string
  mode?: string
  max_iterations?: number
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: Source[]
  isStreaming?: boolean
  thinkingSteps?: ThinkingIteration[]
  metaInfo?: MetaInfo
}

export interface LLMProvider {
  id: string
  name: string
  provider: string
  model: string
  base_url: string
  api_key: string
  max_tokens: number
  max_concurrent_requests: number
  is_default: boolean
  selected_models?: string[]
  default_model?: string
  status?: "ready" | "error" | "unknown"
}

interface AppState {
  sidebarView: SidebarView
  sidebarOpen: boolean
  setSidebarView: (view: SidebarView) => void
  toggleSidebar: () => void

  activeCollection: string
  setActiveCollection: (name: string) => void
  pendingCreateCollection: boolean
  setPendingCreateCollection: (v: boolean) => void
  pendingOpenFile: string | null
  setPendingOpenFile: (source: string | null) => void

  // Meeting ingest progress (persists across dialog open/close)
  ingestMeetingId: string | null
  ingestProgress: Record<number, "pending" | "done" | "error">
  ingestProjectNames: string[]
  setIngestState: (meetingId: string | null, progress: Record<number, "pending" | "done" | "error">, names: string[]) => void

  selectedCollections: string[]
  setSelectedCollections: (names: string[]) => void
  toggleCollection: (name: string) => void
  removeDeletedCollection: (name: string) => void

  activeProvider: string | null
  setActiveProvider: (id: string | null) => void
  activeModel: string | null
  setActiveModel: (model: string | null) => void
  providers: LLMProvider[]
  setProviders: (providers: LLMProvider[] | ((prev: LLMProvider[]) => LLMProvider[])) => void

  messages: Message[]
  isStreaming: boolean
  addMessage: (msg: Message) => void
  appendToLastMessage: (token: string) => void
  setLastMessageSources: (sources: Source[]) => void
  setLastMessageMetaInfo: (info: MetaInfo) => void
  setLastMessageThinkingSteps: (steps: ThinkingIteration[]) => void
  setStreaming: (v: boolean) => void

  isOnline: boolean
  setOnline: (v: boolean) => void

  logPanelOpen: boolean
  toggleLogPanel: () => void

  activeMeeting: string | null
  setActiveMeeting: (id: string | null) => void

  // Navigation guard — return false to block navigation
  navigationGuard: (() => boolean) | null
  setNavigationGuard: (guard: (() => boolean) | null) => void
}

export const useAppStore = create<AppState>((set) => ({
  sidebarView: loadPersisted<SidebarView>("sidebarView", "chat"),
  sidebarOpen: true,
  setSidebarView: (view) => {
    const state = useAppStore.getState()
    // Only guard if navigating away from meeting view
    if (state.sidebarView === "meeting" && view !== "meeting" && state.navigationGuard) {
      if (!state.navigationGuard()) return
    }
    set({ sidebarView: view })
  },
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  activeCollection: "",
  setActiveCollection: (name) => set({ activeCollection: name }),
  pendingCreateCollection: false,
  setPendingCreateCollection: (v) => set({ pendingCreateCollection: v }),
  pendingOpenFile: null,
  setPendingOpenFile: (source) => set({ pendingOpenFile: source }),

  ingestMeetingId: null,
  ingestProgress: {},
  ingestProjectNames: [],
  setIngestState: (meetingId, progress, names) => set({
    ingestMeetingId: meetingId,
    ingestProgress: progress,
    ingestProjectNames: names,
  }),

  selectedCollections: loadPersisted<string[]>("selectedCollections", []),
  setSelectedCollections: (names) => set({ selectedCollections: names }),
  toggleCollection: (name) =>
    set((s) => {
      const exists = s.selectedCollections.includes(name)
      const next = exists
        ? s.selectedCollections.filter((c) => c !== name)
        : [...s.selectedCollections, name]
      return { selectedCollections: next }
    }),
  removeDeletedCollection: (name) =>
    set((s) => ({
      selectedCollections: s.selectedCollections.filter((c) => c !== name),
      activeCollection: s.activeCollection === name ? "" : s.activeCollection,
    })),

  activeProvider: loadPersisted<string | null>("activeProvider", null),
  setActiveProvider: (id) => set({ activeProvider: id }),
  activeModel: loadPersisted<string | null>("activeModel", null),
  setActiveModel: (model) => set({ activeModel: model }),
  providers: [],
  setProviders: (providers) =>
    set((s) => ({
      providers: typeof providers === "function" ? providers(s.providers) : providers,
    })),

  messages: [],
  isStreaming: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendToLastMessage: (token) =>
    set((s) => {
      const msgs = [...s.messages]
      if (msgs.length > 0) {
        const last = msgs[msgs.length - 1]
        msgs[msgs.length - 1] = { ...last, content: last.content + token }
      }
      return { messages: msgs }
    }),
  setLastMessageSources: (sources) =>
    set((s) => {
      const msgs = [...s.messages]
      if (msgs.length > 0) {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], sources, isStreaming: false }
      }
      return { messages: msgs }
    }),
  setLastMessageMetaInfo: (info) =>
    set((s) => {
      const msgs = [...s.messages]
      if (msgs.length > 0) {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], metaInfo: info }
      }
      return { messages: msgs }
    }),
  setLastMessageThinkingSteps: (steps) =>
    set((s) => {
      const msgs = [...s.messages]
      if (msgs.length > 0) {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], thinkingSteps: steps }
      }
      return { messages: msgs }
    }),
  setStreaming: (v) => set({ isStreaming: v }),

  isOnline: false,
  setOnline: (v) => set({ isOnline: v }),

  logPanelOpen: false,
  toggleLogPanel: () => set((s) => ({ logPanelOpen: !s.logPanelOpen })),

  activeMeeting: null,
  setActiveMeeting: (id) => set({ activeMeeting: id }),

  navigationGuard: null,
  setNavigationGuard: (guard) => set({ navigationGuard: guard }),
}))

// Persist selected chat params to localStorage (debounced to avoid writing on every streaming token)
let _persistTimer: ReturnType<typeof setTimeout> | null = null
useAppStore.subscribe((state) => {
  if (_persistTimer) clearTimeout(_persistTimer)
  _persistTimer = setTimeout(() => {
    localStorage.setItem("rag_activeProvider", JSON.stringify(state.activeProvider))
    localStorage.setItem("rag_activeModel", JSON.stringify(state.activeModel))
    localStorage.setItem("rag_selectedCollections", JSON.stringify(state.selectedCollections))
    localStorage.setItem("rag_sidebarView", JSON.stringify(state.sidebarView))
  }, 500)
})
