/*
  CODE CURTAIN · versión Rootlane
  --------------------------------
  Basado en el componente "Code Curtain" (cortina de código con física de tela)
  y mezclado con la idea del "Compare" (una línea brillante que barre y muestra el antes/después).

  Historia en bucle (~15 s), contada solo con código:
    1. WRITING   – el código se escribe solo, línea por línea.
    2. LIVE      – la cortina ondea tranquila (la app funcionando).
    3. ATTACK    – un impacto: todo se pone ROJO desde el punto de entrada y la tela se rasga.
    4. PATCHING  – la línea de escaneo de Rootlane barre de izquierda a derecha y lo devuelve a la normalidad.
    5. REDEPLOY  – la cortina se vuelve a colgar desde la barra (= redeploy) y empieza otra vez.

  Se puede arrastrar con el mouse. Avisa en qué fase está con `onPhase`.
*/
import { useEffect, useRef } from 'react'

const SOURCE =
  "export function verifyToken(token) { const { header } = decode(token); " +
  "return jwt.verify(token, KEY, { algorithms: [header.alg] }) } " +
  "app.get('/admin', auth, async (req, res) => { const user = await db.users.find(req.user.id); " +
  "if (!user.isAdmin) return res.sendStatus(403); res.json(await audit.latest(50)) }) " +
  "router.post('/upload', limit('5mb'), (req, res) => s3.put(BUCKET, req.file.name, req.file.body)) " +
  "const pool = new Pool({ host: env.DB_HOST, ssl: true, max: 20 }); " +
  "export async function deploy(sha) { await pipeline.start({ sha, stage: 'prod' }); return watch(sha) } "

// #region física (verlet) — portada del componente original
function buildCloth(cols, rows, cellW, cellH, stretch) {
  const n = cols * rows
  const m = cols * (rows - 1) + (cols - 1) * rows
  const cl = {
    cols, rows,
    x: new Float64Array(n), y: new Float64Array(n), px: new Float64Array(n), py: new Float64Array(n),
    pin: new Uint8Array(n), a: new Int32Array(m), b: new Int32Array(m), rest: new Float64Array(m),
    lo: new Float64Array(m), hi: new Float64Array(m), alive: new Uint8Array(m).fill(1),
    down: new Int32Array(n).fill(-1), right: new Int32Array(n).fill(-1),
  }
  let k = 0
  const link = (i, j, rest, lo, hi) => { cl.a[k] = i; cl.b[k] = j; cl.rest[k] = rest; cl.lo[k] = rest * lo; cl.hi[k] = rest * hi; return k++ }
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const i = r * cols + c
    cl.x[i] = cl.px[i] = c * cellW
    cl.y[i] = cl.py[i] = r * cellH
    cl.pin[i] = r === 0 ? 1 : 0
  }
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const i = r * cols + c
    if (r < rows - 1) cl.down[i] = link(i, i + cols, cellH, 0.02, stretch)
    if (c < cols - 1) cl.right[i] = link(i, i + 1, cellW, 0.6, r === 0 ? stretch : 4)
  }
  return cl
}

function step(cl, gravity, damping, wind, t) {
  const { cols, rows, x, y, px, py, pin } = cl
  for (let i = 0; i < x.length; i++) {
    if (pin[i]) continue
    const vx = (x[i] - px[i]) * damping, vy = (y[i] - py[i]) * damping
    px[i] = x[i]; py[i] = y[i]
    let fx = 0
    if (wind) {
      const c = i % cols, r = (i - c) / cols
      fx = wind * 0.02 * (r / rows) * (0.55 + 0.45 * Math.sin(t * 1.1 + c * 0.21 - r * 0.07) * Math.sin(t * 0.37 + 1.7))
    }
    x[i] += vx + fx
    y[i] += vy + gravity
  }
}

function relax(cl, iterations, tearAt) {
  const { x, y, pin, a, b, rest, lo, hi, alive } = cl
  for (let it = 0; it < iterations; it++) {
    for (let k = 0; k < a.length; k++) {
      if (!alive[k]) continue
      const i = a[k], j = b[k]
      const dx = x[j] - x[i], dy = y[j] - y[i]
      const d = Math.hypot(dx, dy)
      if (d === 0) continue
      if (tearAt > 0 && d > rest[k] * tearAt) { alive[k] = 0; continue }
      let target
      if (d < lo[k]) target = lo[k]
      else if (d > hi[k]) target = hi[k]
      else continue
      const f = (target - d) / d / 2
      const ox = dx * f, oy = dy * f
      if (!pin[i]) { x[i] -= ox; y[i] -= oy }
      if (!pin[j]) { x[j] += ox; y[j] += oy }
    }
  }
}

function push(cl, mx, my, radius, strength, dx, dy) {
  const { x, y, pin } = cl
  const r2 = radius * radius
  for (let i = 0; i < x.length; i++) {
    if (pin[i]) continue
    const ex = x[i] - mx, ey = y[i] - my
    const ls = ex * ex + ey * ey
    if (ls >= r2) continue
    const f = smoothstep(r2, -0.4 * r2, ls)
    const d = Math.sqrt(ls) || 1
    x[i] += (ex / d) * f * strength * 0.75 + dx * f * 0.2
    y[i] += (ey / d) * f * strength * 0.75 + dy * f * 0.2
  }
}

function nearest(cl, mx, my, radius) {
  let best = -1, bd = radius * radius
  for (let i = 0; i < cl.x.length; i++) {
    const d = (cl.x[i] - mx) ** 2 + (cl.y[i] - my) ** 2
    if (d < bd) { bd = d; best = i }
  }
  return best
}

function fold(cl, i) {
  const { x, y, a, b, rest, alive, right, cols } = cl
  let sum = 0, n = 0
  const ls = [right[i], i % cols > 0 ? right[i - 1] : -1]
  for (const l of ls) {
    if (l < 0 || !alive[l]) continue
    sum += Math.hypot(x[b[l]] - x[a[l]], y[b[l]] - y[a[l]]) / rest[l]
    n++
  }
  return n ? sum / n : 1
}

function bunch(cl, k) {
  const { cols, x, y, px, py, pin } = cl
  for (let i = cols; i < x.length; i++) {
    if (pin[i]) continue
    const top = i % cols
    y[i] = py[i] = y[top] + (y[i] - y[top]) * k
    px[i] = x[i]
  }
}

function scrambleIndex(i, tick, n) {
  let h = (i * 374761393 + Math.floor(tick / 4) * 668265263) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  return ((h ^ (h >>> 16)) >>> 0) % n
}

function smoothstep(e0, e1, v) {
  const t = Math.min(1, Math.max(0, (v - e0) / (e1 - e0)))
  return t * t * (3 - 2 * t)
}
// #endregion

function buildAtlas(chars, fontSize, font, color, dpr) {
  const size = Math.ceil(fontSize * 1.4)
  return {
    size,
    glyphs: chars.map((ch) => {
      const c = document.createElement('canvas')
      c.width = c.height = Math.ceil(size * dpr)
      const g = c.getContext('2d')
      g.scale(dpr, dpr)
      g.font = font
      g.textAlign = 'center'
      g.textBaseline = 'middle'
      g.fillStyle = color
      g.fillText(ch, size / 2, size / 2)
      return c
    }),
  }
}

// Duración de cada fase, en frames (60 fps)
const T = { write: 170, live: 170, attack: 150, patch: 150, redeploy: 70 }

export default function CodeCurtain({
  text = SOURCE,
  columns = 46,
  rows = 34,
  maxWidth = 620,
  maxHeight = 560,
  ink = '#AEB9D6',
  alert = '#FF4D5E',
  heal = '#D7F04B',
  scan = '#8FA4F5',
  fontFamily = '"DM Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
  className = '',
  onPhase,
}) {
  const rootRef = useRef(null)
  const canvasRef = useRef(null)
  const phaseCb = useRef(onPhase)
  phaseCb.current = onPhase

  useEffect(() => {
    const root = rootRef.current, canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const woven = text.replace(/\s+/g, ' ')
    const chars = [...new Set(woven)].filter((c) => c !== ' ')
    const charIndex = new Map(chars.map((c, i) => [c, i]))
    const cols = columns, rws = rows

    let W = 0, H = 0, dpr = 1, ox = 0, oy = 0, cw = 0, chh = 0, cell = 0, fontSize = 12
    let cl = buildCloth(cols, rws, 1, 1, 1.1)
    let glyph = new Int16Array(0)
    let atlas = null
    let jumble = new Float64Array(0)
    let revealAt = new Float64Array(0), redAt = new Float64Array(0), healAt = new Float64Array(0)
    let tick = 0, phase = '', phaseStart = 0, raf = 0, acc = 0, last = 0, t = 0
    let impact = { x: 0, y: 0, i: -1 }
    let scanX = -1, tearAt = 0
    let grabbed = -1, gx = 0, gy = 0, hovering = false, mx = 0, my = 0, lastMx = 0, lastMy = 0
    let visible = true

    const setPhase = (p) => { phase = p; phaseStart = tick; phaseCb.current?.(p) }

    const rebuildAtlas = () => {
      const font = `500 ${fontSize.toFixed(2)}px ${fontFamily}`
      atlas = {
        ink: buildAtlas(chars, fontSize, font, ink, dpr),
        red: buildAtlas(chars, fontSize, font, alert, dpr),
        lime: buildAtlas(chars, fontSize, font, heal, dpr),
      }
    }

    const hang = (startWriting) => {
      cw = Math.max(120, Math.min(maxWidth, W - 40))
      chh = Math.max(120, Math.min(maxHeight, H - 150))
      const cellW = cw / (cols - 1), cellH = chh / (rws - 1)
      cell = Math.min(cellW, cellH)
      ox = (W - cw) / 2
      oy = Math.max(72, (H - chh) / 2 - 10)
      cl = buildCloth(cols, rws, cellW, cellH, 1.1)
      glyph = new Int16Array(cols * rws)
      for (let r = 0; r < rws; r++) for (let c = 0; c < cols; c++) {
        const ch = woven[(c + r * cols) % woven.length]
        glyph[r * cols + c] = ch === ' ' ? -1 : (charIndex.get(ch) ?? -1)
      }
      jumble = new Float64Array(cols * rws)
      revealAt = new Float64Array(cols * rws)
      redAt = new Float64Array(cols * rws).fill(Infinity)
      healAt = new Float64Array(cols * rws).fill(Infinity)
      grabbed = -1; scanX = -1; tearAt = 0
      const fs = Math.max(8, cellH * 1.15)
      if (fs !== fontSize || !atlas) { fontSize = fs; rebuildAtlas() }
      if (reduce) {
        for (let i = 0; i < 200; i++) physics()
        revealAt.fill(0)
        setPhase('live')
        return
      }
      if (startWriting) {
        bunch(cl, 0.08)
        // efecto "se escribe solo": cada fila empieza un poco después y se teclea de izquierda a derecha
        for (let r = 0; r < rws; r++) for (let c = 0; c < cols; c++) revealAt[r * cols + c] = tick + r * 3.6 + c * 0.32
        setPhase('writing')
      }
    }

    const physics = () => {
      if (grabbed >= 0) {
        cl.px[grabbed] = cl.x[grabbed]; cl.py[grabbed] = cl.y[grabbed]
        cl.x[grabbed] = gx; cl.y[grabbed] = gy
      }
      step(cl, 0.2, 0.99, reduce ? 0 : phase === 'attack' ? 1.2 : 0.35, t)
      relax(cl, 5, tearAt)
      t += 1 / 60
    }

    const story = () => {
      const age = tick - phaseStart
      if (phase === 'writing' && age > T.write) setPhase('live')
      else if (phase === 'live' && age > T.live) {
        // impacto: un punto aleatorio en la mitad baja de la cortina
        const c = Math.floor(cols * (0.3 + Math.random() * 0.4)), r = Math.floor(rws * (0.45 + Math.random() * 0.25))
        impact = { i: r * cols + c, x: cl.x[r * cols + c], y: cl.y[r * cols + c] }
        for (let i = 0; i < redAt.length; i++) {
          const d = Math.hypot(cl.x[i] - impact.x, cl.y[i] - impact.y) / cell
          redAt[i] = tick + d * 0.9
          jumble[i] = tick + d * 0.9 + 18
        }
        tearAt = 3.2
        setPhase('attack')
      } else if (phase === 'attack') {
        // el atacante "jala" la tela desde el punto de impacto durante unos frames
        if (age < 22) {
          const k = impact.i
          cl.pin[k] = 1
          cl.x[k] += cell * 0.9 * (impact.x > cw / 2 ? 1 : -1)
          cl.y[k] += cell * 1.1
          push(cl, cl.x[k], cl.y[k], cell * 6, 6, 0, 0)
        } else if (age === 22) cl.pin[impact.i] = 0
        if (age > T.attack) { tearAt = 0; scanX = -cell * 4; setPhase('patching') }
      } else if (phase === 'patching') {
        scanX += (cw + cell * 8) / T.patch
        for (let i = 0; i < healAt.length; i++) {
          if (healAt[i] === Infinity && cl.x[i] < scanX) { healAt[i] = tick; jumble[i] = tick + 10 }
        }
        if (age > T.patch) { scanX = -1; setPhase('redeployed') }
      } else if (phase === 'redeployed' && age > T.redeploy) hang(true)
    }

    const draw = () => {
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      if (!atlas) return
      const { x, y, down, alive, a, b, rest } = cl
      const size = atlas.ink.size, half = size / 2

      // barra (el "rod") de la que cuelga el código = el servidor
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const ry = oy - fontSize * 0.7
      const rodColor = phase === 'attack' ? alert : phase === 'patching' || phase === 'redeployed' ? heal : scan
      ctx.strokeStyle = rodColor; ctx.fillStyle = rodColor; ctx.lineWidth = 2; ctx.lineCap = 'round'
      ctx.beginPath(); ctx.moveTo(ox - 18, ry); ctx.lineTo(ox + cw + 18, ry); ctx.stroke()
      for (const ex of [ox - 22, ox + cw + 22]) { ctx.beginPath(); ctx.arc(ex, ry, 4, 0, Math.PI * 2); ctx.fill() }

      for (let i = 0; i < glyph.length; i++) {
        let g = glyph[i]
        if (g < 0 || tick < revealAt[i]) continue
        if (!reduce && (jumble[i] > tick || tick - revealAt[i] < 6)) g = scrambleIndex(i, tick, chars.length)
        let l = down[i]
        if (l < 0 || !alive[l]) l = i >= cols ? down[i - cols] : -1
        let cos = 1, sin = 0, along = 1
        if (l >= 0 && alive[l]) {
          const dx = x[b[l]] - x[a[l]], dy = y[b[l]] - y[a[l]]
          const d = Math.hypot(dx, dy)
          if (d > 0) { cos = dy / d; sin = -dx / d; along = (d / rest[l]) * 1.15 }
        }
        const across = fold(cl, i)
        const sx = Math.min(1, Math.max(0.3, across)), sy = Math.min(1, Math.max(0.3, along))
        let light = 0.3 + 0.7 * smoothstep(0.45, 0.95, Math.min(across, along))

        // ¿de qué color va este caracter?
        let set = atlas.ink
        const healedFor = tick - healAt[i]
        if (tick >= redAt[i] && healedFor < 0) set = atlas.red
        else if (healedFor >= 0 && healedFor < 45) set = atlas.lime
        // brillo de "recién escrito"
        const fresh = tick - revealAt[i]
        if (phase === 'writing' && fresh < 10) { set = atlas.lime; light = Math.max(light, 1) }
        // el puntero ilumina
        if (hovering && grabbed < 0 && Math.hypot(x[i] - mx, y[i] - my) < 60) light = Math.min(1, light + 0.3)

        const tx = x[i] + ox, ty = y[i] + oy
        ctx.setTransform(dpr * cos * sx, dpr * sin * sx, -dpr * sin * sy, dpr * cos * sy, dpr * tx, dpr * ty)
        ctx.globalAlpha = light * (set === atlas.ink ? 0.85 : 1)
        ctx.drawImage(set.glyphs[g], -half, -half, size, size)
      }
      ctx.globalAlpha = 1

      // cursor de escritura (bloque lima) al final de la línea que se está escribiendo
      if (phase === 'writing') {
        let head = -1
        for (let i = 0; i < revealAt.length; i++) if (revealAt[i] <= tick) head = Math.max(head, i)
        if (head >= 0 && Math.floor(tick / 8) % 2 === 0) {
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
          ctx.fillStyle = heal
          ctx.fillRect(x[head] + ox + cell * 0.6, y[head] + oy - fontSize * 0.5, fontSize * 0.55, fontSize)
        }
      }

      // la línea de escaneo de Rootlane (idea del "Compare"): brilla, deja chispas y "cura" lo que toca
      if (phase === 'patching' && scanX > -cell * 4) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        const sx = scanX + ox
        const top = oy - fontSize, bot = oy + chh + cell * 6
        const g = ctx.createLinearGradient(sx - 90, 0, sx, 0)
        g.addColorStop(0, 'rgba(143,164,245,0)')
        g.addColorStop(1, 'rgba(143,164,245,0.22)')
        ctx.fillStyle = g
        ctx.fillRect(sx - 90, top, 90, bot - top)
        const v = ctx.createLinearGradient(0, top, 0, bot)
        v.addColorStop(0, 'rgba(215,240,75,0)'); v.addColorStop(0.15, heal); v.addColorStop(0.85, heal); v.addColorStop(1, 'rgba(215,240,75,0)')
        ctx.fillStyle = v
        ctx.fillRect(sx - 1, top, 2, bot - top)
        for (let s = 0; s < 26; s++) {
          const py = top + Math.random() * (bot - top), px = sx + Math.random() * 26
          ctx.globalAlpha = Math.random()
          ctx.fillStyle = s % 3 ? '#ffffff' : heal
          ctx.fillRect(px, py, 1.6, 1.6)
        }
        ctx.globalAlpha = 1
        // asa del slider, como en Compare
        ctx.fillStyle = '#fff'
        const hy = oy + chh / 2
        ctx.beginPath(); ctx.roundRect(sx - 9, hy - 9, 18, 18, 4); ctx.fill()
        ctx.fillStyle = '#0B0E13'
        for (const dy of [-4, 0, 4]) { ctx.beginPath(); ctx.arc(sx, hy + dy, 1.4, 0, Math.PI * 2); ctx.fill() }
      }
    }

    const loop = (now) => {
      raf = requestAnimationFrame(loop)
      if (!visible) { last = now; return }
      const dt = last ? Math.min(0.1, (now - last) / 1000) : 1 / 60
      last = now
      acc += dt
      let n = 0
      while (acc >= 1 / 60 && n < 4) { physics(); if (!reduce) story(); tick++; acc -= 1 / 60; n++ }
      if (n === 4) acc = 0
      draw()
    }

    const resize = () => {
      const r = root.getBoundingClientRect()
      const w = Math.round(r.width), h = Math.round(r.height)
      if (w === W && h === H) return
      W = w; H = h
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.max(1, Math.round(W * dpr)); canvas.height = Math.max(1, Math.round(H * dpr))
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px'
      atlas = null
      hang(true)
      draw()
    }

    const local = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left - ox, e.clientY - r.top - oy] }
    const onDown = (e) => {
      if (e.button !== 0) return
      const [px, py] = local(e)
      const i = nearest(cl, px, py, Math.max(20, cell * 2))
      if (i < 0 || cl.pin[i]) return
      grabbed = i; cl.pin[i] = 1; gx = px; gy = py
      canvas.setPointerCapture(e.pointerId); canvas.style.cursor = 'grabbing'
    }
    const onMove = (e) => {
      const [px, py] = local(e)
      hovering = true; mx = px; my = py
      if (grabbed >= 0) { gx = px; gy = py }
      else {
        push(cl, px, py, 70, 4, px - lastMx, py - lastMy)
        const until = tick + 14 + Math.random() * 12
        for (let i = 0; i < jumble.length; i++) if ((cl.x[i] - px) ** 2 + (cl.y[i] - py) ** 2 < 35 * 35) jumble[i] = Math.max(jumble[i], until)
        canvas.style.cursor = nearest(cl, px, py, Math.max(20, cell * 2)) >= 0 ? 'grab' : 'default'
      }
      lastMx = px; lastMy = py
    }
    const release = () => {
      if (grabbed < 0) return
      const i = grabbed
      cl.pin[i] = 0
      const vx = cl.x[i] - cl.px[i], vy = cl.y[i] - cl.py[i], v = Math.hypot(vx, vy), cap = cell * 3
      if (v > cap) { cl.px[i] = cl.x[i] - (vx / v) * cap; cl.py[i] = cl.y[i] - (vy / v) * cap }
      grabbed = -1; canvas.style.cursor = 'grab'
    }
    const onLeave = () => { hovering = false }

    const ro = new ResizeObserver(resize); ro.observe(root)
    const io = new IntersectionObserver(([en]) => { visible = en.isIntersecting }); io.observe(root)
    canvas.addEventListener('pointerdown', onDown)
    canvas.addEventListener('pointermove', onMove)
    canvas.addEventListener('pointerup', release)
    canvas.addEventListener('pointercancel', release)
    canvas.addEventListener('pointerleave', onLeave)
    resize()
    raf = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); io.disconnect()
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerup', release)
      canvas.removeEventListener('pointercancel', release)
      canvas.removeEventListener('pointerleave', onLeave)
    }
  }, [text, columns, rows, maxWidth, maxHeight, ink, alert, heal, scan, fontFamily])

  return (
    <div ref={rootRef} className={'relative h-full w-full select-none overflow-hidden ' + className}>
      <canvas ref={canvasRef} className="absolute left-0 top-0 block" style={{ touchAction: 'none', maxWidth: 'none' }}
        role="img" aria-label="Animated curtain of source code that gets attacked, turns red, and is patched by Rootlane" />
    </div>
  )
}
