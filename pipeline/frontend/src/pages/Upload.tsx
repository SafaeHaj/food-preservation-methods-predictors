import { useState, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload as UploadIcon, FileText, X, CheckCircle, ArrowLeft } from 'lucide-react'
import toast from 'react-hot-toast'
import { papersApi } from '../services/api'

export default function Upload() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)
  const navigate = useNavigate()

  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)

  const onDrop = useCallback((accepted: File[]) => {
    const pdfs = accepted.filter((f) => f.type === 'application/pdf' || f.name.endsWith('.pdf'))
    if (pdfs.length !== accepted.length) toast.error('Only PDF files are accepted')
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name))
      const newFiles = pdfs.filter((f) => !existing.has(f.name))
      return [...prev, ...newFiles].slice(0, 10)
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
    maxFiles: 10,
  })

  const remove = (name: string) => setFiles((prev) => prev.filter((f) => f.name !== name))

  const handleUpload = async () => {
    if (!files.length) return
    setUploading(true)
    try {
      await papersApi.upload(pid, files)
      toast.success(`${files.length} paper${files.length > 1 ? 's' : ''} uploaded successfully`)
      navigate(`/projects/${pid}`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const totalMB = files.reduce((s, f) => s + f.size, 0) / (1024 * 1024)

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link to={`/projects/${pid}`} className="text-slate-500 hover:text-slate-300">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-xl font-bold">Upload Papers</h1>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          isDragActive
            ? 'border-blue-500 bg-blue-950/20'
            : 'border-slate-700 hover:border-slate-600 bg-slate-900/40'
        }`}
      >
        <input {...getInputProps()} />
        <UploadIcon
          size={40}
          className={`mx-auto mb-4 ${isDragActive ? 'text-blue-400' : 'text-slate-600'}`}
        />
        {isDragActive ? (
          <p className="text-blue-400 font-medium">Drop your PDFs here</p>
        ) : (
          <>
            <p className="text-slate-300 font-medium mb-1">Drag & drop PDF files here</p>
            <p className="text-slate-500 text-sm">or click to browse — up to 10 files, 50 MB each</p>
          </>
        )}
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="card space-y-2">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium text-sm text-slate-300">
              {files.length} file{files.length > 1 ? 's' : ''} selected ({totalMB.toFixed(1)} MB)
            </h3>
            <button onClick={() => setFiles([])} className="text-xs text-slate-500 hover:text-slate-300">
              Clear all
            </button>
          </div>
          {files.map((file) => (
            <div key={file.name} className="flex items-center gap-3 bg-slate-800 rounded-lg px-3 py-2">
              <FileText size={14} className="text-blue-400 shrink-0" />
              <span className="text-sm text-slate-300 flex-1 truncate">{file.name}</span>
              <span className="text-xs text-slate-500 shrink-0">
                {(file.size / (1024 * 1024)).toFixed(1)} MB
              </span>
              <button onClick={() => remove(file.name)} className="text-slate-600 hover:text-red-400">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-3 justify-end">
        <Link to={`/projects/${pid}`} className="btn-secondary">Cancel</Link>
        <button
          onClick={handleUpload}
          disabled={!files.length || uploading}
          className="btn-primary"
        >
          {uploading ? 'Uploading...' : `Upload ${files.length || ''} PDF${files.length !== 1 ? 's' : ''}`}
        </button>
      </div>
    </div>
  )
}
