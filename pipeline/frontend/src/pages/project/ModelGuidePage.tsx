import { useParams, useNavigate, Link } from 'react-router-dom'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import clsx from 'clsx'
import { MODEL_DOCS, type ModelDoc } from '../../data/modelDocs'
import { ArrowLeft } from 'lucide-react'

// ─── KaTeX helpers ─────────────────────────────────────────────────────────────

function DisplayMath({ src }: { src: string }) {
  let html = ''
  try {
    html = katex.renderToString(src, { displayMode: true, throwOnError: false, strict: false })
  } catch {
    html = `<span style="color:#ef4444;font-family:monospace;font-size:12px">${src}</span>`
  }
  return (
    <div
      className="katex-display-wrap overflow-x-auto py-4 px-5 bg-slate-50 border border-slate-200 rounded my-0"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function InlineMath({ text }: { text: string }) {
  // The latexNote strings use \( ... \) for inline math
  const parts = text.split(/(\\\(.+?\\\))/g)
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\\\((.+)\\\)$/)
        if (m) {
          let html = ''
          try {
            html = katex.renderToString(m[1], { displayMode: false, throwOnError: false })
          } catch {
            html = m[1]
          }
          return <span key={i} dangerouslySetInnerHTML={{ __html: html }} />
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3 mt-8 first:mt-0 border-b border-slate-100 pb-1.5">
      {children}
    </h2>
  )
}

function ParamsTable({ params }: { params: ModelDoc['params'] }) {
  return (
    <div className="overflow-x-auto border border-slate-200 rounded">
      <table className="w-full text-[13px] border-collapse">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="text-left px-3 py-2 font-semibold text-slate-500 w-16 border-r border-slate-200">Symbol</th>
            <th className="text-left px-3 py-2 font-semibold text-slate-500 w-36 border-r border-slate-200">Name</th>
            <th className="text-left px-3 py-2 font-semibold text-slate-500 w-28 border-r border-slate-200">Unit</th>
            <th className="text-left px-3 py-2 font-semibold text-slate-500">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p, i) => (
            <tr key={i} className={clsx('border-b border-slate-100 last:border-0', i % 2 === 1 && 'bg-slate-50/50')}>
              <td className="px-3 py-2 font-mono text-[12px] text-violet-700 border-r border-slate-100">{p.symbol}</td>
              <td className="px-3 py-2 font-medium text-slate-800 border-r border-slate-100">{p.name}</td>
              <td className="px-3 py-2 text-slate-500 font-mono text-[11px] border-r border-slate-100">{p.unit}</td>
              <td className="px-3 py-2 text-slate-600">{p.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BulletItem({ children, color }: { children: React.ReactNode; color: 'teal' | 'violet' | 'amber' | 'green' }) {
  const dotColor = {
    teal: 'bg-teal-500',
    violet: 'bg-violet-500',
    amber: 'bg-amber-400',
    green: 'bg-green-500',
  }[color]
  return (
    <li className="flex items-start gap-2.5 text-[13px] text-slate-700 leading-relaxed">
      <span className={clsx('mt-1.5 w-1.5 h-1.5 rounded-full shrink-0', dotColor)} />
      {children}
    </li>
  )
}

// ─── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({ current, projectId }: { current: ModelDoc; projectId: string }) {
  const navigate = useNavigate()
  const families: { label: string; family: ModelDoc['family'] }[] = [
    { label: 'Kinetic Models', family: 'kinetic' },
    { label: 'Survival Models', family: 'survival' },
  ]

  return (
    <aside className="w-56 shrink-0 flex flex-col bg-white border-r border-slate-200 overflow-y-auto">
      <div className="px-4 py-4 border-b border-slate-100">
        <Link
          to={`/projects/${projectId}/model-lab`}
          className="inline-flex items-center gap-1.5 text-[12px] text-slate-500 hover:text-slate-800 transition-colors"
        >
          <ArrowLeft size={12} /> Back to Model Lab
        </Link>
        <p className="mt-3 text-[11px] font-bold uppercase tracking-[0.1em] text-slate-400">Model Reference</p>
      </div>

      {families.map(({ label, family }) => {
        const models = MODEL_DOCS.filter((m) => m.family === family)
        return (
          <div key={family} className="px-3 py-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 px-1 mb-1.5">{label}</p>
            <ul className="space-y-0.5">
              {models.map((m) => (
                <li key={m.id}>
                  <button
                    onClick={() => navigate(`/projects/${projectId}/model-lab/guide/${m.id}`)}
                    className={clsx(
                      'w-full text-left px-2 py-1.5 rounded text-[13px] transition-colors',
                      m.id === current.id
                        ? family === 'kinetic'
                          ? 'bg-teal-50 text-teal-800 font-semibold'
                          : 'bg-violet-50 text-violet-800 font-semibold'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    )}
                  >
                    {m.shortName}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </aside>
  )
}

// ─── Main content ──────────────────────────────────────────────────────────────

function ModelContent({ model }: { model: ModelDoc }) {
  const accentText = model.family === 'kinetic' ? 'text-teal-700' : 'text-violet-700'
  const accentBg   = model.family === 'kinetic' ? 'bg-teal-600' : 'bg-violet-600'
  const familyLabel = model.family === 'kinetic' ? 'Kinetic Growth / Inactivation' : 'Survival Analysis'
  const dotColor: 'teal' | 'violet' = model.family === 'kinetic' ? 'teal' : 'violet'

  return (
    <article className="max-w-3xl mx-auto px-10 py-8">
      {/* Header */}
      <header className="mb-8 pb-6 border-b border-slate-200">
        <span className={clsx('inline-block text-[10px] font-bold uppercase tracking-[0.14em] text-white px-2.5 py-1 rounded-sm mb-3', accentBg)}>
          {familyLabel}
        </span>
        <h1 className="text-3xl font-bold text-slate-900 tracking-tight">{model.name}</h1>
        <p className="mt-2 text-[15px] text-slate-500 leading-snug">{model.tagline}</p>
      </header>

      {/* Overview */}
      <SectionHeader>Overview</SectionHeader>
      <p className="text-[13px] text-slate-700 leading-[1.75]">{model.what}</p>

      {/* Best For */}
      <SectionHeader>Best Suited For</SectionHeader>
      <ul className="space-y-1.5">
        {model.bestFor.map((item, i) => (
          <BulletItem key={i} color={dotColor}>{item}</BulletItem>
        ))}
      </ul>

      {/* Mathematical Formulation */}
      <SectionHeader>Mathematical Formulation</SectionHeader>
      <div className="space-y-2">
        {model.latex.map((eq, i) => (
          <DisplayMath key={i} src={eq} />
        ))}
      </div>
      {model.latexNote && (
        <p className="mt-3 text-[12px] text-slate-500 leading-relaxed italic">
          <InlineMath text={model.latexNote} />
        </p>
      )}

      {/* Parameters */}
      <SectionHeader>Model Parameters</SectionHeader>
      <ParamsTable params={model.params} />

      {/* Data Requirements */}
      <SectionHeader>Data Requirements</SectionHeader>
      <ul className="space-y-1.5">
        {model.dataRequirements.map((item, i) => (
          <BulletItem key={i} color={dotColor}>{item}</BulletItem>
        ))}
      </ul>

      {/* Outputs */}
      <SectionHeader>Model Outputs</SectionHeader>
      <ul className="space-y-1.5">
        {model.outputs.map((item, i) => (
          <BulletItem key={i} color={dotColor}>{item}</BulletItem>
        ))}
      </ul>

      {/* Assumptions & Limitations */}
      <div className="grid grid-cols-2 gap-8 mt-8">
        <div>
          <SectionHeader>Assumptions</SectionHeader>
          <ul className="space-y-1.5">
            {model.assumptions.map((a, i) => (
              <BulletItem key={i} color="green">{a}</BulletItem>
            ))}
          </ul>
        </div>
        <div>
          <SectionHeader>Limitations</SectionHeader>
          <ul className="space-y-1.5">
            {model.limitations.map((l, i) => (
              <BulletItem key={i} color="amber">{l}</BulletItem>
            ))}
          </ul>
        </div>
      </div>

      {/* References */}
      {model.references && model.references.length > 0 && (
        <>
          <SectionHeader>References</SectionHeader>
          <ol className="space-y-2 list-decimal list-outside pl-5">
            {model.references.map((ref, i) => (
              <li key={i} className="text-[12px] text-slate-600 leading-relaxed">
                {ref.authors} ({ref.year}).{' '}
                <span className="italic">{ref.title}.</span>{' '}
                <span className={clsx('font-medium', accentText)}>{ref.journal}.</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </article>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function ModelGuidePage() {
  const { projectId = '0', modelId = '' } = useParams<{ projectId: string; modelId: string }>()
  const navigate = useNavigate()

  const model = MODEL_DOCS.find((m) => m.id === modelId)

  if (!model) {
    return (
      <div className="flex items-center justify-center h-full flex-col gap-3">
        <p className="text-slate-500 text-sm">Model "{modelId}" not found.</p>
        <button
          onClick={() => navigate(`/projects/${projectId}/model-lab`)}
          className="text-sm text-violet-600 hover:underline"
        >
          ← Back to Model Lab
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-white">
      <Sidebar current={model} projectId={projectId} />
      <main className="flex-1 overflow-y-auto bg-white">
        <ModelContent model={model} />
      </main>
    </div>
  )
}
