import { useGLTF } from "@react-three/drei"
import { forwardRef, useImperativeHandle, useMemo, useRef } from "react"
import type { Group, Mesh, MeshStandardMaterial } from "three"
import { Color } from "three"

type Nodes = Record<string, Mesh>
type Materials = Record<string, MeshStandardMaterial>

export interface CarHandle {
  root: Group
  body: Group
  wheels: Group[]
  brake: MeshStandardMaterial
}

const WHEEL_RADIUS = 0.38
const WHEEL_SPOTS: [number, number, boolean][] = [
  [0.85, 1.35, true],
  [-0.85, 1.35, false],
  [0.85, -1.3, true],
  [-0.85, -1.3, false],
]

export const Car = forwardRef<CarHandle, { paint: string; headlights?: number }>(function Car({ paint, headlights = 1.5 }, ref) {
  const { nodes: n, materials: m } = useGLTF("/models/chassis-draco.glb") as unknown as { nodes: Nodes; materials: Materials }
  const { nodes: wn, materials: wm } = useGLTF("/models/wheel-draco.glb") as unknown as { nodes: Nodes; materials: Materials }
  const root = useRef<Group>(null!)
  const body = useRef<Group>(null!)
  const wheels = useRef<Group[]>([])

  const mats = useMemo(() => {
    const bodyPaint = m.BodyPaint.clone()
    bodyPaint.color = new Color(paint)
    bodyPaint.metalness = 0.55
    bodyPaint.roughness = 0.32
    const brake = m.BrakeLight.clone()
    brake.emissive = new Color("#ff1a1a")
    brake.emissiveIntensity = 0.6
    brake.transparent = false
    const head = m.HeadLight.clone()
    head.emissive = new Color("#fff4d6")
    head.emissiveIntensity = headlights
    const glass = m.Glass.clone()
    glass.transparent = true
    glass.opacity = 0.8
    glass.color = new Color("#0b0f14")
    return { bodyPaint, brake, head, glass }
  }, [m, paint, headlights])

  useImperativeHandle(ref, () => ({ root: root.current, body: body.current, wheels: wheels.current, brake: mats.brake }), [mats])

  return (
    <group ref={root} dispose={null}>
      <group ref={body} position={[0, 0.98, 0]}>
        <group position={[0, -0.2, -0.2]}>
          <mesh castShadow receiveShadow geometry={n.Chassis_1.geometry} material={mats.bodyPaint} />
          <mesh castShadow geometry={n.Chassis_2.geometry} material={n.Chassis_2.material} material-color="#2b2b2b" />
          <mesh geometry={n.Glass.geometry} material={mats.glass} />
          <mesh geometry={n.BrakeLights.geometry} material={mats.brake} />
          <mesh geometry={n.HeadLights.geometry} material={mats.head} />
          <mesh geometry={n.Cabin_Grilles.geometry} material={m.Black} />
          <mesh geometry={n.Undercarriage.geometry} material={m.Undercarriage} />
          <mesh geometry={n.TurnSignals.geometry} material={m.TurnSignal} />
          <mesh geometry={n.Chrome.geometry} material={n.Chrome.material} />
          <mesh geometry={n.License_1.geometry} material={m.License} />
          <mesh geometry={n.License_2.geometry} material={n.License_2.material} />
        </group>
      </group>
      {WHEEL_SPOTS.map(([x, z, left], i) => (
        <group key={i} position={[x, WHEEL_RADIUS, z]} ref={(g) => { if (g) wheels.current[i] = g }}>
          <group scale={WHEEL_RADIUS / 0.34}>
            <group scale={left ? -1 : 1}>
              <mesh castShadow geometry={wn.Mesh_14.geometry} material={wm["Material.002"]} />
              <mesh castShadow geometry={wn.Mesh_14_1.geometry} material={wm["Material.009"]} />
            </group>
          </group>
        </group>
      ))}
    </group>
  )
})

useGLTF.preload("/models/chassis-draco.glb")
useGLTF.preload("/models/wheel-draco.glb")
export { WHEEL_RADIUS }
