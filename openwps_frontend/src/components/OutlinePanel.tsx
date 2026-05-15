import { useMemo } from 'react'
import { EditorState, TextSelection } from 'prosemirror-state'
import { EditorView } from 'prosemirror-view'
import { X, AlignLeft } from 'lucide-react'

export interface OutlineItem {
  id: string
  level: number
  text: string
  pos: number
}

interface Props {
  editorState: EditorState | null
  view: EditorView | null
  onClose: () => void
}

export function OutlinePanel({ editorState, view, onClose }: Props) {
  const outline = useMemo(() => {
    if (!editorState) return []
    const items: OutlineItem[] = []
    
    editorState.doc.descendants((node, pos) => {
      if (node.type.name === 'paragraph') {
        const headingLevel = Number(node.attrs.headingLevel || 0)
        if (headingLevel >= 1 && headingLevel <= 9) {
          items.push({
            id: `heading-${pos}`,
            level: headingLevel,
            text: node.textContent || '（无标题）',
            pos: pos
          })
        }
      }
      return false // Don't descend into block nodes like paragraph
    })
    
    return items
  }, [editorState])

  const handleGoTo = (pos: number) => {
    if (!view || !editorState) return
    const tr = editorState.tr.setSelection(TextSelection.create(editorState.doc, pos + 1))
    view.dispatch(tr.scrollIntoView())
    view.focus()
  }

  return (
    <div className="flex h-full w-[280px] flex-col border-r border-stone-200 bg-[#f6efe5] flex-shrink-0">
      <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-stone-700">
          <AlignLeft size={16} />
          文档大纲
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-6 w-6 items-center justify-center rounded text-stone-400 hover:bg-white/80 hover:text-stone-700 transition-colors"
          title="关闭大纲"
        >
          <X size={16} />
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-2">
        {outline.length === 0 ? (
          <div className="mt-8 text-center text-sm text-stone-400">
            暂无标题，请在文档中设置标题段落样式
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {outline.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => handleGoTo(item.pos)}
                className="flex items-center rounded-xl px-2.5 py-2 text-left text-sm text-stone-700 hover:bg-[#fffaf2] hover:text-amber-800 hover:shadow-sm transition-all focus:outline-none focus:ring-1 focus:ring-amber-300"
                style={{
                  paddingLeft: `${Math.max(0, (item.level - 1) * 16 + 8)}px`,
                  fontWeight: item.level === 1 ? 600 : item.level === 2 ? 500 : 400,
                  fontSize: item.level === 1 ? '14px' : '13px'
                }}
              >
                <span className="truncate">{item.text}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
