import { useState, FormEvent, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Mail, Lock, ArrowRight, FlaskConical, BarChart3, Database, Brain } from 'lucide-react'
import toast from 'react-hot-toast'
import { login as loginRequest } from '../api/auth'
import { errorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'

// ─── Animated particle network canvas ──────────────────────────────────────────

function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number
    const PARTICLE_COUNT = 70
    const MAX_DIST = 130
    const W = canvas.width = canvas.offsetWidth
    const H = canvas.height = canvas.offsetHeight

    type Particle = { x: number; y: number; vx: number; vy: number; r: number; opacity: number }
    const particles: Particle[] = Array.from({ length: PARTICLE_COUNT }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r: Math.random() * 2.5 + 1,
      opacity: Math.random() * 0.5 + 0.3,
    }))

    const draw = () => {
      ctx.clearRect(0, 0, W, H)
      for (const p of particles) {
        p.x += p.vx; p.y += p.vy
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0

        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(255,255,255,${p.opacity})`
        ctx.fill()
      }

      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < MAX_DIST) {
            const alpha = (1 - dist / MAX_DIST) * 0.25
            ctx.beginPath()
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.strokeStyle = `rgba(255,200,210,${alpha})`
            ctx.lineWidth = 0.8
            ctx.stroke()
          }
        }
      }
      animId = requestAnimationFrame(draw)
    }

    draw()
    const handleResize = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    window.addEventListener('resize', handleResize)
    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', handleResize) }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
}

// ─── Feature pill ───────────────────────────────────────────────────────────────

function Feature({ icon: Icon, text }: { icon: React.ElementType; text: string }) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-2.5 bg-white/10 backdrop-blur-sm rounded-full border border-white/20 hover:bg-white/15 transition-colors">
      <Icon size={14} className="text-white shrink-0" />
      <span className="text-white/90 text-sm font-medium">{text}</span>
    </div>
  )
}

// ─── Main ───────────────────────────────────────────────────────────────────────

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const data = await loginRequest(email, password)
      setAuth(data.access_token, data.user)
      navigate('/')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not sign you in'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex bg-white">
      {/* ── Left panel: animated branded hero ──────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[54%] relative overflow-hidden flex-col">
        {/* Layered gradient background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#6B0018] via-[#C8102E] to-[#8B0000]" />
        {/* Subtle animated blobs */}
        <div className="absolute top-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-white/5 animate-blob1" />
        <div className="absolute bottom-[-10%] left-[-15%] w-[400px] h-[400px] rounded-full bg-white/5 animate-blob2" />
        <div className="absolute top-[40%] left-[30%] w-[250px] h-[250px] rounded-full bg-[#FFB3C1]/10 animate-blob3" />
        {/* Particle network overlay */}
        <ParticleCanvas />

        {/* Content */}
        <div className="relative z-10 flex flex-col h-full p-12">
          {/* McGill logo */}
          <div className="flex items-center gap-3">
            <div className="bg-white rounded-lg p-1.5 shadow-lg">
              <img src="/mcgill.png" alt="McGill" className="h-9 w-auto" />
            </div>
            <div>
              <p className="text-white font-bold text-base leading-tight">McGill University</p>
              <p className="text-white/70 text-xs leading-tight">Faculty of Agricultural & Environmental Sciences</p>
            </div>
          </div>

          {/* Hero text */}
          <div className="mt-auto mb-auto pt-20">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-white/15 rounded-full border border-white/25 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-white/90 text-xs font-medium">AI-Powered Research Platform</span>
            </div>
            <h1 className="text-5xl font-extrabold text-white leading-tight tracking-tight mb-4">
              Meat & Cheese<br />
              <span className="text-white/80">Database</span>
            </h1>
            <p className="text-white/75 text-lg leading-relaxed max-w-md">
              Extract structured scientific data from research papers using Docling,
              PP-Chart2Table, and Llama 4 — all in one collaborative platform.
            </p>

            {/* Features */}
            <div className="mt-8 flex flex-wrap gap-2.5">
              <Feature icon={FlaskConical} text="Docling Extraction" />
              <Feature icon={BarChart3} text="Chart → CSV" />
              <Feature icon={Brain} text="Llama 4 AI" />
              <Feature icon={Database} text="Scientific Database" />
            </div>

            {/* Stats */}
            <div className="mt-10 grid grid-cols-3 gap-6">
              {[
                { value: '100+', label: 'Papers processed' },
                { value: '12K+', label: 'Measurements' },
                { value: '6', label: 'Kinetic models' },
              ].map(({ value, label }) => (
                <div key={label} className="border-l-2 border-white/30 pl-4">
                  <div className="text-2xl font-bold text-white">{value}</div>
                  <div className="text-white/60 text-xs mt-0.5">{label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <p className="text-white/40 text-xs">
            © 2025 McGill University · Food Science Research Program
          </p>
        </div>
      </div>

      {/* ── Right panel: login form ─────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col items-center justify-center px-8 py-12 bg-slate-50 relative">
        {/* Top-right subtle decoration */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-[#C8102E]/5 to-transparent rounded-bl-full pointer-events-none" />

        <div className="w-full max-w-[380px]">
          {/* Mobile logo */}
          <div className="flex items-center gap-3 mb-8 lg:hidden">
            <div className="bg-[#C8102E] rounded-lg p-1.5">
              <img src="/mcgill.png" alt="McGill" className="h-7 w-auto brightness-0 invert" />
            </div>
            <div>
              <p className="font-bold text-slate-900 text-sm leading-tight">Meat & Cheese Database</p>
              <p className="text-slate-500 text-xs">McGill University</p>
            </div>
          </div>

          {/* Welcome */}
          <div className="mb-8">
            <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">Welcome back</h2>
            <p className="text-slate-500 text-sm mt-1.5">Sign in to your research account to continue</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5 uppercase tracking-wide">
                Email address
              </label>
              <div className="relative">
                <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input
                  type="email"
                  className="w-full bg-white border border-slate-200 rounded-xl px-3 py-3 pl-10 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#C8102E]/40 focus:border-[#C8102E] transition shadow-sm"
                  placeholder="you@university.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5 uppercase tracking-wide">
                Password
              </label>
              <div className="relative">
                <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input
                  type="password"
                  className="w-full bg-white border border-slate-200 rounded-xl px-3 py-3 pl-10 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#C8102E]/40 focus:border-[#C8102E] transition shadow-sm"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 bg-[#C8102E] hover:bg-[#a60d26] active:bg-[#8B0000] text-white font-semibold rounded-xl transition-all shadow-lg shadow-[#C8102E]/25 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Signing in…
                </span>
              ) : (
                <>Sign In <ArrowRight size={15} /></>
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-slate-200 text-center">
            <p className="text-sm text-slate-500">
              No account?{' '}
              <Link to="/register" className="text-[#C8102E] hover:text-[#a60d26] font-semibold transition-colors">
                Create one
              </Link>
            </p>
          </div>

          {/* Institutional badge */}
          <div className="mt-8 flex items-center justify-center gap-2 text-slate-400">
            <div className="h-px bg-slate-200 flex-1" />
            <div className="flex items-center gap-1.5 px-3">
              <img src="/mcgill.png" alt="" className="h-4 w-auto opacity-30" />
              <span className="text-[10px] font-medium">McGill University</span>
            </div>
            <div className="h-px bg-slate-200 flex-1" />
          </div>
        </div>
      </div>
    </div>
  )
}
