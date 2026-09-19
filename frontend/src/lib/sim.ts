import { useEffect, useState } from "react"

export type Maneuver = "cruise" | "slow" | "stop" | "overtake"

export interface Hazard {
  id: number
  kind: "van" | "boxes" | "cones" | "branch" | "pedestrian" | "deer" | "dog"
  x: number
  y: number
  l: number
  w: number
  vx: number
  vy: number
  state: string
  text: string
  sudden: boolean
}

export interface OncomingCar {
  id: number
  x: number
  y: number
  v: number
  c: number
}

export interface SimEvent {
  t: number
  kind: string
  text: string
  severity?: string
  sudden?: boolean
}

export interface PlannerStatus {
  name: string
  requests: number
  errors: number
  cost_usd: number
  last_latency_ms: number | null
  p50_latency_ms: number | null
  probabilities: Partial<Record<Maneuver, number>>
  scene: unknown
  error: string | null
}

export interface Snapshot {
  t: number
  ego: { x: number; y: number; v: number; vy: number; a: number; maneuver: Maneuver; phase: string; aeb: boolean; brake: "" | "normal" | "hard" | "emergency" }
  hazards: Hazard[]
  oncoming: OncomingCar[]
  target: number | null
  stats: Record<string, number>
  decision: { maneuver?: Maneuver; source?: string; note?: string; probabilities?: Record<string, number>; latency_ms?: number }
  frozen: boolean
  events: SimEvent[]
  planner: "jev" | "gemini" | "rules"
  planner_status: PlannerStatus
  running: boolean
  seed: number
  jev_available: boolean
  safety_floor: boolean
  eye: "code" | "camera"
  camera: { frame: number; objects: { what: string; where: string; approx_distance_m: number | null; box_2d?: number[]; radar?: string }[]; latency_ms: number | null; cost_usd: number; error: string | null }
  camera_model: string | null
  models: Record<"jev" | "gemini", ModelStatus>
  agreement: { same: number; different: number }
  hazard_settings: { kinds: string[]; interval_s: number; sudden: boolean }
  race: { frame: number | null; answers: Record<string, { choice: string; after_s: number }> }
  view: "chase" | "dash" | "side" | "drone"
  code_ahead: { what: string; distance_m: number; where: string; moving: string }[]
  last_take: string | null
  director: { active: boolean; caption: string; elapsed_s: number | null; last: { action: string; t: number; seq: number; p: number } | null }
}

export interface ModelStatus {
  name: string
  requests: number
  errors: number
  cost_usd: number
  last_latency_ms: number | null
  p50_latency_ms: number | null
  probabilities: Record<string, number>
  error: string | null
  choice: string | null
  why: string | null
  decided_at: number
}

type Listener = (s: Snapshot) => void

export const live = {
  current: null as Snapshot | null,
  receivedAt: 0,
  connected: false,
  listeners: new Set<Listener>(),
  buffer: [] as Snapshot[],
}

export const view = {
  ready: false,
  t: 0,
  ego: { x: 0, y: 0, v: 0, vy: 0, a: 0 },
  hazards: new Map<number, { x: number; y: number; vx: number; vy: number }>(),
  oncoming: new Map<number, { x: number; v: number }>(),
}

const RENDER_DELAY = 0.12

export function setViewExact(s: Snapshot) {
  live.current = s
  live.buffer = [s]
  view.ready = true
  view.t = s.t
  Object.assign(view.ego, { x: s.ego.x, y: s.ego.y, v: s.ego.v, vy: s.ego.vy, a: s.ego.a })
  view.hazards.clear()
  for (const h of s.hazards) view.hazards.set(h.id, { x: h.x, y: h.y, vx: h.vx, vy: h.vy })
  view.oncoming.clear()
  for (const c of s.oncoming) view.oncoming.set(c.id, { x: c.x, v: c.v })
}

export function advanceView(delta: number) {
  const buf = live.buffer
  const latest = buf[buf.length - 1]
  if (!latest) return
  const rate = latest.running && !latest.frozen ? 1 : 0
  const goal = Math.min(latest.t, latest.t + ((performance.now() - live.receivedAt) / 1000) * rate - RENDER_DELAY)
  if (!view.ready || Math.abs(goal - view.t) > 1) {
    view.t = goal
    view.ready = true
  } else {
    view.t += delta * rate
    view.t += (goal - view.t) * Math.min(1, delta * 1.5)
    view.t = Math.min(view.t, latest.t)
  }
  let i = buf.length - 1
  while (i > 0 && buf[i - 1].t > view.t) i--
  const b = buf[i]
  const a = i > 0 ? buf[i - 1] : b
  const span = b.t - a.t
  const f = span > 1e-6 ? Math.min(1, Math.max(0, (view.t - a.t) / span)) : 1
  const mix = (p: number, q: number) => p + (q - p) * f
  view.ego.x = mix(a.ego.x, b.ego.x)
  view.ego.y = mix(a.ego.y, b.ego.y)
  view.ego.v = mix(a.ego.v, b.ego.v)
  view.ego.vy = mix(a.ego.vy, b.ego.vy)
  view.ego.a = mix(a.ego.a, b.ego.a)
  const ha = new Map(a.hazards.map((h) => [h.id, h]))
  view.hazards.clear()
  for (const h of b.hazards) {
    const p = ha.get(h.id) ?? h
    view.hazards.set(h.id, { x: mix(p.x, h.x), y: mix(p.y, h.y), vx: h.vx, vy: h.vy })
  }
  const oa = new Map(a.oncoming.map((c) => [c.id, c]))
  view.oncoming.clear()
  for (const c of b.oncoming) {
    const p = oa.get(c.id) ?? c
    view.oncoming.set(c.id, { x: mix(p.x, c.x), v: mix(p.v, c.v) })
  }
}

let source: EventSource | null = null

export function connect() {
  if (source) return
  source = new EventSource("/stream")
  source.onopen = () => (live.connected = true)
  source.onerror = () => (live.connected = false)
  source.onmessage = (m) => {
    live.current = JSON.parse(m.data) as Snapshot
    live.receivedAt = performance.now()
    const buf = live.buffer
    if (buf.length && live.current.t < buf[buf.length - 1].t) buf.length = 0
    buf.push(live.current)
    if (buf.length > 30) buf.shift()
    live.connected = true
    live.listeners.forEach((l) => l(live.current!))
  }
}

export async function control(body: Record<string, unknown>) {
  const response = await fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  return (await response.json()) as { ok: boolean; error?: string }
}

export function sinceSnapshot() {
  return Math.min(0.15, (performance.now() - live.receivedAt) / 1000)
}

export function useSnapshot(intervalMs = 100) {
  const [snap, setSnap] = useState<Snapshot | null>(live.current)
  useEffect(() => {
    connect()
    let last = 0
    const listener: Listener = (s) => {
      const now = performance.now()
      if (now - last >= intervalMs) {
        last = now
        setSnap(s)
      }
    }
    live.listeners.add(listener)
    return () => {
      live.listeners.delete(listener)
    }
  }, [intervalMs])
  return snap
}

export const LANE_W = 3.5
export const ROAD_RIGHT = -LANE_W / 2
export const ROAD_LEFT = LANE_W * 1.5
export const SPEED_LIMIT_KMH = 50
