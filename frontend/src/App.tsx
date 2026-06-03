import { TooltipProvider } from "@/components/ui/tooltip"
import { AppLayout } from "@/components/layout/app-layout"
import { Toaster } from "sonner"

export default function App() {
  return (
    <TooltipProvider>
      <AppLayout />
      <Toaster position="top-right" richColors />
    </TooltipProvider>
  )
}
