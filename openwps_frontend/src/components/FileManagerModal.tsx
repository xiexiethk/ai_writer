import { useEffect, useState } from 'react'

export type DocumentSource = 'internal' | 'wps_directory'

export interface DocumentFileSummary {
  name: string
  size: number
  updatedAt: string
  source: DocumentSource
  directory: string
}

export interface DocumentSettings {
  activeSource: DocumentSource
  wpsDirectory: string
  available: boolean
  errorMessage?: string | null
  activeDirectory: string
  internalDirectory: string
}

interface Props {
  mode: 'open' | 'save'
  files: DocumentFileSummary[]
  loading: boolean
  error: string | null
  settings: DocumentSettings
  settingsSaving: boolean
  initialName?: string
  onClose: () => void
  onOpen: (name: string) => void | Promise<void>
  onSave: (name: string) => void | Promise<void>
  onDelete: (name: string) => void | Promise<void>
  onRefresh: () => void | Promise<void>
  onChangeSource: (source: DocumentSource) => void | Promise<void>
  onUpdateWpsDirectory: (path: string) => void | Promise<void>
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function sourceLabel(source: DocumentSource) {
  return source === 'wps_directory' ? 'WPS 目录' : '服务器文档'
}

export default function FileManagerModal({
  mode,
  files,
  loading,
  error,
  settings,
  settingsSaving,
  initialName = 'document.docx',
  onClose,
  onOpen,
  onSave,
  onDelete,
  onRefresh,
  onChangeSource,
  onUpdateWpsDirectory,
}: Props) {
  const [name, setName] = useState(initialName)
  const [wpsDirectoryDraft, setWpsDirectoryDraft] = useState(settings.wpsDirectory)
  const isSave = mode === 'save'
  const isWpsSource = settings.activeSource === 'wps_directory'

  useEffect(() => {
    const timer = window.setTimeout(() => setName(initialName), 0)
    return () => window.clearTimeout(timer)
  }, [initialName, mode])

  useEffect(() => {
    const timer = window.setTimeout(() => setWpsDirectoryDraft(settings.wpsDirectory), 0)
    return () => window.clearTimeout(timer)
  }, [settings.wpsDirectory])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const submit = async () => {
    const trimmed = name.trim()
    if (!trimmed || !settings.available) return
    await onSave(trimmed)
  }

  const currentDirectory = settings.activeDirectory || (isWpsSource ? settings.wpsDirectory : settings.internalDirectory)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#2c2116]/35">
      <div className="mx-4 flex w-[620px] max-w-[96vw] flex-col rounded-[20px] border border-stone-200 bg-[#fffaf3] shadow-[0_28px_60px_rgba(69,50,30,0.2)]" style={{ maxHeight: '88vh' }}>
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3.5 flex-shrink-0">
          <div>
            <h2 className="font-semibold text-stone-800 text-base">{isSave ? '保存文档' : '打开文档'}</h2>
            <p className="text-xs text-stone-400 mt-0.5">当前来源：{sourceLabel(settings.activeSource)}</p>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-stone-100 text-stone-400 hover:text-stone-700 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="space-y-3 border-b border-stone-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <button
              onClick={() => void onChangeSource('internal')}
              className={`px-3 py-1.5 text-sm rounded-lg border ${
                settings.activeSource === 'internal'
                  ? 'border-amber-300 bg-amber-50 text-amber-700'
                  : 'border-stone-300 bg-[#fffdf8] text-stone-700 hover:bg-stone-50'
              }`}
              disabled={settingsSaving}
            >
              服务器文档
            </button>
            <button
              onClick={() => void onChangeSource('wps_directory')}
              className={`px-3 py-1.5 text-sm rounded-lg border ${
                settings.activeSource === 'wps_directory'
                  ? 'border-amber-300 bg-amber-50 text-amber-700'
                  : 'border-stone-300 bg-[#fffdf8] text-stone-700 hover:bg-stone-50'
              }`}
              disabled={settingsSaving}
            >
              WPS 目录
            </button>
            <button
              onClick={() => void onRefresh()}
              className="ml-auto rounded-lg border border-stone-300 bg-[#fffdf8] px-3 py-1.5 text-xs text-stone-700 hover:bg-stone-50"
              disabled={loading}
            >
              刷新
            </button>
          </div>

          {isWpsSource && (
            <div className="space-y-2 rounded-2xl border border-stone-200 bg-[#f7efe4] px-3 py-3">
              <label className="block text-xs font-medium text-stone-600">WPS 本地 DOCX 目录</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={wpsDirectoryDraft}
                  onChange={event => setWpsDirectoryDraft(event.target.value)}
                  placeholder="/Users/you/Documents/WPS"
                  className="flex-1 rounded-xl border border-stone-300 bg-[#fffdf8] px-3 py-2 text-sm text-stone-800 focus:outline-none focus:ring-2 focus:ring-amber-300"
                />
                <button
                  onClick={() => void onUpdateWpsDirectory(wpsDirectoryDraft)}
                  className="rounded-xl bg-amber-700 px-3 py-2 text-sm text-white hover:bg-amber-800 disabled:opacity-50"
                  disabled={settingsSaving}
                >
                  保存目录
                </button>
              </div>
              <p className="text-xs text-stone-500">仅读取该目录顶层 `.docx` 文件，不扫描子目录。</p>
            </div>
          )}

          <div className="break-all text-xs text-stone-500">
            目录：{currentDirectory || '未配置'}
          </div>

          {!settings.available && (
            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg">
              {settings.errorMessage || '当前文档来源不可用'}
            </div>
          )}

          {isSave && (
            <div className="space-y-2">
              <label className="block text-xs font-medium text-stone-500">文件名</label>
              <input
                type="text"
                value={name}
                onChange={event => setName(event.target.value)}
                placeholder="document.docx"
                className="w-full rounded-xl border border-stone-300 bg-[#fffdf8] px-3 py-2 text-sm text-stone-800 focus:outline-none focus:ring-2 focus:ring-amber-300"
              />
              <p className="text-xs text-stone-400">
                {isWpsSource ? '将直接保存到当前 WPS 目录。' : '会保存到后端 `server/data/documents/`。'}
              </p>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {error && (
            <div className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</div>
          )}

          {loading ? (
            <div className="text-sm text-stone-500">正在读取文件列表…</div>
          ) : files.length === 0 ? (
            <div className="text-sm text-stone-500">
              {settings.available ? '当前目录还没有可用的 docx 文件。' : '当前目录不可用，请先修正配置或切回服务器文档。'}
            </div>
          ) : (
            <div className="space-y-2">
              {files.map(file => (
                <div key={file.name} className="flex items-center gap-3 rounded-2xl border border-stone-200 bg-[#fffdf8] px-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-stone-800">{file.name}</div>
                    <div className="text-xs text-stone-400">{formatBytes(file.size)} · {formatTime(file.updatedAt)}</div>
                  </div>
                  {isSave ? (
                    <button
                      onClick={() => setName(file.name)}
                      className="rounded-lg border border-stone-300 bg-[#fffaf2] px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-50"
                    >
                      使用此名
                    </button>
                  ) : (
                    <button
                      onClick={() => void onOpen(file.name)}
                      className="rounded-lg bg-amber-700 px-2.5 py-1 text-xs text-white hover:bg-amber-800 disabled:opacity-50"
                      disabled={!settings.available}
                    >
                      打开
                    </button>
                  )}
                  <button
                    onClick={() => void onDelete(file.name)}
                    className="px-2.5 py-1 text-xs rounded-lg border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
                    disabled={!settings.available}
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-stone-200 px-5 py-3.5 flex-shrink-0">
          <button
            onClick={onClose}
            className="rounded-lg border border-stone-300 bg-[#fffdf8] px-4 py-2 text-sm text-stone-700 hover:bg-stone-50"
          >
            取消
          </button>
          {isSave && (
            <button
              onClick={() => void submit()}
              className="rounded-lg bg-amber-700 px-4 py-2 text-sm text-white hover:bg-amber-800 disabled:opacity-50"
              disabled={!name.trim() || !settings.available}
            >
              保存
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
