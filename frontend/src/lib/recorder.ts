import { useCallback, useEffect, useRef, useState } from "react"

function pickType() {
  const types = ["video/mp4;codecs=avc1.640028", "video/mp4", "video/webm;codecs=vp9", "video/webm"]
  return types.find((t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) ?? ""
}

export function useRecorder() {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const recorder = useRef<MediaRecorder | null>(null)
  const started = useRef(0)

  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => setSeconds(Math.floor((performance.now() - started.current) / 1000)), 250)
    return () => clearInterval(id)
  }, [recording])

  const uploadNext = useRef(false)
  const start = useCallback(async (opts?: { upload?: boolean }) => {
    uploadNext.current = !!opts?.upload
    if (!navigator.mediaDevices?.getDisplayMedia) throw new Error("This browser cannot record a tab. Use Chrome, or macOS Cmd+Shift+5.")
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 60 },
      audio: false,
      preferCurrentTab: true,
      selfBrowserSurface: "include",
    } as DisplayMediaStreamOptions)
    const type = pickType()
    const rec = new MediaRecorder(stream, { mimeType: type || undefined, videoBitsPerSecond: 16_000_000 })
    const chunks: Blob[] = []
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    rec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop())
      const blob = new Blob(chunks, { type: rec.mimeType })
      if (uploadNext.current) {
        const res = await fetch("/take/upload", { method: "POST", headers: { "Content-Type": rec.mimeType }, body: blob })
        const out = await res.json().catch(() => ({}))
        window.dispatchEvent(new CustomEvent("take-saved", { detail: out }))
        setRecording(false)
        return
      }
      const a = document.createElement("a")
      a.href = URL.createObjectURL(blob)
      a.download = `jev-drive-${new Date().toISOString().replace(/[:.]/g, "-")}.${rec.mimeType.includes("mp4") ? "mp4" : "webm"}`
      a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 10_000)
      setRecording(false)
    }
    stream.getVideoTracks()[0].addEventListener("ended", () => rec.state !== "inactive" && rec.stop())
    rec.start(1000)
    recorder.current = rec
    started.current = performance.now()
    setSeconds(0)
    setRecording(true)
  }, [])

  const stop = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop()
  }, [])

  return { recording, seconds, start, stop }
}
