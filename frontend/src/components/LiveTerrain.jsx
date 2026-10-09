import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { IS_DEMO } from '../lib/useAgent'

/*
  LIVE TERRAIN (inspirado en Greptile TREX)
  Un "paisaje" de líneas que respira con el tráfico real de la app.
  - Cada línea = una franja del sistema; la altura de las ondas sigue a requests/s.
  - Las cajas rosadas = tus endpoints y servicios (vienen de /api/surface).
  - Cuadritos lima = tráfico entre servicios.
  - El círculo lima = el agente; recorre los servicios y, si algo pasa, vuela hacia allá.
  - Un pico rojo = un asset bajo ataque; se aplana cuando el agente lo arregla.
*/

const N = 34
const LAYOUT = {
  ftp: [0.3, 9], feedback: [0.56, 6], admin: [0.84, 11],
  login: [0.2, 19], search: [0.66, 17], users: [0.83, 23],
  basket: [0.43, 25], cards: [0.14, 29], db: [0.54, 32], server: [0.76, 30],
}
const LINKS = [
  ['login', 'basket'], ['basket', 'db'], ['search', 'db'], ['users', 'db'], ['cards', 'db'],
  ['search', 'server'], ['feedback', 'search'], ['admin', 'server'], ['login', 'users'], ['ftp', 'login'], ['basket', 'cards'],
]
const C = {
  bg: '#0B0E13', line: [143, 164, 245], lime: '#D7F04B', pink: '#F2A3C7', box: '#F07F95',
  bar: '#F5E65A', red: [255, 77, 94], amber: [245, 165, 36], mute: '#7C8798',
}
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`

export default function LiveTerrain({ state, bare = false }) {
  const wrap = useRef(null)
  const canvas = useRef(null)
  const live = useRef(state)
  live.current = state

  useEffect(() => {
    const cv = canvas.current, ctx = cv.getContext('2d')
    let W = 0, H = 0, raf = 0, clk = 0, prev = performance.now()
    const spikes = {}
    const eye = { x: 0, y: 0, init: false, target: 'login', switchAt: 0 }
    const packets = LINKS.map((_, i) => ({ link: i, p: Math.random(), speed: 0.12 + Math.random() * 0.18 }))
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const resize = () => {
      const r = wrap.current.getBoundingClientRect()
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      W = r.width; H = r.height
      cv.width = W * dpr; cv.height = H * dpr
      cv.style.width = W + 'px'; cv.style.height = H + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    const ro = new ResizeObserver(resize); ro.observe(wrap.current); resize()

    const top = () => H * (bare ? 0.42 : 0.36), bottom = () => H - 34
    const rowY = (i) => top() + (bottom() - top()) * (i / (N - 1))
    const halfW = (i) => W * (0.3 + 0.17 * (i / (N - 1)))

    const frame = (now) => {
      const s = live.current
      const paused = s.monitoring === false
      clk += reduce ? 0 : Math.min(0.05, (now - prev) / 1000) * (paused ? 0.06 : 1)
      prev = now
      const t = clk
      const LINE = paused ? [92, 101, 116] : C.line
      const last = s.metrics.at(-1)
      const energy = last ? Math.min(1.8, Math.max(0.6, last.total / 50)) : 1
      const small = W < 640

      // pico por asset según su estado (sube rápido, baja suave)
      for (const a of s.surface) {
        const goal = a.status === 'bad' ? 1 : a.status === 'warn' ? 0.55 : 0
        const cur = spikes[a.id] ?? 0
        spikes[a.id] = cur + (goal - cur) * (goal > cur ? 0.06 : 0.025)
      }

      const disp = (u, i) => {
        const env = Math.pow(Math.sin(Math.PI * u), 1.4)
        const depth = 1 - (i / N) * 0.55
        const f = Math.sin(u * 7 + t * 0.55 + i * 0.22) * 0.45 + Math.sin(u * 15 - t * 0.8 + i * 0.37) * 0.18
          + Math.sin(u * 3.2 + t * 0.25 + 1.3) * 0.55
        let d = (16 + 22 * depth) * energy * env * (0.55 + 0.45 * f)
        let hot = 0
        for (const id in spikes) {
          const k = spikes[id]; if (k < 0.01 || !LAYOUT[id]) continue
          const [su, sr] = LAYOUT[id]
          const g = k * Math.exp(-((u - su) ** 2) / 0.0018) * Math.exp(-((i - sr) ** 2) / 18)
          d += g * (small ? 60 : 95) * (1 + 0.08 * Math.sin(t * 9 + i))
          hot = Math.max(hot, g)
        }
        return [d, hot]
      }
      const point = (u, i) => {
        const [d, hot] = disp(u, i)
        return [W / 2 + (u - 0.5) * 2 * halfW(i), rowY(i) - d, hot]
      }

      ctx.clearRect(0, 0, W, H)

      // columnas de texto tipo "AUTOMATIC TESTGEN"
      ctx.font = '500 9px "DM Mono", ui-monospace, monospace'
      const words = ['WATCH', 'TRACE', 'SCAN']
      if (!small) {
        for (let c = 0; c < 3; c++) {
          for (let r = 0; r < 9; r++) {
            const y = H * 0.4 + r * 13 + ((t * 8 + c * 5) % 13)
            ctx.fillStyle = rgba(LINE, 0.12 + 0.35 * ((r + c) % 3 === 0 ? 1 : 0.4) * (1 - r / 10))
            ctx.fillText(words[c], W * 0.035 + c * 44, y)
          }
        }
        ctx.save(); ctx.translate(W * 0.955, H * 0.32); ctx.rotate(Math.PI / 2)
        for (let c = 0; c < 4; c++) {
          ctx.fillStyle = `rgba(242,163,199,${0.12 + 0.1 * c})`
          ctx.fillText('VERIFY · PATCH · DEPLOY', 0, c * 12)
        }
        ctx.restore()
      }

      // líneas del terreno (de atrás hacia adelante, rellenando para que tapen)
      const STEPS = Math.max(60, Math.round(W / 7))
      for (let i = 0; i < N; i++) {
        const pts = []
        let maxHot = 0, hotU = 0
        for (let k = 0; k <= STEPS; k++) {
          const u = k / STEPS
          const p = point(u, i); pts.push(p)
          if (p[2] > maxHot) { maxHot = p[2]; hotU = u }
        }
        ctx.beginPath()
        ctx.moveTo(pts[0][0], pts[0][1])
        for (const p of pts) ctx.lineTo(p[0], p[1])
        ctx.lineTo(pts.at(-1)[0], rowY(i) + 6); ctx.lineTo(pts[0][0], rowY(i) + 6); ctx.closePath()
        ctx.fillStyle = C.bg; ctx.fill()

        ctx.beginPath()
        ctx.moveTo(pts[0][0], pts[0][1])
        for (const p of pts) ctx.lineTo(p[0], p[1])
        const a = (paused ? 0.25 : 0.35) + (paused ? 0.25 : 0.5) * (i / N)
        if (maxHot > 0.04) {
          const x0 = pts[0][0], x1 = pts.at(-1)[0], xc = x0 + (x1 - x0) * hotU
          const g = ctx.createLinearGradient(x0, 0, x1, 0)
          const span = 70 / (x1 - x0)
          const pc = (xc - x0) / (x1 - x0)
          const hotC = s.status === 'investigating' || s.status === 'patching' || maxHot > 0.5 ? C.red : C.amber
          g.addColorStop(0, rgba(LINE, a))
          g.addColorStop(Math.max(0, pc - span), rgba(LINE, a))
          g.addColorStop(pc, rgba(hotC, Math.min(1, a + maxHot)))
          g.addColorStop(Math.min(1, pc + span), rgba(LINE, a))
          g.addColorStop(1, rgba(LINE, a))
          ctx.strokeStyle = g
        } else ctx.strokeStyle = rgba(LINE, a)
        ctx.lineWidth = 1.15
        ctx.stroke()
      }

      // posiciones de nodos sobre el terreno
      const pos = {}
      for (const a of s.surface) {
        const L = LAYOUT[a.id]; if (!L) continue
        const [x, y] = point(L[0], L[1])
        pos[a.id] = { x, y: y - 14, a }
      }

      // enlaces + paquetes de tráfico
      LINKS.forEach(([fa, fb]) => {
        const A = pos[fa], B = pos[fb]; if (!A || !B) return
        ctx.strokeStyle = paused ? 'rgba(92,101,116,0.25)' : 'rgba(242,163,199,0.28)'; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y); ctx.stroke()
      })
      for (const pk of packets) {
        const [fa, fb] = LINKS[pk.link]; const A = pos[fa], B = pos[fb]; if (!A || !B) continue
        if (paused) continue
        pk.p = (pk.p + (reduce ? 0 : pk.speed * energy * 0.016)) % 1
        const x = A.x + (B.x - A.x) * pk.p, y = A.y + (B.y - A.y) * pk.p
        ctx.fillStyle = C.lime; ctx.fillRect(x - 4, y - 4, 8, 8)
      }

      // cajas de servidor
      for (const id in pos) {
        const { x, y, a } = pos[id]
        const bad = a.status === 'bad', warn = a.status === 'warn'
        const w = small ? 22 : 30, h = small ? 6 : 7
        if (bad || warn) {
          ctx.fillStyle = bad ? 'rgba(255,77,94,0.22)' : 'rgba(245,165,36,0.2)'
          ctx.beginPath(); ctx.arc(x, y + h, 26 + 4 * Math.sin(t * 6), 0, Math.PI * 2); ctx.fill()
        }
        for (let r = 0; r < 3; r++) {
          const yy = y + r * (h + 1)
          ctx.fillStyle = paused ? '#3B4656' : bad ? '#FF4D5E' : warn ? '#F5A524' : C.box
          ctx.fillRect(x - w / 2, yy, w, h)
          ctx.fillStyle = paused ? '#2A3340' : r === 0 ? '#8FA4F5' : C.bar
          ctx.fillRect(x - w / 2 + 4, yy + h / 2 - 1, w - 8, 2)
        }
        if (!small) {
          ctx.font = '500 9.5px "DM Mono", ui-monospace, monospace'
          ctx.textAlign = 'center'
          ctx.fillStyle = paused ? '#5C6574' : bad ? '#FF4D5E' : warn ? '#F5A524' : 'rgba(215,240,75,0.85)'
          ctx.fillText(a.name.toUpperCase(), x, y + 3 * (h + 1) + 12)
          ctx.textAlign = 'left'
        }
      }

      // el agente: esfera de alambre lima con su "red" de puntos
      const incident = Object.values(s.incidents).find((x) => ['investigating', 'pending_approval', 'applying'].includes(x.status))
      const hotAsset = s.surface.find((a) => a.status !== 'ok')
      const ids = Object.keys(pos)
      if (hotAsset && pos[hotAsset.id]) eye.target = hotAsset.id
      else if (incident) {
        const m = s.surface.find((a) => a.name === incident.target); if (m) eye.target = m.id
      } else if (now > eye.switchAt && ids.length) {
        eye.target = ids[Math.floor(Math.random() * ids.length)]; eye.switchAt = now + 3200
      }
      const tp = pos[eye.target]
      if (tp && !paused) {
        if (!eye.init) { eye.x = tp.x; eye.y = tp.y - 40; eye.init = true }
        eye.x += (tp.x - eye.x) * 0.04; eye.y += (tp.y - 46 - eye.y) * 0.04
        const R = small ? 16 : 24
        ctx.strokeStyle = 'rgba(215,240,75,0.75)'; ctx.lineWidth = 1
        for (let k = 0; k < 4; k++) {
          ctx.beginPath(); ctx.ellipse(eye.x, eye.y, R * Math.abs(Math.cos(t * 0.8 + k * 0.8)), R, 0, 0, Math.PI * 2); ctx.stroke()
          ctx.beginPath(); ctx.ellipse(eye.x, eye.y, R, R * Math.abs(Math.sin(t * 0.6 + k * 0.7)), 0, 0, Math.PI * 2); ctx.stroke()
        }
        // líneas del agente hacia el asset que mira
        ctx.strokeStyle = 'rgba(215,240,75,0.55)'
        ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(eye.x, eye.y + R); ctx.lineTo(tp.x, tp.y); ctx.stroke(); ctx.setLineDash([])
        const corners = [[-1.9, -0.6], [1.7, -1.1], [2.1, 0.9], [-1.4, 1.3]]
        ctx.beginPath()
        corners.forEach(([cx, cy], k) => {
          const px = eye.x + cx * R + Math.sin(t + k) * 3, py = eye.y + cy * R + Math.cos(t * 1.2 + k) * 3
          k ? ctx.lineTo(px, py) : ctx.moveTo(px, py)
        })
        ctx.closePath(); ctx.stroke()
        corners.forEach(([cx, cy], k) => {
          ctx.fillStyle = C.lime
          ctx.fillRect(eye.x + cx * R + Math.sin(t + k) * 3 - 3, eye.y + cy * R + Math.cos(t * 1.2 + k) * 3 - 3, 6, 6)
        })
      }

      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf); ro.disconnect() }
  }, [])

  const incident = Object.values(state.incidents).find((x) => ['investigating', 'pending_approval', 'applying'].includes(x.status))
  const bad = IS_DEMO ? state.surface.filter((a) => a.status !== 'ok') : []
  if (bare) return (
    <div ref={wrap} className="absolute inset-0">
      <canvas ref={canvas} className="absolute inset-0" aria-hidden="true" />
    </div>
  )

  const paused = state.monitoring === false
  const headline = paused
    ? { text: 'Constant review is paused', tone: 'text-mute-300' }
    : incident
    ? { text: incident.title, tone: 'text-bad' }
    : bad.length ? { text: `${bad.length} asset needs attention`, tone: 'text-warn' }
    : IS_DEMO ? { text: 'Every service running clean', tone: 'text-mute-100' }
    : { text: 'No open incidents', tone: 'text-mute-100' }
  const sub = paused
    ? 'Rootlane cannot see new attacks until you turn constant review back on.'
    : incident
    ? (incident.status === 'pending_approval' ? (IS_DEMO || incident.verification?.replica_after ? `Fix proven on a replica for ${incident.target}. One approval ships it.` : `A fix for ${incident.target} is waiting for approval.`) : incident.status === 'applying' ? `Applying the approved fix to production…` : `Rootlane is investigating ${incident.target} on its own.`)
    : IS_DEMO ? `Watching ${state.surface.length} assets in ${state.summary.repo} and ${state.summary.infra}, live.`
    : state.connected ? `Reading request events from ${state.summary.infra}.` : 'The Rootlane API is not reachable right now.'

  return (
    <section className="panel relative overflow-hidden">
      <div ref={wrap} className="relative h-[400px] w-full sm:h-[440px]">
        <canvas ref={canvas} className="absolute inset-0" aria-label="Live map of services, traffic and the Rootlane agent" role="img" />
        <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-col items-center px-4 pt-6 text-center">
          <div className="font-mono text-[12px] tracking-[0.3em] text-mute-300">{IS_DEMO || state.connected ? '[ ROOTLANE · LIVE ]' : '[ ROOTLANE · OFFLINE ]'}</div>
          <AnimatePresence mode="wait">
            <motion.h2 key={headline.text} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              className={`mt-2 max-w-[22ch] text-[28px] font-semibold leading-[1.05] tracking-[-0.03em] sm:max-w-none sm:text-[40px] ${headline.tone}`}
              style={{ textWrap: 'balance' }}>
              {headline.text}
            </motion.h2>
          </AnimatePresence>
          <p className="mt-2 max-w-[60ch] text-[13px] text-mute-300 sm:text-[15px]">{sub}</p>
        </div>
      </div>
      <div className="relative overflow-hidden border-t border-ink-700 py-2">
        <div className="ticker flex w-max gap-10 whitespace-nowrap font-mono text-[11px] tracking-[0.25em] text-[#8FA4F5]/80">
          {Array.from({ length: 2 }).map((_, k) => (
            <span key={k} className="flex gap-10">
              {Array.from({ length: 6 }).map((__, j) => <span key={j}>WATCH · TRACE · PATCH · DEPLOY · VERIFY</span>)}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}
