import { useEffect, useRef, useState } from "react"

import { type Snapshot, setViewExact } from "@/lib/sim"
import { World3D } from "@/scene/World3D"

interface Job {
  id: string
  snapshot: Snapshot
}

const nextFrame = () => new Promise((r) => requestAnimationFrame(() => r(null)))
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export default function RenderMode() {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [done, setDone] = useState(0)
  const wrapper = useRef<HTMLDivElement>(null!)
  useEffect(() => {
    let alive = true
    ;(async () => {
      while (alive) {
        let job: Job | null = null
        try {
          const r = await fetch("/render/next")
          if (r.status === 200) job = await r.json()
        } catch {
          await sleep(500)
        }
        if (!job) {
          await sleep(50)
          continue
        }
        setViewExact(job.snapshot)
        setSnap(job.snapshot)
        for (let i = 0; i < 4; i++) await nextFrame()
        await sleep(30)
        const canvas = wrapper.current.querySelector("canvas")!
        const jpeg = canvas.toDataURL("image/jpeg", 0.88)
        await fetch("/render/result", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: job.id, jpeg }) })
        setDone((d) => d + 1)
      }
    })()
    return () => {
      alive = false
    }
  }, [])
  const embedded = new URLSearchParams(location.search).has("embed")
  if (embedded)
    return (
      <div ref={wrapper} style={{ width: 1280, height: 720 }}>
        <World3D snap={snap} mode="dash" render />
      </div>
    )
  return (
    <div className="flex h-dvh w-full flex-col items-center justify-center gap-2 bg-background text-sm text-muted-foreground">
      <div ref={wrapper} style={{ width: 1280, height: 720 }}>
        <World3D snap={snap} mode="dash" render />
      </div>
      <span>Render worker: {done} frames. Keep this tab visible while an evaluation runs.</span>
    </div>
  )
}
