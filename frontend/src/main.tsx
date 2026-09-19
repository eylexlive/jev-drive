import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App.tsx"
import RenderMode from "./RenderMode.tsx"
import { ThemeProvider } from "@/components/theme-provider.tsx"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="jev-drive-theme">
      <TooltipProvider>
        {new URLSearchParams(location.search).has("render") ? <RenderMode /> : <App />}
        <Toaster theme="dark" position="top-center" visibleToasts={3} />
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>
)
