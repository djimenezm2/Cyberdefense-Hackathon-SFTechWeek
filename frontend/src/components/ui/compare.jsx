/*
  COMPARE · versión Rootlane
  Basado en el componente "Compare" (slider antes/después con línea brillante y chispas).
  Cambios para este proyecto:
   - En vez de dos imágenes recibe dos bloques de contenido (`first` = antes, `second` = después).
   - Las chispas se dibujan en un canvas propio (sin @tabler ni SparklesCore).
   - El asa usa un ícono de lucide-react.
*/
import { useCallback, useEffect, useRef, useState } from 'react'
import { GripVertical } from 'lucide-react'

function Sparkles({ color = '#D7F04B' }) {
  const ref = useRef(null)
  useEffect(() => {
    const cv = ref.current, ctx = cv.getContext('2d')
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let raf = 0
    const parts = Array.from({ length: 70 }, () => ({ x: Math.random(), y: Math.random(), v: 0.2 + Math.random() * 0.8, s: 0.6 + Math.random() * 1.2, a: Math.random() }))
    const loop = () => {
      const r = cv.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1)
      if (cv.width !== Math.round(r.width * dpr)) { cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr) }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, r.width, r.height)
      for (const p of parts) {
        p.x += p.v * 0.012; p.a -= 0.012
        if (p.x > 1 || p.a <= 0) { p.x = 0; p.y = Math.random(); p.a = 0.4 + Math.random() * 0.6 }
        ctx.globalAlpha = p.a * (1 - p.x)
        ctx.fillStyle = Math.random() > 0.7 ? color : '#ffffff'
        ctx.fillRect(p.x * r.width, p.y * r.height, p.s, p.s)
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [color])
  return <canvas ref={ref} className="h-full w-full" aria-hidden="true" />
}

export function Compare({
  first,
  second,
  className = '',
  initialSliderPercentage = 50,
  slideMode = 'hover',
  showHandlebar = true,
  autoplay = false,
  autoplayDuration = 4000,
  sparkles = true,
  quiet = false,
}) {
  const [pct, setPct] = useState(initialSliderPercentage)
  const [dragging, setDragging] = useState(false)
  const ref = useRef(null)
  const raf = useRef(0)

  const startAutoplay = useCallback(() => {
    if (!autoplay || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const t0 = performance.now()
    const tick = (now) => {
      const p = ((now - t0) % (autoplayDuration * 2)) / autoplayDuration
      const v = p <= 1 ? p : 2 - p
      setPct(8 + (v * v * (3 - 2 * v)) * 84)
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
  }, [autoplay, autoplayDuration])
  const stopAutoplay = useCallback(() => cancelAnimationFrame(raf.current), [])

  useEffect(() => { startAutoplay(); return stopAutoplay }, [startAutoplay, stopAutoplay])

  const move = (clientX) => {
    if (!ref.current) return
    if (slideMode === 'hover' || dragging) {
      const r = ref.current.getBoundingClientRect()
      setPct(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)))
    }
  }

  return (
    <div ref={ref}
      className={'relative select-none overflow-hidden ' + className}
      style={{ cursor: slideMode === 'drag' ? 'grab' : 'col-resize' }}
      onMouseEnter={stopAutoplay}
      onMouseLeave={() => { setDragging(false); if (slideMode === 'hover') setPct(initialSliderPercentage); startAutoplay() }}
      onMouseMove={(e) => move(e.clientX)}
      onMouseDown={() => slideMode === 'drag' && setDragging(true)}
      onMouseUp={() => setDragging(false)}
      onTouchStart={(e) => { stopAutoplay(); setDragging(true); move(e.touches[0].clientX) }}
      onTouchMove={(e) => move(e.touches[0].clientX)}
      onTouchEnd={() => { setDragging(false) }}
      role="slider" aria-label="Before and after" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') { stopAutoplay(); setPct((p) => Math.max(0, p - 5)) }
        if (e.key === 'ArrowRight') { stopAutoplay(); setPct((p) => Math.min(100, p + 5)) }
      }}>
      {/* después (abajo) */}
      <div className="absolute inset-0">{second}</div>
      {/* antes (arriba, recortado) */}
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pct}% 0 0)` }}>{first}</div>

      {/* la línea brillante */}
      <div className={`pointer-events-none absolute top-0 z-30 h-full w-px bg-gradient-to-b from-transparent from-[5%] to-transparent to-[95%] ${quiet ? 'via-[#8FA4F5]' : 'via-[#D7F04B]'}`} style={{ left: `${pct}%` }}>
        <div className="absolute left-0 top-1/2 h-full w-36 -translate-y-1/2 bg-gradient-to-r from-[#8FA4F5]/50 via-transparent to-transparent opacity-40 [mask-image:radial-gradient(100px_at_left,white,transparent)]" />
        {!quiet && <div className="absolute left-0 top-1/2 h-1/2 w-10 -translate-y-1/2 bg-gradient-to-r from-[#D7F04B]/80 via-transparent to-transparent [mask-image:radial-gradient(50px_at_left,white,transparent)]" />}
        {sparkles && (
          <div className="absolute -right-10 top-1/2 h-3/4 w-10 -translate-y-1/2 [mask-image:radial-gradient(100px_at_left,white,transparent)]">
            <Sparkles />
          </div>
        )}
        {showHandlebar && (
          <div className={`absolute -right-2.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-md bg-white ${quiet ? '' : 'shadow-[0_0_18px_rgba(215,240,75,0.5)]'}`}>
            <GripVertical className="h-3.5 w-3.5 text-ink-950" />
          </div>
        )}
      </div>
    </div>
  )
}

export default Compare
