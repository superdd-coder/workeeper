import { useState, useEffect, useCallback } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Eye, EyeOff, Loader2, RefreshCw } from "lucide-react"
import { createLLMProvider, updateLLMProvider, getAvailableModels, type LLMProvider } from "@/api/client"
import { useProviderTypes } from "@/hooks/use-provider-types"
import { toast } from "sonner"

interface AddProviderDialogProps {
  open: boolean
  provider: LLMProvider | null
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}

const defaultForm = {
  name: "",
  provider: "openai_compatible",
  model: "",
  base_url: "",
  api_key: "",
  max_tokens: "4096",
  max_concurrent_requests: "10",
  is_default: false,
  selected_models: [] as string[],
  default_model: "",
}

export function AddProviderDialog({ open, provider, onOpenChange, onSaved }: AddProviderDialogProps) {
  const [form, setForm] = useState(defaultForm)
  const [showApiKey, setShowApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fetchingModels, setFetchingModels] = useState(false)
  const [availableModels, setAvailableModels] = useState<string[]>([])

  const llmOptions = useProviderTypes().llm

  useEffect(() => {
    if (provider) {
      setForm({
        name: provider.name || "",
        provider: provider.provider || "openai_compatible",
        model: provider.model || "",
        base_url: provider.base_url || "",
        api_key: provider.api_key || "",
        max_tokens: String(provider.max_tokens ?? 4096),
        max_concurrent_requests: String(provider.max_concurrent_requests ?? 10),
        is_default: provider.is_default,
        selected_models: provider.selected_models || (provider.model ? [provider.model] : []),
        default_model: provider.default_model || provider.model || "",
      })
    } else {
      setForm(defaultForm)
    }
    setShowApiKey(false)
    setAvailableModels([])
  }, [provider, open])

  const set = (key: string, value: string | boolean | string[]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const fetchModels = useCallback(async () => {
    if (!form.base_url.trim()) {
      toast.error("Enter a base URL first")
      return
    }
    setFetchingModels(true)
    try {
      const res = await getAvailableModels("llm", {
        base_url: form.base_url,
        api_key: form.api_key || undefined,
      })
      if (res.error) {
        toast.error(res.error)
      } else {
        setAvailableModels(res.models || [])
        if (res.models?.length) {
          toast.success(`Found ${res.models.length} models`)
        } else {
          toast.info("No models returned")
        }
      }
    } catch (err) {
      toast.error(`Failed to fetch models: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setFetchingModels(false)
    }
  }, [form.base_url, form.api_key])

  const toggleModelSelection = (model: string) => {
    setForm((prev) => {
      const selected = prev.selected_models.includes(model)
        ? prev.selected_models.filter((m) => m !== model)
        : [...prev.selected_models, model]
      // If default was removed, reset default
      let defaultModel = prev.default_model
      if (!selected.includes(defaultModel)) {
        defaultModel = selected[0] || ""
      }
      return { ...prev, selected_models: selected, default_model: defaultModel }
    })
  }

  const setDefaultModel = (model: string) => {
    setForm((prev) => ({ ...prev, default_model: model }))
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("Name is required")
      return
    }
    setSaving(true)
    try {
      const data = {
        name: form.name.trim(),
        provider: form.provider,
        model: form.default_model || form.selected_models[0],
        base_url: form.base_url,
        api_key: form.api_key || undefined,
        max_tokens: parseInt(form.max_tokens) || 4096,
        max_concurrent_requests: parseInt(form.max_concurrent_requests) || 10,
        is_default: form.is_default,
        selected_models: form.selected_models,
        default_model: form.default_model || form.selected_models[0],
      }
      if (provider) {
        await updateLLMProvider(provider.id, data)
        toast.success("Provider updated")
      } else {
        await createLLMProvider(data)
        toast.success("Provider created")
      }
      onSaved()
    } catch (err) {
      toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{provider ? "Edit Provider" : "Add Provider"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Name</label>
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="My LLM" />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Provider Type</label>
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={form.provider}
              onChange={(e) => set("provider", e.target.value)}
            >
              {llmOptions.map((p) => (
                <option key={p.name} value={p.name}>{p.display_name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Base URL</label>
            <Input value={form.base_url} onChange={(e) => set("base_url", e.target.value)} placeholder="https://api.openai.com/v1" />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">API Key</label>
            <div className="relative">
              <Input
                type={showApiKey ? "text" : "password"}
                value={form.api_key}
                onChange={(e) => set("api_key", e.target.value)}
                placeholder="sk-..."
              />
              <Button
                variant="ghost"
                size="icon"
                className="absolute right-0 top-0 h-full px-3"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Max Tokens</label>
              <Input value={form.max_tokens} onChange={(e) => set("max_tokens", e.target.value)} placeholder="4096" />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Max Concurrent Requests</label>
              <Input value={form.max_concurrent_requests} onChange={(e) => set("max_concurrent_requests", e.target.value)} placeholder="10" />
            </div>
          </div>

          {/* Fetch Models */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Models</label>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={fetchModels}
                disabled={fetchingModels || !form.base_url.trim()}
              >
                {fetchingModels ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <RefreshCw className="h-3 w-3 mr-1" />
                )}
                Fetch Models
              </Button>
            </div>

            {availableModels.length > 0 && (
              <div className="border rounded-md p-2 max-h-40 overflow-y-auto space-y-1">
                {availableModels.map((model) => (
                  <label key={model} className="flex items-center gap-2 text-sm cursor-pointer px-2 py-1 rounded hover:bg-accent">
                    <input
                      type="checkbox"
                      checked={form.selected_models.includes(model)}
                      onChange={() => toggleModelSelection(model)}
                      className="rounded"
                    />
                    <span className="flex-1 truncate font-mono text-xs">{model}</span>
                    {form.selected_models.includes(model) && (
                      <button
                        type="button"
                        className={`text-[10px] px-1.5 py-0.5 rounded ${
                          form.default_model === model
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground hover:bg-accent"
                        }`}
                        onClick={(e) => {
                          e.preventDefault()
                          setDefaultModel(model)
                        }}
                      >
                        {form.default_model === model ? "default" : "set default"}
                      </button>
                    )}
                  </label>
                ))}
              </div>
            )}

            {availableModels.length === 0 && !fetchingModels && form.selected_models.length > 0 && (
              <div className="border rounded-md p-2 space-y-1">
                {form.selected_models.map((model) => (
                  <label key={model} className="flex items-center gap-2 text-sm cursor-pointer px-2 py-1 rounded hover:bg-accent">
                    <input
                      type="checkbox"
                      checked
                      onChange={() => toggleModelSelection(model)}
                      className="rounded"
                    />
                    <span className="flex-1 truncate font-mono text-xs">{model}</span>
                    <button
                      type="button"
                      className={`text-[10px] px-1.5 py-0.5 rounded ${
                        form.default_model === model
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:bg-accent"
                      }`}
                      onClick={(e) => {
                        e.preventDefault()
                        setDefaultModel(model)
                      }}
                    >
                      {form.default_model === model ? "default" : "set default"}
                    </button>
                  </label>
                ))}
              </div>
            )}

            {form.selected_models.length === 0 && availableModels.length === 0 && !fetchingModels && (
              <p className="text-xs text-muted-foreground">
                Enter base URL and click "Fetch Models", or models will be selected after creation.
              </p>
            )}
          </div>

          <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => set("is_default", e.target.checked)}
              className="rounded"
            />
            Set as default
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : provider ? "Update" : "Create"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
