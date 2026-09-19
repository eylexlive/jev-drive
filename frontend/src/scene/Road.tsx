import { useFrame } from "@react-three/fiber"
import { useLayoutEffect, useMemo, useRef } from "react"
import * as THREE from "three"

import { LANE_W, ROAD_LEFT, ROAD_RIGHT, view } from "@/lib/sim"
import { hash } from "@/lib/utils"

const TILE = 9
const ROAD_W = ROAD_LEFT - ROAD_RIGHT
const AHEAD = 520
const BEHIND = 60
const WALK_W = 3.2

let noiseSeed = 1
const noise = () => hash(noiseSeed++)

function canvasTexture(w: number, h: number, paint: (g: CanvasRenderingContext2D) => void) {
  const c = document.createElement("canvas")
  c.width = w
  c.height = h
  paint(c.getContext("2d")!)
  const t = new THREE.CanvasTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  return t
}

function speckle(g: CanvasRenderingContext2D, w: number, h: number, base: string, dots: number, light: number) {
  g.fillStyle = base
  g.fillRect(0, 0, w, h)
  for (let i = 0; i < dots; i++) {
    const v = noise()
    g.fillStyle = v > 0.5 ? `rgba(255,255,255,${light * noise()})` : `rgba(0,0,0,${light * 1.4 * noise()})`
    g.fillRect(noise() * w, noise() * h, 1 + noise() * 2, 1 + noise() * 2)
  }
}

function useTextures() {
  return useMemo(() => {
    const px = 64
    const road = canvasTexture(ROAD_W * px, TILE * px, (g) => {
      const W = ROAD_W * px, H = TILE * px
      speckle(g, W, H, "#3b3e44", 26000, 0.12)
      g.fillStyle = "rgba(0,0,0,0.18)"
      for (const lane of [LANE_W / 2, LANE_W * 1.5]) for (const off of [-0.8, 0.8]) g.fillRect((lane + off - 0.25) * px, 0, 0.5 * px, H)
      g.fillStyle = "#e9e9e6"
      g.fillRect(0.12 * px, 0, 0.15 * px, H)
      g.fillRect((ROAD_W - 0.27) * px, 0, 0.15 * px, H)
      g.fillStyle = "#f2c230"
      g.fillRect((LANE_W - 0.07) * px, 0, 0.14 * px, 3 * px)
    })
    road.repeat.set(1, (AHEAD + BEHIND) / TILE)
    const walk = canvasTexture(256, 256, (g) => {
      speckle(g, 256, 256, "#a9a49a", 4000, 0.08)
      g.strokeStyle = "rgba(60,55,50,0.35)"
      g.lineWidth = 2
      for (let i = 0; i <= 4; i++) {
        g.beginPath(); g.moveTo(i * 64, 0); g.lineTo(i * 64, 256); g.stroke()
        g.beginPath(); g.moveTo(0, i * 64); g.lineTo(256, i * 64); g.stroke()
      }
    })
    walk.repeat.set(WALK_W / 1.2, (AHEAD + BEHIND) / 1.2)
    const grass = canvasTexture(512, 512, (g) => {
      speckle(g, 512, 512, "#56733f", 30000, 0.16)
      for (let i = 0; i < 300; i++) {
        g.fillStyle = `rgba(${90 + noise() * 40},${110 + noise() * 40},60,0.25)`
        g.beginPath(); g.arc(noise() * 512, noise() * 512, 6 + noise() * 18, 0, 7); g.fill()
      }
    })
    grass.repeat.set(40, 80)
    const windows = canvasTexture(128, 256, (g) => {
      g.fillStyle = "#000"
      g.fillRect(0, 0, 128, 256)
      for (let y = 8; y < 256; y += 22) for (let x = 8; x < 128; x += 20) {
        const lit = noise() < 0.35
        g.fillStyle = lit ? `rgba(255,${190 + noise() * 50},${120 + noise() * 60},1)` : "rgba(40,50,60,1)"
        g.fillRect(x, y, 12, 14)
      }
    })
    return { road, walk, grass, windows }
  }, [])
}

function snapped(z: number, step: number) {
  return Math.floor(z / step) * step
}

export function Road() {
  const tex = useTextures()
  const road = useRef<THREE.Mesh>(null!)
  const ground = useRef<THREE.Group>(null!)
  useFrame(() => {
    const z = view.ego.x
    road.current.position.z = snapped(z, TILE) + (AHEAD - BEHIND) / 2
    ground.current.position.z = snapped(z, 1.2 * 10)
  })
  const length = AHEAD + BEHIND
  const walkRight = ROAD_RIGHT - WALK_W / 2
  const walkLeft = ROAD_LEFT + WALK_W / 2
  return (
    <group>
      <mesh ref={road} rotation-x={-Math.PI / 2} position={[(ROAD_LEFT + ROAD_RIGHT) / 2, 0.01, 0]} receiveShadow>
        <planeGeometry args={[ROAD_W, length]} />
        <meshStandardMaterial map={tex.road} roughness={0.92} metalness={0} />
      </mesh>
      <group ref={ground}>
        {[walkRight, walkLeft].map((x) => (
          <mesh key={x} position={[x, 0.08, (AHEAD - BEHIND) / 2]} receiveShadow>
            <boxGeometry args={[WALK_W, 0.16, length]} />
            <meshStandardMaterial map={tex.walk} roughness={0.95} />
          </mesh>
        ))}
        {[ROAD_RIGHT - 0.1, ROAD_LEFT + 0.1].map((x) => (
          <mesh key={x} position={[x, 0.1, (AHEAD - BEHIND) / 2]} receiveShadow castShadow>
            <boxGeometry args={[0.22, 0.2, length]} />
            <meshStandardMaterial color="#cfccc4" roughness={0.8} />
          </mesh>
        ))}
        <mesh rotation-x={-Math.PI / 2} position={[0, -0.01, 150]} receiveShadow>
          <planeGeometry args={[480, 960]} />
          <meshStandardMaterial map={tex.grass} roughness={1} />
        </mesh>
      </group>
      <Props windows={tex.windows} />
    </group>
  )
}

interface PoolSpec {
  spacing: number
  sides: number[]
  skip: number
}

const dummy = new THREE.Object3D()
const tmpColor = new THREE.Color()

function Props({ windows }: { windows: THREE.Texture }) {
  const trees = { spacing: 7, sides: [ROAD_RIGHT - WALK_W - 2.2, ROAD_LEFT + WALK_W + 2.2], skip: 0.35 }
  const lamps = { spacing: 32, sides: [ROAD_RIGHT - 0.55, ROAD_LEFT + 0.55], skip: 0 }
  const houses = { spacing: 16, sides: [ROAD_RIGHT - WALK_W - 14, ROAD_LEFT + WALK_W + 14], skip: 0.3 }
  const count = (s: PoolSpec) => Math.ceil((AHEAD + BEHIND) / s.spacing + 2) * s.sides.length

  const trunk = useRef<THREE.InstancedMesh>(null!)
  const crown = useRef<THREE.InstancedMesh>(null!)
  const crown2 = useRef<THREE.InstancedMesh>(null!)
  const pole = useRef<THREE.InstancedMesh>(null!)
  const arm = useRef<THREE.InstancedMesh>(null!)
  const bulb = useRef<THREE.InstancedMesh>(null!)
  const house = useRef<THREE.InstancedMesh>(null!)
  const roof = useRef<THREE.InstancedMesh>(null!)
  const lastStart = useRef<Record<string, number>>({})

  useLayoutEffect(() => {
    for (const mesh of [house.current]) {
      for (let i = 0; i < mesh.count; i++) mesh.setColorAt(i, tmpColor.set("#ffffff"))
    }
  }, [])

  function place(key: string, spec: PoolSpec, z: number, fn: (slot: number, index: number, side: number, visible: boolean) => void) {
    const start = Math.floor((z - BEHIND) / spec.spacing)
    if (lastStart.current[key] === start) return
    lastStart.current[key] = start
    const per = Math.ceil((AHEAD + BEHIND) / spec.spacing + 2)
    for (let s = 0; s < spec.sides.length; s++) {
      for (let j = 0; j < per; j++) {
        const index = start + j
        fn(s * per + j, index, s, hash(index * 7.3 + s * 101) >= spec.skip)
      }
    }
  }

  useFrame(() => {
    const z = view.ego.x
    place("trees", trees, z, (slot, i, s, visible) => {
      const x = trees.sides[s] + (hash(i * 3.1 + s) - 0.5) * 2.4 * (s ? 1 : -1) + (s ? 1 : -1) * hash(i + 9) * 1.5
      const zz = i * trees.spacing + hash(i * 1.7 + s) * 4
      const h = 3.2 + hash(i * 5.5 + s) * 2.8
      const sc = visible ? 1 : 0
      dummy.position.set(x, (h * 0.45) / 2, zz); dummy.scale.set(sc, sc * h * 0.45, sc); dummy.rotation.set(0, 0, 0); dummy.updateMatrix()
      trunk.current.setMatrixAt(slot, dummy.matrix)
      dummy.position.set(x, h * 0.62, zz); dummy.scale.setScalar(sc * (1.2 + hash(i * 2.2) * 0.8)); dummy.rotation.set(hash(i) * 3, hash(i * 2) * 3, 0); dummy.updateMatrix()
      crown.current.setMatrixAt(slot, dummy.matrix)
      dummy.position.set(x + 0.4, h * 0.85, zz - 0.3); dummy.scale.setScalar(sc * (0.8 + hash(i * 4.1) * 0.6)); dummy.updateMatrix()
      crown2.current.setMatrixAt(slot, dummy.matrix)
    })
    place("lamps", lamps, z, (slot, i, s) => {
      const x = lamps.sides[s], zz = i * lamps.spacing + (s ? lamps.spacing / 2 : 0), dir = s ? -1 : 1
      dummy.rotation.set(0, 0, 0); dummy.scale.set(1, 1, 1)
      dummy.position.set(x, 3, zz); dummy.updateMatrix(); pole.current.setMatrixAt(slot, dummy.matrix)
      dummy.position.set(x + dir * 0.8, 5.9, zz); dummy.updateMatrix(); arm.current.setMatrixAt(slot, dummy.matrix)
      dummy.position.set(x + dir * 1.55, 5.78, zz); dummy.updateMatrix(); bulb.current.setMatrixAt(slot, dummy.matrix)
    })
    place("houses", houses, z, (slot, i, s, visible) => {
      const w = 7 + hash(i * 1.3 + s) * 6, d = 8 + hash(i * 2.9 + s) * 5, h = visible ? 4 + hash(i * 4.7 + s) * 10 : 0
      const x = houses.sides[s] + (s ? 1 : -1) * (w / 2 + hash(i * 6.1) * 3)
      const zz = i * houses.spacing + hash(i * 8.3 + s) * 3
      dummy.rotation.set(0, 0, 0)
      dummy.position.set(x, h / 2, zz); dummy.scale.set(w, Math.max(h, 0.001), d); dummy.updateMatrix()
      house.current.setMatrixAt(slot, dummy.matrix)
      const palette = ["#d8cbb8", "#c9b39a", "#b7c4cc", "#e2d6c4", "#a9a39a", "#cdb5a8"]
      house.current.setColorAt(slot, tmpColor.set(palette[Math.floor(hash(i * 3.3 + s) * palette.length)]))
      dummy.position.set(x, h + 0.25, zz); dummy.scale.set(w + 0.4, h ? 0.5 : 0.001, d + 0.4); dummy.updateMatrix()
      roof.current.setMatrixAt(slot, dummy.matrix)
    })
    for (const m of [trunk, crown, crown2, pole, arm, bulb, house, roof]) m.current.instanceMatrix.needsUpdate = true
    if (house.current.instanceColor) house.current.instanceColor.needsUpdate = true
  })

  return (
    <group>
      <instancedMesh ref={trunk} args={[undefined, undefined, count(trees)]} castShadow>
        <cylinderGeometry args={[0.14, 0.2, 1, 6]} />
        <meshStandardMaterial color="#5a4030" roughness={1} />
      </instancedMesh>
      <instancedMesh ref={crown} args={[undefined, undefined, count(trees)]} castShadow receiveShadow>
        <icosahedronGeometry args={[1.3, 1]} />
        <meshStandardMaterial color="#3f6b35" roughness={0.9} flatShading />
      </instancedMesh>
      <instancedMesh ref={crown2} args={[undefined, undefined, count(trees)]} castShadow>
        <icosahedronGeometry args={[1.1, 1]} />
        <meshStandardMaterial color="#4f7d3c" roughness={0.9} flatShading />
      </instancedMesh>
      <instancedMesh ref={pole} args={[undefined, undefined, count(lamps)]} castShadow>
        <cylinderGeometry args={[0.07, 0.1, 6, 8]} />
        <meshStandardMaterial color="#3a3f46" metalness={0.6} roughness={0.4} />
      </instancedMesh>
      <instancedMesh ref={arm} args={[undefined, undefined, count(lamps)]}>
        <boxGeometry args={[1.7, 0.08, 0.08]} />
        <meshStandardMaterial color="#3a3f46" metalness={0.6} roughness={0.4} />
      </instancedMesh>
      <instancedMesh ref={bulb} args={[undefined, undefined, count(lamps)]}>
        <boxGeometry args={[0.55, 0.12, 0.28]} />
        <meshStandardMaterial color="#fff3d6" emissive="#ffd9a0" emissiveIntensity={2.2} />
      </instancedMesh>
      <instancedMesh ref={house} args={[undefined, undefined, count(houses)]} castShadow receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={windows} emissiveMap={windows} emissive="#ffcf8a" emissiveIntensity={0.35} roughness={0.85} />
      </instancedMesh>
      <instancedMesh ref={roof} args={[undefined, undefined, count(houses)]} castShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#4a4640" roughness={0.9} />
      </instancedMesh>
    </group>
  )
}
