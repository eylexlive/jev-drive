import { BrainCircuitIcon, CarFrontIcon, ClapperboardIcon, PackageIcon, PersonStandingIcon, TruckIcon, CircleIcon, EyeOffIcon, OctagonAlertIcon, PauseIcon, PlayIcon, RotateCcwIcon, SquareIcon, TriangleAlertIcon } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { type Maneuver, type Snapshot, SPEED_LIMIT_KMH, control, useSnapshot } from "@/lib/sim"
import { BrakeOverlay, CameraPanel, PipelineStrip, VersusCard } from "@/components/hud"
import { DirectorOverlay } from "@/components/director"
import { ObstacleMenu } from "@/components/obstacles"
import { useRecorder } from "@/lib/recorder"
import { type CameraMode, World3D } from "@/scene/World3D"

const MANEUVERS: Maneuver[] = ["cruise", "slow", "stop", "overtake"]
const MANEUVER_TEXT: Record<Maneuver, string> = {
  cruise: "text-maneuver-cruise",
  slow: "text-maneuver-slow",
  stop: "text-maneuver-stop",
  overtake: "text-maneuver-overtake",
}

async function send(body: Record<string, unknown>) {
  const result = await control(body)
  if (!result.ok) toast.error(result.error ?? "Request failed")
}

function TitleChip({ snap }: { snap: Snapshot | null }) {
  const eye = snap?.eye === "camera" ? "Gemini camera" : "code-written text"
  const driver = snap?.planner === "gemini" ? "Gemini (LLM)" : snap?.planner === "rules" ? "rules" : "Jev"
  return (
    <div className="pointer-events-auto flex items-center gap-2 rounded-xl bg-card/75 px-3 py-2 ring-1 ring-foreground/10 backdrop-blur-md">
      <CarFrontIcon />
      <span className="font-semibold">Jev Drive</span>
      <Separator orientation="vertical" className="h-4" />
      <span className="text-xs text-muted-foreground">eye: {eye}</span>
      <Badge variant="secondary">
        <BrainCircuitIcon data-icon="inline-start" />
        driver: {driver}
      </Badge>
    </div>
  )
}

interface ControlsProps {
  snap: Snapshot | null
  camera: CameraMode
  setCamera: (c: CameraMode) => void
  recorder: ReturnType<typeof useRecorder>
  onClean: () => void
  share: boolean
  setShare: (on: boolean) => void
  onTake: () => void
}

function IconButton({ label, onClick, children, variant = "outline" }: { label: string; onClick: () => void; children: React.ReactNode; variant?: "outline" | "default" | "destructive" }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button size="icon-sm" variant={variant} onClick={onClick} aria-label={label}>{children}</Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

function Controls({ snap, camera, setCamera, recorder, onClean, share, setShare, onTake }: ControlsProps) {
  const record = () => (recorder.recording ? recorder.stop() : recorder.start({ upload: true }).catch((e: Error) => toast.error(e.message)))
  const clock = `${Math.floor(recorder.seconds / 60)}:${String(recorder.seconds % 60).padStart(2, "0")}`
  const noKey = snap ? !snap.jev_available : false
  return (
    <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-xl bg-card/75 p-1.5 ring-1 ring-foreground/10 backdrop-blur-md">
      <Select value={snap?.planner ?? "jev"} onValueChange={(v) => send({ action: "planner", planner: v })}>
        <SelectTrigger size="sm" className="w-32" aria-label="Driver"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="jev" disabled={noKey}>Driver: Jev</SelectItem>
            <SelectItem value="gemini" disabled={noKey}>Driver: Gemini</SelectItem>
            <SelectItem value="rules">Driver: Rules</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select value={snap?.eye ?? "code"} onValueChange={(v) => send({ action: "eye", eye: v })}>
        <SelectTrigger size="sm" className="w-32" aria-label="Eye"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="camera" disabled={noKey}>Eye: Camera</SelectItem>
            <SelectItem value="code">Eye: Code</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select value={camera} onValueChange={(v) => setCamera(v as CameraMode)}>
        <SelectTrigger id="ctl-view" size="sm" className="w-28" aria-label="View"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="chase">View: Chase</SelectItem>
            <SelectItem value="dash">View: Dash</SelectItem>
            <SelectItem value="side">View: Cinematic</SelectItem>
            <SelectItem value="drone">View: Drone</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <ObstacleMenu snap={snap} />
      <span id="ctl-spawn-van" className="inline-flex rounded-md">
        <IconButton label="Stopped van ahead" onClick={() => send({ action: "spawn", kind: "van", sudden: false })}><TruckIcon /></IconButton>
      </span>
      <span id="ctl-spawn-boxes" className="inline-flex rounded-md">
        <IconButton label="Cargo falls suddenly" onClick={() => send({ action: "spawn", kind: "boxes", sudden: true })}><PackageIcon /></IconButton>
      </span>
      <span id="ctl-spawn-person" className="inline-flex rounded-md">
        <IconButton label="Person steps out suddenly" onClick={() => send({ action: "spawn", kind: "pedestrian", sudden: true })}><PersonStandingIcon /></IconButton>
      </span>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 px-1">
            <Switch id="floor" size="sm" checked={snap?.safety_floor ?? true} onCheckedChange={(on) => send({ action: "floor", on })} />
            <Label htmlFor="floor" className="text-xs">Floor</Label>
          </div>
        </TooltipTrigger>
        <TooltipContent>Safety floor: code-only emergency brake at the last moment</TooltipContent>
      </Tooltip>
      <span id="ctl-pause" className="inline-flex rounded-md">
      <IconButton label={snap?.running ? "Pause" : "Resume"} onClick={() => send({ action: snap?.running ? "pause" : "resume" })}>
        {snap?.running ? <PauseIcon /> : <PlayIcon />}
      </IconButton>
      </span>
      <IconButton label="New road" onClick={() => send({ action: "reset" })}><RotateCcwIcon /></IconButton>
      <IconButton label="Clean view for filming (H)" onClick={onClean}><EyeOffIcon /></IconButton>
      <div className="flex items-center gap-1.5 px-1">
        <Switch id="share" size="sm" checked={share} onCheckedChange={setShare} />
        <Label htmlFor="share" className="text-xs">Share</Label>
      </div>
      <Button size="sm" variant="secondary" onClick={onTake} disabled={snap?.director?.active}>
        <ClapperboardIcon data-icon="inline-start" />
        Jev directs
      </Button>
      <Button id="ctl-record" size="sm" variant={recorder.recording ? "destructive" : "default"} onClick={record}>
        {recorder.recording ? <SquareIcon data-icon="inline-start" /> : <CircleIcon data-icon="inline-start" />}
        {recorder.recording ? clock : "Record"}
      </Button>
    </div>
  )
}

function Speed({ snap }: { snap: Snapshot }) {
  const kmh = Math.round(snap.ego.v * 3.6)
  const brake = snap.ego.brake
  return (
    <Card size="sm" className="pointer-events-auto w-36 bg-card/80 backdrop-blur-md">
      <CardContent className="flex flex-col gap-1.5">
        <span className="text-[11px] tracking-wide text-muted-foreground uppercase">Speed</span>
        <span className="flex items-baseline gap-1 text-4xl leading-none font-semibold tabular-nums">
          {kmh}<span className="text-xs font-normal text-muted-foreground">km/h</span>
        </span>
        <Progress value={Math.min(100, (kmh / SPEED_LIMIT_KMH) * 100)} aria-label="Speed against the limit" />
        {brake === "emergency" || brake === "hard" ? <Badge variant="destructive">{brake} brake</Badge>
          : <Badge variant="outline">{snap.ego.phase ? "overtaking" : brake === "normal" ? "braking" : `limit ${SPEED_LIMIT_KMH}`}</Badge>}
      </CardContent>
    </Card>
  )
}

function Decision({ snap }: { snap: Snapshot }) {
  const status = snap.planner_status
  const current: Maneuver = snap.ego.phase ? "overtake" : snap.ego.maneuver
  const probs = status.probabilities ?? {}
  const top = MANEUVERS.reduce((a, b) => ((probs[b] ?? 0) > (probs[a] ?? 0) ? b : a), MANEUVERS[0])
  const isJev = snap.planner === "jev"
  return (
    <Card size="sm" className="pointer-events-auto w-80 max-w-full bg-card/80 backdrop-blur-md lg:w-[26rem]">
      <CardHeader>
        <CardDescription>{isJev ? "Jev's decision" : "Rule planner's decision"}</CardDescription>
        <CardAction>
          {isJev && status.last_latency_ms != null && <Badge variant="outline">{Math.round(status.last_latency_ms)} ms</Badge>}
        </CardAction>
        <CardTitle className={cn("text-4xl font-bold tracking-tight uppercase", MANEUVER_TEXT[current])}>{current}</CardTitle>
        {snap.decision?.note && <CardDescription>{snap.decision.note}</CardDescription>}
      </CardHeader>
      {isJev && (
        <CardContent className="hidden flex-col gap-2 md:flex">
          {MANEUVERS.map((m) => (
            <div key={m} className="grid grid-cols-[5.5rem_1fr_2.5rem] items-center gap-3 text-sm">
              <span className={cn("capitalize", m === top ? "font-semibold text-foreground" : "text-muted-foreground")}>{m}</span>
              <Progress value={(probs[m] ?? 0) * 100} aria-label={`${m} probability`} />
              <span className="text-right tabular-nums text-muted-foreground">{(probs[m] ?? 0).toFixed(2)}</span>
            </div>
          ))}
        </CardContent>
      )}
      <CardFooter className="flex flex-wrap gap-x-4 gap-y-1 border-t text-xs text-muted-foreground">
        {isJev ? (
          <>
            <span>median {status.p50_latency_ms != null ? `${Math.round(status.p50_latency_ms)} ms` : "-"}</span>
            <span>{status.requests} requests</span>
            <span>${status.cost_usd.toFixed(4)}</span>
            {status.error && <span className="text-destructive">error: {status.error}</span>}
          </>
        ) : (
          <span>decides every 0.5 s, instantly</span>
        )}
      </CardFooter>
    </Card>
  )
}

function Stats({ snap }: { snap: Snapshot }) {
  const s = snap.stats
  const items: [string, string | number, boolean?][] = [
    ["km", (s.distance_m / 1000).toFixed(2)],
    ["hazards", s.hazards],
    ["sudden", s.sudden ?? 0],
    ["overtakes", s.overtakes],
    ["safety floor", s.safety_floor, s.safety_floor > 0],
    ["crashes", s.crashes, s.crashes > 0],
    ["violations", s.violations, s.violations > 0],
  ]
  return (
    <Card size="sm" className="pointer-events-auto bg-card/75 backdrop-blur-md">
      <CardContent className="flex items-center gap-4">
        {items.map(([label, value, bad], i) => (
          <div key={label} className="flex items-center gap-4">
            {i > 0 && <Separator orientation="vertical" className="h-8" />}
            <div className="flex flex-col">
              <span className={cn("text-lg font-semibold tabular-nums", bad && "text-destructive")}>{value}</span>
              <span className="text-[11px] tracking-wide text-muted-foreground uppercase">{label}</span>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function SceneText({ snap }: { snap: Snapshot }) {
  return (
    <Card size="sm" className="pointer-events-auto min-h-0 flex-1 bg-card/75 backdrop-blur-md">
      <CardHeader>
        <CardTitle>What the driver reads</CardTitle>
        <CardDescription>The exact request body. No images, no hidden intentions.</CardDescription>
      </CardHeader>
      <CardContent className="min-h-0 flex-1">
        <ScrollArea className="h-full max-h-72">
          <pre className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
            {snap.planner_status.scene ? JSON.stringify(snap.planner_status.scene, null, 1) : "Waiting for the first request..."}
          </pre>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

function Events({ snap }: { snap: Snapshot }) {
  const events = [...snap.events].reverse()
  return (
    <Card size="sm" className="pointer-events-auto min-h-0 flex-1 bg-card/75 backdrop-blur-md">
      <CardHeader>
        <CardTitle>Events</CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1">
        <ScrollArea className="h-full max-h-64">
          <ul className="flex flex-col gap-2">
            {events.map((e, i) => (
              <li key={`${e.t}-${i}`} className="grid grid-cols-[3rem_1fr] gap-2 text-xs">
                <span className="tabular-nums text-muted-foreground">{e.t.toFixed(1)}s</span>
                <span className="flex flex-wrap items-center gap-1.5">
                  {["safety", "crash", "violation", "brake"].includes(e.kind) && <Badge variant="destructive">{e.kind}</Badge>}
                  {e.kind === "spawn" && <Badge variant={e.sudden ? "destructive" : "secondary"}>{e.sudden ? "sudden" : "hazard"}</Badge>}
                  {e.kind === "overtake" && <Badge variant="secondary">overtake</Badge>}
                  <span className={cn(e.kind === "maneuver" || e.kind === "clear" ? "text-muted-foreground" : "text-foreground")}>{e.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

function CameraWorker() {
  return (
    <iframe src="/?render=1&embed=1" title="Camera renderer" aria-hidden className="pointer-events-none fixed bottom-0 left-0 origin-bottom-left border-0 opacity-0"
      style={{ width: 1280, height: 720, transform: "scale(0.02)" }} />
  )
}

function Banner({ snap }: { snap: Snapshot }) {
  const target = snap.hazards.find((h) => h.id === snap.target)
  if (snap.frozen)
    return (
      <Alert variant="destructive" className="pointer-events-auto w-[28rem] max-w-full bg-card/90 backdrop-blur-md">
        <OctagonAlertIcon />
        <AlertTitle>Collision</AlertTitle>
        <AlertDescription>The car hit something. Counted as a crash; the run continues.</AlertDescription>
      </Alert>
    )
  if (snap.ego.brake === "emergency" || snap.ego.brake === "hard") return null
  const seen = snap.eye === "camera"
    ? snap.camera.objects.find((o) => (o.where === "in my lane" || o.where === "across both lanes") && !o.radar?.startsWith("ignored"))?.what
    : target?.text
  if (target && seen && snap.ego.maneuver === "stop" && snap.ego.v > 1 && !snap.ego.phase)
    return (
      <Alert className="pointer-events-auto w-[28rem] max-w-full bg-card/90 backdrop-blur-md">
        <TriangleAlertIcon />
        <AlertTitle>{snap.planner === "jev" ? "Jev" : snap.planner === "gemini" ? "Gemini" : "Rules"}: stop</AlertTitle>
        <AlertDescription>{snap.eye === "camera" ? `camera: ${seen}` : seen}</AlertDescription>
      </Alert>
    )
  return null
}

function useEventToasts(snap: Snapshot | null) {
  const seen = useRef(new Set<string>())
  useEffect(() => {
    if (!snap) return
    for (const e of snap.events) {
      const key = `${snap.seed}-${e.t}-${e.text}`
      if (seen.current.has(key)) continue
      seen.current.add(key)
      if (e.kind === "spawn") (e.sudden ? toast.warning : toast)(e.text)
      if (e.kind === "crash") toast.error(e.text)
    }
  }, [snap])
}

const EYE_NOTE = {
  code: ["Eye: code (ground truth)", "No camera. The simulator writes the scene as text straight from its own data; Jev decides on that."],
  camera: ["Eye: Gemini camera", "Each camera frame is sent to Gemini, which describes it in words; radar adds distances. Jev decides on that text."],
} as const

export default function App() {
  const snap = useSnapshot(100)
  const [clean, setClean] = useState(false)
  const [share, setShare] = useState(false)
  const recorder = useRecorder()
  useEffect(() => {
    const onSaved = (e: Event) => {
      const path = (e as CustomEvent<{ path?: string }>).detail?.path
      if (path) toast.success(`Saving the video to ${path.replace(/^.*\/Downloads\//, "Downloads/")} (ready in a minute or two)`)
    }
    window.addEventListener("take-saved", onSaved)
    return () => window.removeEventListener("take-saved", onSaved)
  }, [])
  const eyeNow = snap?.eye
  const runningNow = snap?.running
  useEffect(() => {
    if (!eyeNow || !runningNow) return
    const [title, description] = EYE_NOTE[eyeNow === "camera" ? "camera" : "code"]
    toast(title, { id: "eye-note", description, duration: 2000 })
  }, [eyeNow, runningNow])
  const camera: CameraMode = snap?.view ?? "chase"
  const setCamera = (v: CameraMode) => send({ action: "view", view: v })
  const startTake = async () => {
    setShare(true)
    setClean(false)
    const w = window as unknown as { __takeStatus?: string }
    try {
      await recorder.start({ upload: true })
      w.__takeStatus = "recording"
    } catch (e) {
      w.__takeStatus = `recording failed: ${(e as Error).message}`
      toast.error(`Recording not started: ${(e as Error).message}`)
    }
    await send({ action: "director", on: true })
  }
  useEffect(() => {
    ;(window as unknown as { __startTake?: () => Promise<void> }).__startTake = startTake
  })
  const wasDirecting = useRef(false)
  useEffect(() => {
    const active = !!snap?.director?.active
    if (wasDirecting.current && !active && recorder.recording) {
      setTimeout(() => recorder.stop(), 2500)
    }
    wasDirecting.current = active
  }, [snap?.director?.active, recorder])
  useEventToasts(snap)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "h" && !(e.target instanceof HTMLInputElement)) setClean((c) => !c)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])
  const connected = useMemo(() => !!snap, [snap])
  const models = snap && snap.planner !== "rules" && snap.models?.jev && snap.models?.gemini
  return (
    <div className="relative h-dvh w-full overflow-hidden bg-background">
      {snap?.eye === "camera" && <CameraWorker />}
      <div className="absolute inset-0">
        <World3D snap={snap} mode={camera} labels={snap?.eye !== "camera"} />
      </div>
      {snap && <BrakeOverlay snap={snap} />}
      {snap && <DirectorOverlay snap={snap} />}
      <div className="pointer-events-none absolute inset-0 grid grid-rows-[auto_minmax(0,1fr)_auto] gap-3 p-3">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <TitleChip snap={snap} />
            {clean ? (recorder.recording ? <Badge variant="destructive" className="pointer-events-auto">REC {recorder.seconds}s</Badge> : <span />)
              : <Controls snap={snap} camera={camera} setCamera={setCamera} recorder={recorder} onClean={() => setClean(true)}
                share={share} setShare={setShare} onTake={startTake} />}
          </div>
          {snap && <div className="flex justify-center"><PipelineStrip snap={snap} share={share} /></div>}
        </div>
        <div className="relative flex min-h-0 justify-end">
          {snap?.eye === "camera" && <CameraPanel snap={snap} compact />}
          {snap && !clean && snap.eye !== "camera" && (
            <div className="hidden min-h-0 w-96 flex-col gap-3 xl:flex">
              <SceneText snap={snap} />
              <Events snap={snap} />
            </div>
          )}
          {snap && (
            <div className="pointer-events-none absolute inset-x-0 top-2 flex justify-center px-4">
              <Banner snap={snap} />
            </div>
          )}
        </div>
        {snap ? (
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap items-end gap-3">
              <Speed snap={snap} />
              {models ? <VersusCard snap={snap} share={share} /> : <Decision snap={snap} />}
            </div>
            {!clean && !share && <div className="hidden 2xl:block"><Stats snap={snap} /></div>}
          </div>
        ) : (
          <div className="flex justify-center">
            <Badge variant="outline" className="pointer-events-auto bg-background/80">
              {connected ? "Loading..." : "Connecting to the simulation at /stream..."}
            </Badge>
          </div>
        )}
      </div>
      <p className="pointer-events-none absolute right-3 bottom-1 text-[10px] text-muted-foreground/70">
        Car model "Classic Muscle car" by Alexus16 (CC-BY-4.0) via pmndrs/racing-game (MIT)
      </p>
    </div>
  )
}
