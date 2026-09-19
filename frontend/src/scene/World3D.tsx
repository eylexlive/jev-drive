import { Environment, Lightformer, Sky } from "@react-three/drei"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing"
import { Suspense, useRef } from "react"
import * as THREE from "three"

import { LANE_W, type Snapshot, advanceView, live, view } from "@/lib/sim"

import { Car, type CarHandle, WHEEL_RADIUS } from "./Car"
import { Hazards } from "./Hazards"
import { Road } from "./Road"

export type CameraMode = "chase" | "side" | "drone" | "dash"

const PAINTS = ["#c92a2a", "#e8590c", "#7048e8", "#dee2e6", "#2b8a3e"]
const SUN = new THREE.Vector3(-70, 22, 110)
const SUN_BEHIND = new THREE.Vector3(-60, 45, -90)

function EgoCar() {
  const car = useRef<CarHandle>(null!)
  const travelled = useRef(0)
  const lastX = useRef<number | null>(null)
  useFrame((_, delta) => {
    const s = live.current
    if (!s || !car.current || !view.ready) return
    const e = view.ego
    const root = car.current.root
    root.position.set(e.y, 0, e.x)
    root.rotation.y = Math.atan2(e.vy, Math.max(e.v, 2))
    const pitch = THREE.MathUtils.clamp(-e.a * 0.008, -0.02, 0.06)
    car.current.body.rotation.x += (pitch - car.current.body.rotation.x) * (1 - Math.exp(-delta * 4))
    if (lastX.current !== null && Math.abs(e.x - lastX.current) < 5) travelled.current += e.x - lastX.current
    lastX.current = e.x
    car.current.wheels.forEach((w) => (w.rotation.x = travelled.current / WHEEL_RADIUS))
    const brake = s.ego.brake
    car.current.brake.emissiveIntensity = brake === "emergency" ? 9 : brake === "hard" ? 7 : brake === "normal" ? 4 : 0.7
  })
  return <Car ref={car} paint="#1f5eff" headlights={2.2} />
}

function OncomingTraffic({ snap }: { snap: Snapshot }) {
  return (
    <>
      {snap.oncoming.map((c) => (
        <MirroredCar key={c.id} id={c.id} colour={c.c} />
      ))}
    </>
  )
}

function MirroredCar({ id, colour }: { id: number; colour: number }) {
  const group = useRef<THREE.Group>(null!)
  const car = useRef<CarHandle>(null!)
  const travelled = useRef(0)
  useFrame((_, delta) => {
    const c = view.oncoming.get(id)
    const raw = live.current?.oncoming.find((o) => o.id === id)
    if (!c || !raw || !group.current) return
    group.current.position.set(raw.y, 0, c.x)
    travelled.current += c.v * delta
    car.current?.wheels.forEach((w) => (w.rotation.x = travelled.current / WHEEL_RADIUS))
    if (car.current) car.current.brake.emissiveIntensity = c.v < 5 ? 5 : 0.7
  })
  return (
    <group ref={group} rotation-y={Math.PI}>
      <Car ref={car} paint={PAINTS[colour % PAINTS.length]} />
    </group>
  )
}

function StopLine() {
  const mesh = useRef<THREE.Mesh>(null!)
  useFrame(() => {
    const s = live.current
    const target = s?.hazards.find((h) => h.id === s.target)
    const pos = target ? view.hazards.get(target.id) : undefined
    const show = !!s && !!target && !!pos && s.ego.maneuver === "stop" && !s.ego.phase
    mesh.current.visible = show
    if (show) mesh.current.position.set(0, 0.03, pos!.x - target!.l / 2 - (target!.kind === "van" ? 12 : 9))
  })
  return (
    <mesh ref={mesh} rotation-x={-Math.PI / 2}>
      <planeGeometry args={[LANE_W - 0.3, 0.45]} />
      <meshBasicMaterial color="#ff4d4d" transparent opacity={0.85} toneMapped={false} />
    </mesh>
  )
}

function Sun({ sun = SUN }: { sun?: THREE.Vector3 }) {
  const light = useRef<THREE.DirectionalLight>(null!)
  const { scene } = useThree()
  useFrame(() => {
    const z = view.ego.x
    light.current.position.set(sun.x * 0.4, sun.y * 1.6, z + sun.z * 0.4)
    light.current.target.position.set(0, 0, z + 10)
    light.current.target.updateMatrixWorld()
  })
  return (
    <>
      <hemisphereLight args={["#ffe2c4", "#3b4a2c", 0.9]} />
      <directionalLight
        ref={(l) => {
          if (l && !light.current) {
            light.current = l
            scene.add(l.target)
          }
        }}
        color="#ffd2a1"
        intensity={2.6}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-camera-left={-40}
        shadow-camera-right={40}
        shadow-camera-top={60}
        shadow-camera-bottom={-40}
        shadow-camera-far={200}
      />
    </>
  )
}

function CameraRig({ mode }: { mode: CameraMode }) {
  const look = useRef(new THREE.Vector3())
  const shake = useRef(0)
  useFrame(({ camera, clock }, delta) => {
    const s = live.current
    if (!s || !view.ready) return
    const e = s.ego
    const z = view.ego.x
    const x = view.ego.y
    let pos: THREE.Vector3, target: THREE.Vector3
    if (mode === "dash") {
      pos = new THREE.Vector3(x, 1.3, z + 1.2)
      target = new THREE.Vector3(x, 1.1, z + 31)
      camera.position.copy(pos)
      look.current.copy(target)
      camera.lookAt(look.current)
      return
    } else if (mode === "side") {
      const a = clock.elapsedTime * 0.12
      pos = new THREE.Vector3(x - 7.5 + Math.sin(a) * 1.5, 1.7, z + 5 + Math.cos(a) * 3)
      target = new THREE.Vector3(x, 0.9, z + 3)
    } else if (mode === "drone") {
      pos = new THREE.Vector3(1.75, 30, z - 16)
      target = new THREE.Vector3(1.75, 0, z + 20)
    } else {
      pos = new THREE.Vector3(x * 0.75, 3.9, z - 10.5)
      target = new THREE.Vector3(x * 0.5 + 0.35, 0.9, z + 18)
    }
    const hard = e.brake === "emergency" ? 1 : e.brake === "hard" ? 0.6 : 0
    shake.current += (hard - shake.current) * (1 - Math.exp(-delta * 6))
    const k = 1 - Math.exp(-delta * (mode === "drone" ? 2 : 4))
    camera.position.x += (pos.x - camera.position.x) * k
    camera.position.y += (pos.y - camera.position.y) * k
    camera.position.z = mode === "side" ? camera.position.z + (pos.z - camera.position.z) * k : pos.z
    if (shake.current > 0.02) {
      const amp = 0.05 * shake.current
      camera.position.x += (Math.random() - 0.5) * amp
      camera.position.y += (Math.random() - 0.5) * amp
    }
    look.current.set(look.current.lengthSq() ? look.current.x + (target.x - look.current.x) * k : target.x, target.y, target.z)
    camera.lookAt(look.current)
  })
  return null
}

function Clock() {
  useFrame((_, delta) => advanceView(Math.min(delta, 0.1)), -1)
  return null
}

export function World3D({ snap, mode, render = false, labels = true }: { snap: Snapshot | null; mode: CameraMode; render?: boolean; labels?: boolean }) {
  return (
    <Canvas shadows dpr={render ? 1 : [1, 2]} camera={{ fov: render ? 36 : 52, near: 0.1, far: 900, position: [0, 3, -9] }}
      gl={{ antialias: true, preserveDrawingBuffer: render }}>
      <color attach="background" args={["#f2c9a0"]} />
      <fog attach="fog" args={["#e9c4a2", 90, 480]} />
      <Sky sunPosition={(render ? SUN_BEHIND : SUN).toArray()} turbidity={7} rayleigh={1.6} mieCoefficient={0.006} mieDirectionalG={0.86} distance={2000} />
      {!render && <Clock />}
      <Sun sun={render ? SUN_BEHIND : SUN} />
      <Environment resolution={128} frames={1}>
        <Lightformer form="rect" intensity={3} color="#ffd9b0" position={[-10, 8, 10]} scale={[20, 6, 1]} />
        <Lightformer form="rect" intensity={1.5} color="#bcd7ff" position={[10, 10, -10]} scale={[20, 4, 1]} />
        <Lightformer form="ring" intensity={2} color="#ffffff" position={[0, 12, 0]} scale={6} rotation-x={Math.PI / 2} />
      </Environment>
      <Suspense fallback={null}>
        <Road />
        {snap && (
          <>
            {!render && mode !== "dash" && <EgoCar />}
            <OncomingTraffic snap={snap} />
            <Hazards hazards={snap.hazards} target={render ? null : snap.target} labels={labels} />
          </>
        )}
        {!render && <StopLine />}
      </Suspense>
      <CameraRig mode={mode} />
      {!render && (
        <EffectComposer multisampling={4}>
          <Bloom mipmapBlur intensity={0.75} luminanceThreshold={0.9} luminanceSmoothing={0.2} />
          <Vignette offset={0.28} darkness={0.55} />
        </EffectComposer>
      )}
    </Canvas>
  )
}
