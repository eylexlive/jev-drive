import { DogIcon, PackageIcon, PawPrintIcon, PersonStandingIcon, TrafficConeIcon, TreeDeciduousIcon, TriangleAlertIcon, TruckIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Field, FieldContent, FieldDescription, FieldGroup, FieldLabel, FieldSet, FieldLegend } from "@/components/ui/field"
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { type Snapshot, control } from "@/lib/sim"

const KINDS = [
  { value: "van", label: "Stopped van", icon: TruckIcon },
  { value: "boxes", label: "Fallen cargo", icon: PackageIcon },
  { value: "cones", label: "Road works", icon: TrafficConeIcon },
  { value: "branch", label: "Fallen tree", icon: TreeDeciduousIcon },
  { value: "pedestrian", label: "Person", icon: PersonStandingIcon },
  { value: "deer", label: "Deer", icon: PawPrintIcon },
  { value: "dog", label: "Dog", icon: DogIcon },
]

async function send(body: Record<string, unknown>) {
  const result = await control(body)
  if (!result.ok) toast.error(result.error ?? "Request failed")
  return result.ok
}

export function ObstacleMenu({ snap }: { snap: Snapshot | null }) {
  const settings = snap?.hazard_settings
  const [kindsPicked, setKinds] = useState<string[] | null>(null)
  const [intervalPicked, setGap] = useState<number | null>(null)
  const [suddenPicked, setSudden] = useState<boolean | null>(null)
  const kinds = kindsPicked ?? settings?.kinds ?? KINDS.map((k) => k.value)
  const interval = intervalPicked ?? Math.round(settings?.interval_s ?? 15)
  const sudden = suddenPicked ?? settings?.sudden ?? true

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="sm" variant="outline">
          <TriangleAlertIcon data-icon="inline-start" />
          Obstacles
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96">
        <PopoverHeader>
          <PopoverTitle>Obstacles</PopoverTitle>
          <PopoverDescription>What appears on the road, how often, and how suddenly.</PopoverDescription>
        </PopoverHeader>
        <FieldGroup>
          <FieldSet>
            <FieldLegend variant="label">Which obstacles</FieldLegend>
            <ToggleGroup type="multiple" variant="outline" size="sm" spacing={1} className="flex-wrap" value={kinds}
              onValueChange={(v) => {
                if (v.length === 0) return
                setKinds(v)
                send({ action: "hazards", kinds: v })
              }}>
              {KINDS.map(({ value, label, icon: Icon }) => (
                <ToggleGroupItem key={value} value={value} aria-label={label}>
                  <Icon data-icon="inline-start" />
                  {label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </FieldSet>
          <Field>
            <FieldLabel htmlFor="interval">Next obstacle after {interval} s</FieldLabel>
            <Slider id="interval" min={5} max={40} step={1} value={[interval]} onValueChange={(v) => setGap(v[0])}
              onValueCommit={(v) => send({ action: "hazards", interval_s: v[0] })} />
            <FieldDescription>Counted from when the previous obstacle is behind you, so they never overlap.</FieldDescription>
          </Field>
          <Field orientation="horizontal">
            <Switch id="sudden" checked={sudden} onCheckedChange={(on) => { setSudden(on); send({ action: "hazards", sudden: on }) }} />
            <FieldContent>
              <FieldLabel htmlFor="sudden">Appear suddenly</FieldLabel>
              <FieldDescription>On: pops up 22-45 m ahead (2-3 s at 50 km/h). Off: visible from about 100 m.</FieldDescription>
            </FieldContent>
          </Field>
          <Button onClick={() => send({ action: "spawn", sudden })}>Spawn one now</Button>
        </FieldGroup>
      </PopoverContent>
    </Popover>
  )
}
