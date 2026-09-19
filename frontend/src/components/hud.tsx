import { ArrowRightIcon, BrainCircuitIcon, CameraIcon, CarFrontIcon, EyeIcon, ZapIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { type Maneuver, type Snapshot } from "@/lib/sim"
import { cn } from "@/lib/utils"

const MANEUVER_TEXT: Record<Maneuver, string> = {
  cruise: "text-maneuver-cruise",
  slow: "text-maneuver-slow",
  stop: "text-maneuver-stop",
  overtake: "text-maneuver-overtake",
}

function usePulse(key: unknown, ms = 700) {
  const [on, setOn] = useState(false)
  const first = useRef(true)
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    setOn(true)
    const id = setTimeout(() => setOn(false), ms)
    return () => clearTimeout(id)
  }, [key, ms])
  return on
}

function Step({ icon: Icon, title, detail, pulse, accent }: { icon: typeof CameraIcon; title: string; detail: string; pulse: boolean; accent?: string }) {
  return (
    <div className={cn("flex min-w-0 items-center gap-2 rounded-lg px-2.5 py-1.5 ring-1 ring-foreground/10 transition-colors duration-300",
      pulse ? "bg-primary/20 ring-primary/50" : "bg-card/60")}>
      <Icon className={cn("shrink-0", pulse && "animate-pulse")} />
      <div className="flex min-w-0 flex-col leading-tight">
        <span className="text-[11px] tracking-wide text-muted-foreground uppercase">{title}</span>
        <span className={cn("truncate text-sm font-semibold", accent)}>{detail}</span>
      </div>
    </div>
  )
}

export function PipelineStrip({ snap, share = false }: { snap: Snapshot; share?: boolean }) {
  const driver = snap.planner
  const model = snap.models?.[driver as "jev" | "gemini" | "gemini_vision"]
  const cam = snap.camera
  const m: Maneuver = snap.ego.phase ? "overtake" : snap.ego.maneuver
  const camPulse = usePulse(cam.frame)
  const decidePulse = usePulse(model?.decided_at)
  const actPulse = usePulse(m)
  const camera = snap.eye === "camera" || driver === "gemini_vision"
  if (driver === "gemini_vision")
    return (
      <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-xl bg-card/70 p-1.5 backdrop-blur-md ring-1 ring-foreground/10">
        <Step icon={CameraIcon} title="Camera" detail={`frame ${cam.frame}`} pulse={camPulse} />
        <ArrowRightIcon className="text-muted-foreground" />
        <Step icon={BrainCircuitIcon} title="Gemini sees and decides" pulse={decidePulse}
          detail={share ? (model?.choice ?? "...").toUpperCase() : model?.last_latency_ms != null ? `${(model.last_latency_ms / 1000).toFixed(1)} s` : "..."} />
        <ArrowRightIcon className="text-muted-foreground" />
        <Step icon={CarFrontIcon} title="Car" detail={snap.ego.aeb ? "EMERGENCY BRAKE" : m.toUpperCase()} pulse={actPulse}
          accent={snap.ego.aeb ? "text-destructive" : MANEUVER_TEXT[m]} />
      </div>
    )
  return (
    <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-xl bg-card/70 p-1.5 backdrop-blur-md ring-1 ring-foreground/10">
      <Step icon={CameraIcon} title="Camera" detail={camera ? `frame ${cam.frame}` : "off (code eye)"} pulse={camera && camPulse} />
      <ArrowRightIcon className="text-muted-foreground" />
      <Step icon={EyeIcon} title={camera ? "Gemini sees" : "Code describes"} pulse={camPulse && camera}
        detail={share ? (camera ? `${cam.objects.filter((o) => !o.radar?.startsWith("ignored")).length} things` : "text") : camera ? (cam.latency_ms != null ? `${(cam.latency_ms / 1000).toFixed(1)} s` : "...") : "instant"} />
      <ArrowRightIcon className="text-muted-foreground" />
      <Step icon={driver === "jev" ? ZapIcon : BrainCircuitIcon} pulse={decidePulse}
        title={driver === "jev" ? "Jev decides" : driver === "gemini" ? "Gemini decides" : "Rules decide"}
        detail={share ? (model?.choice ?? "...").toUpperCase() : model?.last_latency_ms != null ? `${Math.round(model.last_latency_ms)} ms` : driver === "rules" ? "instant" : "..."} />
      <ArrowRightIcon className="text-muted-foreground" />
      <Step icon={CarFrontIcon} title="Car" detail={snap.ego.aeb ? "EMERGENCY BRAKE" : m.toUpperCase()} pulse={actPulse}
        accent={snap.ego.aeb ? "text-destructive" : MANEUVER_TEXT[m]} />
    </div>
  )
}

const BOX_COLOUR = (what: string) => {
  const w = what.toLowerCase()
  if (/(person|pedestrian|man|woman|child|jogger|someone|people|deer|dog|animal|stag|doe|buck)/.test(w)) return "var(--maneuver-stop)"
  if (/(car|vehicle|truck|van|lorry|bus)/.test(w)) return "var(--maneuver-overtake)"
  return "var(--maneuver-slow)"
}

export function CameraPanel({ snap, compact = false }: { snap: Snapshot; compact?: boolean }) {
  const cam = snap.camera
  const age = snap.planner_status.scene && typeof (snap.planner_status.scene as Record<string, unknown>).camera_report_age_s === "number"
    ? (snap.planner_status.scene as Record<string, number>).camera_report_age_s : null
  const scene = (snap.planner_status.scene ?? {}) as Record<string, unknown>
  const radarPath = scene.nearest_radar_object_in_your_path as { distance_m: number } | undefined
  const kept = cam.objects.filter((o) => !o.radar?.startsWith("ignored"))
  const cameraInLane = kept.some((o) => o.where === "in my lane" || o.where === "across both lanes")
  const disagree = cameraInLane !== !!radarPath
  const W = compact ? 340 : 384
  const H = (W * 9) / 16
  return (
    <Card size="sm" className="pointer-events-auto bg-card/80 backdrop-blur-md" style={{ width: W + 26 }}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <EyeIcon />
          What Gemini sees
        </CardTitle>
        <CardAction className="flex gap-1.5">
          <Badge variant="destructive" className="gap-1">
            <span className="size-1.5 animate-pulse rounded-full bg-current" />
            LIVE
          </Badge>
          {age != null && <Badge variant="outline">{age.toFixed(1)} s old</Badge>}
        </CardAction>
        {!compact && <CardDescription>{snap.camera_model?.split("/").pop()} reads each windscreen frame. The driver only gets its words plus a radar.</CardDescription>}
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        <div className="relative overflow-hidden rounded-md bg-muted ring-1 ring-foreground/10" style={{ width: W, height: H }}>
          {cam.frame > 0 && <img src={`/camera/latest.jpg?f=${cam.frame}`} alt="Windscreen frame the vision model described" width={W} height={H} className="block" />}
          <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 size-full">
            {cam.objects.map((o, i) => {
              if (!o.box_2d) return null
              const [y0, x0, y1, x1] = o.box_2d
              const confirmed = !o.radar || o.radar.startsWith("confirmed")
              const colour = confirmed ? BOX_COLOUR(o.what) : "var(--muted-foreground)"
              return (
                <g key={i}>
                  <rect x={x0} y={y0} width={Math.max(4, x1 - x0)} height={Math.max(4, y1 - y0)} fill="none" stroke={colour}
                    strokeWidth={confirmed ? 2.5 : 1.5} strokeDasharray={confirmed ? undefined : "4 3"} vectorEffect="non-scaling-stroke" />
                </g>
              )
            })}
          </svg>
          {cam.objects.map((o, i) =>
            o.box_2d && !compact ? (
              <span key={i} className="absolute max-w-[60%] truncate rounded-sm px-1 text-[10px] font-semibold text-black"
                style={{ left: `${o.box_2d[1] / 10}%`, top: `max(0px, calc(${o.box_2d[0] / 10}% - 14px))`, background: BOX_COLOUR(o.what) }}>
                {o.what.split(",")[0]}
              </span>
            ) : null,
          )}
          <div className="scanline pointer-events-none absolute inset-x-0 h-8" />
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <Badge variant="outline">Radar: {radarPath ? `object in your lane, ${radarPath.distance_m} m` : "your lane clear"}</Badge>
          {disagree && <Badge variant="destructive">camera and radar disagree</Badge>}
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] tracking-wide text-muted-foreground uppercase">Code knows (perfect eye)</span>
            {snap.code_ahead.length === 0 && <span className="text-muted-foreground">nothing within 130 m</span>}
            {snap.code_ahead.slice(0, 3).map((o, i) => (
              <span key={i} className="line-clamp-2">{o.what} <span className="text-muted-foreground">· {o.where} · {o.distance_m} m</span></span>
            ))}
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] tracking-wide text-muted-foreground uppercase">Gemini sees (what Jev reads)</span>
            {cam.objects.filter((o) => !o.radar?.startsWith("ignored")).length === 0 && <span className="text-muted-foreground">nothing reported</span>}
            {cam.objects.filter((o) => !o.radar?.startsWith("ignored")).slice(0, 3).map((o, i) => (
              <span key={i} className="line-clamp-2">{o.what} <span className="text-muted-foreground">· {o.where}{o.radar?.startsWith("confirmed") ? ` · ${o.radar.replace("confirmed at ", "")}` : ""}</span></span>
            ))}
          </div>
        </div>
        {!compact && (
          <ul className="flex flex-col gap-1 text-xs">
            {cam.objects.length === 0 && <li className="text-muted-foreground">Nothing reported on or near the road.</li>}
            {cam.objects.slice(0, compact ? 3 : 5).map((o, i) => (
              <li key={i} className={cn("flex flex-wrap items-center gap-1.5", o.radar && !o.radar.startsWith("confirmed") && "opacity-60",
                o.radar?.startsWith("ignored") && "line-through")}>
                <Badge variant="secondary">{o.where}</Badge>
                <span className="truncate">{o.what}</span>
                {o.radar ? (o.radar.startsWith("confirmed")
                  ? <Badge variant="outline">radar ✓ {o.radar.replace("confirmed at ", "")}</Badge>
                  : o.radar.startsWith("ignored") ? <Badge variant="outline">ignored: radar sees no vehicle</Badge>
                  : <Badge variant="destructive">not confirmed by radar</Badge>)
                  : o.approx_distance_m != null && <span className="text-muted-foreground">~{o.approx_distance_m} m</span>}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function ModelColumn({ label, icon: Icon, st, driving, maxLatency, sub, race, share }: {
  label: string; icon: typeof ZapIcon; st?: Snapshot["models"]["jev"]; driving: boolean; maxLatency: number; sub: string
  race?: { after_s: number; first: boolean }; share?: boolean
}) {
  const choice = st?.choice as Maneuver | undefined
  const perDecision = st && st.requests ? st.cost_usd / st.requests : 0
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      <div className="flex items-center gap-2">
        <Icon />
        <span className="font-semibold">{label}</span>
        {driving ? <Badge>driving</Badge> : <Badge variant="outline">shadow</Badge>}
        {race?.first && !share && <Badge variant="secondary">first</Badge>}
      </div>
      <span className="truncate text-[11px] text-muted-foreground">{sub}</span>
      <span className={cn("text-2xl leading-none font-bold uppercase", choice ? MANEUVER_TEXT[choice] : "text-muted-foreground")}>{choice ?? "..."}</span>
      {!share && <div className="flex flex-col gap-1">
        <div className="flex justify-between text-xs"><span className="text-muted-foreground">answered after</span><span className="tabular-nums">{race ? `${race.after_s.toFixed(2)} s` : st?.last_latency_ms != null ? `${(st.last_latency_ms / 1000).toFixed(2)} s` : "-"}</span></div>
        <Progress value={st?.last_latency_ms ? Math.min(100, (st.last_latency_ms / maxLatency) * 100) : 0} aria-label={`${label} answer time`} />
      </div>}
      {!share && <div className="flex justify-between text-xs"><span className="text-muted-foreground">per decision</span><span className="tabular-nums">${perDecision.toFixed(6)}</span></div>}
      {st?.why && <span className="line-clamp-1 text-xs text-muted-foreground italic">"{st.why}"</span>}
    </div>
  )
}

export function VersusCard({ snap, share = false }: { snap: Snapshot; share?: boolean }) {
  const jev = snap.models?.jev
  const gem = snap.models?.gemini
  if (!jev || !gem || snap.planner === "rules") return null
  const maxLatency = Math.max(1000, jev.last_latency_ms ?? 0, gem.last_latency_ms ?? 0)
  const total = snap.agreement.same + snap.agreement.different
  const answers = snap.race?.answers ?? {}
  const both = answers.jev && answers.gemini
  const race = (name: "jev" | "gemini") => answers[name]
    ? { after_s: answers[name].after_s, first: !!both && answers[name].after_s <= answers[name === "jev" ? "gemini" : "jev"].after_s }
    : undefined
  return (
    <Card size="sm" className="pointer-events-auto w-[30rem] max-w-full bg-card/80 backdrop-blur-md">
      <CardHeader>
        <CardTitle>Same scene, two deciders</CardTitle>
        <CardDescription>Both get the same report at the same moment. Decision model (System 1) vs general LLM (System 2)</CardDescription>
        {total > 0 && !share && <CardAction><Badge variant="outline">agree {Math.round((100 * snap.agreement.same) / total)}%</Badge></CardAction>}
      </CardHeader>
      <CardContent className="flex gap-4">
        <ModelColumn label="Jev" icon={ZapIcon} st={jev} driving={snap.planner === "jev"} maxLatency={maxLatency} sub="typed decision, no text generation" race={race("jev")} share={share} />
        <Separator orientation="vertical" />
        <ModelColumn label="Gemini" icon={BrainCircuitIcon} st={gem} driving={snap.planner === "gemini"} maxLatency={maxLatency} sub="generates an answer as text" race={race("gemini")} share={share} />
      </CardContent>
    </Card>
  )
}

export function BrakeOverlay({ snap }: { snap: Snapshot }) {
  const kind = snap.ego.brake === "emergency" ? "emergency" : snap.ego.brake === "hard" ? "hard" : null
  const previous = useRef<typeof kind>(null)
  const [shown, setShown] = useState<{ kind: "emergency" | "hard"; id: number } | null>(null)
  useEffect(() => {
    if (kind && kind !== previous.current && !(previous.current === "emergency" && kind === "hard")) {
      const id = Date.now()
      setShown({ kind, id })
      const t = setTimeout(() => setShown((s) => (s?.id === id ? null : s)), 750)
      previous.current = kind
      return () => clearTimeout(t)
    }
    previous.current = kind
  }, [kind])
  if (!shown) return null
  const emergency = shown.kind === "emergency"
  const who = emergency ? "Safety floor (code) - reacts in milliseconds" : `${snap.planner === "jev" ? "Jev" : snap.planner === "rules" ? "Rules" : "Gemini"} chose STOP - hard braking`
  return (
    <div key={shown.id} className="brake-flash pointer-events-none absolute inset-0 flex items-center justify-center">
      <div className={cn("absolute inset-0", emergency ? "brake-vignette-red" : "brake-vignette-amber")} />
      <div className="relative flex flex-col items-center gap-2 rounded-2xl bg-black/55 px-8 py-5 backdrop-blur-sm">
        <svg viewBox="0 0 120 100" className={cn("h-20 w-24", emergency ? "text-destructive" : "text-maneuver-slow")}>
          <circle cx="60" cy="50" r="30" fill="none" stroke="currentColor" strokeWidth="8" />
          <path d="M22 18 A45 45 0 0 0 22 82" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" />
          <path d="M98 18 A45 45 0 0 1 98 82" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" />
          <rect x="55" y="30" width="10" height="26" rx="3" fill="currentColor" />
          <circle cx="60" cy="67" r="5.5" fill="currentColor" />
        </svg>
        <span className={cn("text-3xl font-black tracking-wider", emergency ? "text-destructive" : "text-maneuver-slow")}>
          {emergency ? "EMERGENCY BRAKE" : "HARD BRAKE"}
        </span>
        <span className="text-sm text-white/85">{who}</span>
      </div>
    </div>
  )
}
