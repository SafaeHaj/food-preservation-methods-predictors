import { useCallback, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload as UploadIcon, FileText, X, ArrowLeft, CloudUpload, Microscope, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { useUploadPapers } from '../api/papers'
import { useStartPaperExtraction } from '../api/workspace'
import { errorMessage } from '../api/errors'

/** Mirrors EXTRACTION_MAX_PAPERS_PER_UPLOAD on the extraction service. */
const MAX_FILES = 10

export default function Upload() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)
  const navigate = useNavigate()

  const [files, setFiles] = useState<File[]>([])
  const uploadPapers = useUploadPapers(pid)
  const startExtraction = useStartPaperExtraction(pid)

  // The "batch" mode is gone with the legacy flat-extraction path it fed. Papers are
  // uploaded here and analysed in the workspace; several at once is still supported, it
  // just no longer means a different pipeline.
  const onDrop = useCallback((accepted: File[]) => {
    const pdfs = accepted.filter((f) => f.type === 'application/pdf' || f.name.endsWith('.pdf'))
    if (pdfs.length !== accepted.length) toast.error('Only PDF files are accepted')
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name))
      return [...prev, ...pdfs.filter((f) => !existing.has(f.name))].slice(0, MAX_FILES)
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
    maxFiles: MAX_FILES,
  })

  const remove = (name: string) => setFiles((prev) => prev.filter((f) => f.name !== name))

  const handleUpload = async () => {
    if (!files.length) return

    let created
    try {
      created = await uploadPapers.mutateAsync(files)
    } catch (error) {
      toast.error(errorMessage(error, 'Upload failed'))
      return
    }

    // Uploading is the first half of "analyse this PDF", so the parse is queued here rather
    // than waiting for a second click on a page the user has not seen yet. Queued for every
    // paper, in parallel: they run on the extraction workers, not in this request.
    const starts = await Promise.allSettled(
      created.map((paper) => startExtraction.mutateAsync(paper.id)),
    )
    const failed = starts.filter((result) => result.status === 'rejected').length

    // A paper that failed to start is still uploaded, and still has its own "Analyse
    // document" button — so this is a warning, not a dead end.
    if (failed) {
      toast.error(
        failed === created.length
          ? errorMessage(
              (starts[0] as PromiseRejectedResult).reason,
              'Uploaded, but the analysis could not be started',
            )
          : `${failed} of ${created.length} papers could not be queued for analysis`,
      )
    }

    if (created.length === 1) {
      navigate(`/projects/${pid}/papers/${created[0].id}/workspace`)
    } else {
      if (!failed) toast.success(`${created.length} papers uploaded and queued for analysis`)
      // The jobs page, not the project: it is where the runs just queued are visible, and
      // it now updates itself as they progress.
      navigate(`/projects/${pid}/jobs`)
    }
  }

  const totalMB = files.reduce((s, f) => s + f.size, 0) / (1024 * 1024)
  const busy = uploadPapers.isPending || startExtraction.isPending

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`/projects/${pid}`}
          className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="page-title">Upload Papers</h1>
          <p className="muted">Upload PDF scientific papers for AI extraction</p>
        </div>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={clsx(
          'border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-200',
          isDragActive
            ? 'border-blue-400 bg-blue-50 scale-[1.01]'
            : 'border-slate-300 hover:border-blue-300 hover:bg-slate-50 bg-white',
        )}
      >
        <input {...getInputProps()} />
        <div className={clsx(
          'w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4 transition-colors',
          isDragActive ? 'bg-blue-100' : 'bg-slate-100',
        )}>
          <CloudUpload size={26} className={isDragActive ? 'text-blue-500' : 'text-slate-400'} />
        </div>
        {isDragActive ? (
          <p className="text-blue-600 font-semibold text-base">Drop your PDF here</p>
        ) : (
          <>
            <p className="text-slate-800 font-semibold text-base mb-1">
              Drag &amp; drop PDF files here
            </p>
            <p className="text-slate-400 text-sm">
              or <span className="text-blue-600 hover:underline">click to browse</span>
            </p>
            <p className="text-slate-400 text-xs mt-3">
              Up to {MAX_FILES} files · 50 MB each
            </p>
          </>
        )}
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-slate-700">
              {files.length} file{files.length > 1 ? 's' : ''} selected
              <span className="text-slate-400 font-normal ml-1.5">({totalMB.toFixed(1)} MB total)</span>
            </p>
            <button
              onClick={() => setFiles([])}
              className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
            >
              Clear
            </button>
          </div>
          <div className="space-y-2">
            {files.map((file) => (
              <div
                key={file.name}
                className="flex items-center gap-3 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2.5"
              >
                <div className="w-7 h-7 bg-blue-50 rounded-lg flex items-center justify-center shrink-0">
                  <FileText size={13} className="text-blue-500" />
                </div>
                <span className="text-sm text-slate-700 flex-1 truncate font-medium">{file.name}</span>
                <span className="text-xs text-slate-400 shrink-0">
                  {(file.size / (1024 * 1024)).toFixed(1)} MB
                </span>
                <button
                  onClick={() => remove(file.name)}
                  className="p-1 text-slate-300 hover:text-red-400 hover:bg-red-50 rounded transition-colors"
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3 justify-end">
        <Link to={`/projects/${pid}`} className="btn-secondary">Cancel</Link>
        <button
          onClick={handleUpload}
          disabled={!files.length || busy}
          className="btn-primary min-w-40 justify-center"
        >
          {busy ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {uploadPapers.isPending ? 'Uploading…' : 'Starting analysis…'}
            </>
          ) : files.length === 1 ? (
            <><Microscope size={14} /> Upload &amp; analyse</>
          ) : (
            <><UploadIcon size={14} /> Upload &amp; analyse {files.length || ''} PDF{files.length !== 1 ? 's' : ''}</>
          )}
        </button>
      </div>
    </div>
  )
}
