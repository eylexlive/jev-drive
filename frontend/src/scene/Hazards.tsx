import { Html } from "@react-three/drei"
import { useFrame } from "@react-three/fiber"
import { useRef } from "react"
import * as THREE from "three"

import { Badge } from "@/components/ui/badge"
import { type Hazard, live, view } from "@/lib/sim"

import { hash } from "@/lib/utils"

const SHIRTS = ["#e4572e", "#4c6ef5", "#12b886", "#f59f00", "#ae3ec9", "#495057"]

function useLive(h: Hazard) {
  const ref = useRef<THREE.Group>(null!)
  useFrame(() => {
    const p = view.hazards.get(h.id)
    if (p && ref.current) ref.current.position.set(p.y, 0, p.x)
  })
  return ref
}

function Van({ h }: { h: Hazard }) {
  const ref = useLive(h)
  const lights = useRef<THREE.MeshStandardMaterial>(null!)
  useFrame(({ clock }) => {
    lights.current.emissiveIntensity = Math.floor(clock.elapsedTime * 2.4) % 2 ? 0.2 : 6
  })
  return (
    <group ref={ref}>
      <mesh position={[0, 1.35, -0.5]} castShadow receiveShadow>
        <boxGeometry args={[2.05, 2.3, 4.2]} />
        <meshStandardMaterial color="#f1f3f5" roughness={0.45} metalness={0.1} />
      </mesh>
      <mesh position={[0, 1.0, 2.05]} castShadow>
        <boxGeometry args={[2.0, 1.6, 1.3]} />
        <meshStandardMaterial color="#e9ecef" roughness={0.45} />
      </mesh>
      <mesh position={[0, 1.45, 2.72]}>
        <boxGeometry args={[1.8, 0.7, 0.05]} />
        <meshStandardMaterial color="#10151b" roughness={0.1} metalness={0.6} />
      </mesh>
      <mesh position={[0, 0.9, -0.5]}>
        <boxGeometry args={[2.07, 0.25, 4.22]} />
        <meshStandardMaterial color="#1c7ed6" />
      </mesh>
      {[[-0.95, -2.62], [0.95, -2.62], [-0.95, 2.72], [0.95, 2.72]].map(([x, z], i) => (
        <mesh key={i} position={[x, 0.75, z]}>
          <boxGeometry args={[0.18, 0.14, 0.06]} />
          <meshStandardMaterial ref={i === 0 ? lights : undefined} color="#ffa94d" emissive="#ff8c00" emissiveIntensity={6} />
        </mesh>
      ))}
      {[[-0.95, 1.8], [0.95, 1.8], [-0.95, -1.7], [0.95, -1.7]].map(([x, z], i) => (
        <mesh key={i} position={[x, 0.36, z]} rotation-z={Math.PI / 2} castShadow>
          <cylinderGeometry args={[0.36, 0.36, 0.28, 16]} />
          <meshStandardMaterial color="#1b1b1b" roughness={0.8} />
        </mesh>
      ))}
    </group>
  )
}

function Boxes({ h }: { h: Hazard }) {
  const ref = useLive(h)
  const boxes = [0, 1, 2, 3, 4].map((i) => {
    const r = (k: number) => hash(h.id * 13 + i * 7 + k)
    const s = 0.35 + r(1) * 0.3
    const half = Math.SQRT1_2 * s * 0.6
    return { s, x: (r(2) - 0.5) * Math.max(0, h.w - 2 * half), z: (r(3) - 0.5) * Math.max(0, h.l - 2 * half), y: i === 4 ? s + 0.2 : s / 2, rot: r(4) * Math.PI }
  })
  return (
    <group ref={ref}>
      {boxes.map((b, i) => (
        <group key={i} position={[b.x, b.y, b.z]} rotation-y={b.rot}>
          <mesh castShadow receiveShadow>
            <boxGeometry args={[b.s * 1.2, b.s, b.s]} />
            <meshStandardMaterial color="#b98b53" roughness={0.95} />
          </mesh>
          <mesh position={[0, b.s / 2 + 0.002, 0]}>
            <boxGeometry args={[b.s * 1.21, 0.004, 0.12]} />
            <meshStandardMaterial color="#d8c39a" />
          </mesh>
        </group>
      ))}
    </group>
  )
}

function Cones({ h }: { h: Hazard }) {
  const ref = useLive(h)
  return (
    <group ref={ref}>
      {[-1.6, -0.55, 0.55, 1.6].map((z, i) => (
        <group key={i} position={[(i % 2 ? 0.45 : -0.45), 0, z]}>
          <mesh position={[0, 0.03, 0]} receiveShadow>
            <boxGeometry args={[0.42, 0.06, 0.42]} />
            <meshStandardMaterial color="#222" />
          </mesh>
          <mesh position={[0, 0.4, 0]} castShadow>
            <coneGeometry args={[0.17, 0.72, 20]} />
            <meshStandardMaterial color="#ff6b1a" roughness={0.5} />
          </mesh>
          <mesh position={[0, 0.45, 0]}>
            <cylinderGeometry args={[0.1, 0.125, 0.12, 20]} />
            <meshStandardMaterial color="#f8f9fa" emissive="#ffffff" emissiveIntensity={0.4} />
          </mesh>
        </group>
      ))}
    </group>
  )
}

function Branch({ h }: { h: Hazard }) {
  const ref = useLive(h)
  return (
    <group ref={ref} rotation-y={0.6}>
      <mesh position={[0, 0.22, 0]} rotation-z={Math.PI / 2} castShadow>
        <cylinderGeometry args={[0.16, 0.22, 3.2, 8]} />
        <meshStandardMaterial color="#6b4a2b" roughness={1} />
      </mesh>
      {[[-0.6, 0.6, 0.4], [0.5, 0.5, -0.5], [1.3, 0.55, 0.3], [-1.3, 0.5, -0.2]].map(([x, y, z], i) => (
        <mesh key={i} position={[x, y, z]} castShadow>
          <icosahedronGeometry args={[0.55 + (i % 2) * 0.2, 1]} />
          <meshStandardMaterial color={i % 2 ? "#3f6b35" : "#4f7d3c"} flatShading roughness={0.9} />
        </mesh>
      ))}
    </group>
  )
}

function Walker({ h, scale = 1 }: { h: Hazard; scale?: number }) {
  const ref = useLive(h)
  const legL = useRef<THREE.Group>(null!)
  const legR = useRef<THREE.Group>(null!)
  const armL = useRef<THREE.Group>(null!)
  const armR = useRef<THREE.Group>(null!)
  const head = useRef<THREE.Mesh>(null!)
  const phone = h.text.includes("phone")
  const shirt = SHIRTS[h.id % SHIRTS.length]
  useFrame(({ clock }, delta) => {
    const current = live.current?.hazards.find((x) => x.id === h.id) ?? h
    const speed = Math.hypot(current.vx, current.vy)
    const swing = speed > 0.2 ? Math.sin(clock.elapsedTime * (4 + speed * 2.5)) * Math.min(0.7, 0.25 + speed * 0.2) : 0
    legL.current.rotation.x = swing
    legR.current.rotation.x = -swing
    armL.current.rotation.x = -swing * 0.8
    armR.current.rotation.x = phone && speed < 0.2 ? -1.2 : swing * 0.8
    head.current.rotation.x = phone && speed < 0.2 ? 0.45 : 0
    const target = speed > 0.2 ? Math.atan2(current.vy, current.vx) : phone ? Math.PI / 2 + 0.6 : Math.PI / 2
    ref.current.rotation.y += (target - ref.current.rotation.y) * (1 - Math.exp(-delta * 8))
  })
  return (
    <group ref={ref} scale={scale}>
      <group ref={legL} position={[-0.11, 0.88, 0]}>
        <mesh position={[0, -0.44, 0]} castShadow>
          <capsuleGeometry args={[0.075, 0.72, 4, 8]} />
          <meshStandardMaterial color="#2f3640" />
        </mesh>
      </group>
      <group ref={legR} position={[0.11, 0.88, 0]}>
        <mesh position={[0, -0.44, 0]} castShadow>
          <capsuleGeometry args={[0.075, 0.72, 4, 8]} />
          <meshStandardMaterial color="#2f3640" />
        </mesh>
      </group>
      <mesh position={[0, 1.2, 0]} castShadow>
        <capsuleGeometry args={[0.2, 0.45, 4, 12]} />
        <meshStandardMaterial color={shirt} roughness={0.8} />
      </mesh>
      <group ref={armL} position={[-0.27, 1.42, 0]}>
        <mesh position={[0, -0.3, 0]} castShadow>
          <capsuleGeometry args={[0.055, 0.5, 4, 8]} />
          <meshStandardMaterial color={shirt} />
        </mesh>
      </group>
      <group ref={armR} position={[0.27, 1.42, 0]}>
        <mesh position={[0, -0.3, 0]} castShadow>
          <capsuleGeometry args={[0.055, 0.5, 4, 8]} />
          <meshStandardMaterial color={shirt} />
        </mesh>
        {phone && (
          <mesh position={[0, -0.6, 0.06]}>
            <boxGeometry args={[0.07, 0.13, 0.015]} />
            <meshStandardMaterial color="#111" emissive="#6cc4ff" emissiveIntensity={1.5} />
          </mesh>
        )}
      </group>
      <mesh ref={head} position={[0, 1.66, 0]} castShadow>
        <sphereGeometry args={[0.14, 16, 16]} />
        <meshStandardMaterial color="#e0b48f" roughness={0.7} />
      </mesh>
    </group>
  )
}

function Deer({ h }: { h: Hazard }) {
  const ref = useLive(h)
  const legs = useRef<THREE.Group[]>([])
  useFrame(({ clock }, delta) => {
    const current = live.current?.hazards.find((x) => x.id === h.id) ?? h
    const moving = Math.hypot(current.vx, current.vy) > 0.2
    legs.current.forEach((g, i) => { if (g) g.rotation.x = moving ? Math.sin(clock.elapsedTime * 6 + i * Math.PI / 2) * 0.5 : 0 })
    const target = moving ? Math.atan2(current.vy, current.vx) : Math.PI
    ref.current.rotation.y += (target - ref.current.rotation.y) * (1 - Math.exp(-delta * 5))
  })
  const fur = <meshStandardMaterial color="#8b5a2b" roughness={0.9} />
  return (
    <group ref={ref}>
      <mesh position={[0, 1.05, 0]} rotation-x={Math.PI / 2} castShadow>
        <capsuleGeometry args={[0.28, 0.95, 4, 12]} />
        {fur}
      </mesh>
      <mesh position={[0, 1.45, 0.62]} rotation-x={-0.6} castShadow>
        <capsuleGeometry args={[0.1, 0.45, 4, 8]} />
        {fur}
      </mesh>
      <mesh position={[0, 1.72, 0.82]} rotation-x={0.3} castShadow>
        <coneGeometry args={[0.13, 0.4, 10]} />
        {fur}
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * 0.12, 1.98, 0.72]} rotation-z={s * -0.5} castShadow>
          <cylinderGeometry args={[0.018, 0.025, 0.42, 5]} />
          <meshStandardMaterial color="#d9c3a0" />
        </mesh>
      ))}
      <mesh position={[0, 1.15, -0.72]}>
        <sphereGeometry args={[0.09, 8, 8]} />
        <meshStandardMaterial color="#f8f0e3" />
      </mesh>
      {[[-0.15, 0.45], [0.15, 0.45], [-0.15, -0.45], [0.15, -0.45]].map(([x, z], i) => (
        <group key={i} position={[x, 0.95, z]} ref={(g) => { if (g) legs.current[i] = g }}>
          <mesh position={[0, -0.47, 0]} castShadow>
            <cylinderGeometry args={[0.045, 0.035, 0.95, 6]} />
            {fur}
          </mesh>
        </group>
      ))}
    </group>
  )
}

function Dog({ h }: { h: Hazard }) {
  const ref = useLive(h)
  const legs = useRef<THREE.Group[]>([])
  useFrame(({ clock }, delta) => {
    const current = live.current?.hazards.find((x) => x.id === h.id) ?? h
    const moving = Math.hypot(current.vx, current.vy) > 0.2
    legs.current.forEach((g, i) => { if (g) g.rotation.x = moving ? Math.sin(clock.elapsedTime * 14 + i * Math.PI) * 0.7 : 0 })
    const target = moving ? Math.atan2(current.vy, current.vx) : -Math.PI / 2
    ref.current.rotation.y += (target - ref.current.rotation.y) * (1 - Math.exp(-delta * 8))
  })
  const fur = <meshStandardMaterial color="#c8955a" roughness={0.9} />
  return (
    <group ref={ref}>
      <mesh position={[0, 0.48, 0]} rotation-x={Math.PI / 2} castShadow>
        <capsuleGeometry args={[0.15, 0.5, 4, 10]} />
        {fur}
      </mesh>
      <mesh position={[0, 0.66, 0.42]} castShadow>
        <sphereGeometry args={[0.14, 12, 12]} />
        {fur}
      </mesh>
      <mesh position={[0, 0.62, 0.58]}>
        <boxGeometry args={[0.1, 0.08, 0.14]} />
        <meshStandardMaterial color="#3b2a1a" />
      </mesh>
      {[[-0.09, 0.22], [0.09, 0.22], [-0.09, -0.22], [0.09, -0.22]].map(([x, z], i) => (
        <group key={i} position={[x, 0.42, z]} ref={(g) => { if (g) legs.current[i] = g }}>
          <mesh position={[0, -0.2, 0]} castShadow>
            <cylinderGeometry args={[0.035, 0.03, 0.4, 6]} />
            {fur}
          </mesh>
        </group>
      ))}
    </group>
  )
}

const MODELS: Record<Hazard["kind"], (p: { h: Hazard }) => React.JSX.Element> = {
  van: Van,
  boxes: Boxes,
  cones: Cones,
  branch: Branch,
  pedestrian: ({ h }) => <Walker h={h} scale={h.text.includes("child") ? 0.7 : 1} />,
  deer: Deer,
  dog: Dog,
}

const LABEL: Record<Hazard["kind"], string> = {
  van: "Stopped van",
  boxes: "Debris",
  cones: "Road works",
  branch: "Fallen branch",
  pedestrian: "Pedestrian",
  deer: "Deer",
  dog: "Dog",
}

function TargetMarker({ h, label }: { h: Hazard; label: boolean }) {
  const ring = useRef<THREE.Mesh>(null!)
  const group = useLive(h)
  const material = useRef<THREE.MeshBasicMaterial>(null!)
  useFrame(({ clock }) => {
    const s = live.current
    const phase = s?.ego.phase
    const color = phase ? "#6cc4ff" : s?.ego.maneuver === "stop" ? "#ff5b5b" : s?.ego.maneuver === "slow" ? "#ffd166" : "#9aa5b1"
    material.current.color.set(color)
    const pulse = 1 + Math.sin(clock.elapsedTime * 5) * 0.08
    ring.current.scale.setScalar(pulse)
  })
  const distance = Math.max(0, h.x - h.l / 2 - (view.ego.x + 2.25))
  return (
    <group ref={group}>
      <mesh ref={ring} rotation-x={-Math.PI / 2} position={[0, 0.04, 0]}>
        <ringGeometry args={[Math.max(h.l, h.w) * 0.75 + 0.5, Math.max(h.l, h.w) * 0.75 + 0.75, 48]} />
        <meshBasicMaterial ref={material} transparent opacity={0.85} toneMapped={false} />
      </mesh>
      {label && <Html position={[0, h.kind === "van" ? 3.4 : 2.4, 0]} center distanceFactor={14} zIndexRange={[20, 0]}>
        <div className="pointer-events-none flex items-center gap-1.5 whitespace-nowrap">
          <Badge variant={h.sudden ? "destructive" : "secondary"}>{h.sudden ? "Sudden" : "Ahead"}</Badge>
          <Badge variant="outline" className="bg-background/80 backdrop-blur">
            {LABEL[h.kind]} · {Math.round(distance)} m
          </Badge>
        </div>
      </Html>}
    </group>
  )
}

export function Hazards({ hazards, target, labels = true }: { hazards: Hazard[]; target: number | null; labels?: boolean }) {
  return (
    <>
      {hazards.map((h) => {
        const Model = MODELS[h.kind]
        return <Model key={h.id} h={h} />
      })}
      {hazards.filter((h) => h.id === target).map((h) => <TargetMarker key={`t${h.id}`} h={h} label={labels} />)}
    </>
  )
}
