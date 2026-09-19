import { ClapperboardIcon, MousePointer2Icon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { type Snapshot } from "@/lib/sim"
import { cn } from "@/lib/utils"

const TARGET: Record<string, string> = {
  view_dash: "ctl-view", view_chase: "ctl-view", view_cinematic: "ctl-view",
  spawn_van: "ctl-spawn-van", spawn_boxes: "ctl-spawn-boxes", spawn_person: "ctl-spawn-person", finish: "ctl-pause",
}
const LABEL: Record<string, string> = {
  view_dash: "View: Dash", view_chase: "View: Chase", view_cinematic: "View: Cinematic",
  spawn_van: "Stopped van", spawn_boxes: "Sudden cargo", spawn_person: "Sudden person", finish: "Pause - that's a wrap",
}

export function DirectorOverlay({ snap }: { snap: Snapshot }) {
  const d = snap.director
  const [cursor, setCursor] = useState<{ x: number; y: number; label: string; pressing: boolean } | null>(null)
  const seq = useRef(0)
  useEffect(() => {
    const last = d?.last
    if (!last || last.seq === seq.current) return
    seq.current = last.seq
    const el = document.getElementById(TARGET[last.action] ?? "")
    if (!el) return
    const r = el.getBoundingClientRect()
    const appear = setTimeout(() => setCursor((c) => ({ x: c?.x ?? window.innerWidth / 2, y: c?.y ?? window.innerHeight / 2, label: LABEL[last.action], pressing: false })), 0)
    const move = setTimeout(() => setCursor({ x: r.left + r.width / 2, y: r.top + r.height / 2, label: LABEL[last.action], pressing: false }), 30)
    const press = setTimeout(() => {
      setCursor((c) => (c ? { ...c, pressing: true } : c))
      el.classList.add("jev-pressed")
    }, 700)
    const release = setTimeout(() => {
      setCursor((c) => (c ? { ...c, pressing: false } : c))
      el.classList.remove("jev-pressed")
    }, 1300)
    return () => [appear, move, press, release].forEach(clearTimeout)
  }, [d?.last])

  if (!d || (!d.active && !d.caption)) return null
  return (
    <>
      {d.active && (
        <div className="pointer-events-none absolute top-3 left-1/2 z-50 -translate-x-1/2">
          <Badge className="h-7 gap-1.5 px-3 text-sm">
            <ClapperboardIcon data-icon="inline-start" />
            Directed by Jev · {Math.floor(d.elapsed_s ?? 0)} s
          </Badge>
        </div>
      )}
      {d.caption && (
        <div className="pointer-events-none absolute inset-x-0 bottom-40 z-40 flex justify-center px-6">
          <div key={d.caption} className="caption-in max-w-3xl rounded-xl bg-black/70 px-5 py-3 text-center text-xl font-semibold text-white backdrop-blur-sm">
            {d.caption}
          </div>
        </div>
      )}
      {cursor && (
        <div className="pointer-events-none fixed z-[60] transition-all duration-700 ease-out" style={{ left: cursor.x, top: cursor.y }}>
          <MousePointer2Icon className={cn("size-7 fill-white stroke-black drop-shadow", cursor.pressing && "scale-90")} />
          <span className={cn("absolute -top-1 left-7 rounded-full bg-primary px-2 py-0.5 text-xs font-bold whitespace-nowrap text-primary-foreground shadow",
            cursor.pressing && "ring-4 ring-primary/40")}>
            Jev: {cursor.label}
          </span>
          {cursor.pressing && <span className="absolute -top-3 -left-3 size-12 animate-ping rounded-full bg-primary/40" />}
        </div>
      )}
    </>
  )
}
