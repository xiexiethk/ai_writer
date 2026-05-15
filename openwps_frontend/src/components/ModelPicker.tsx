import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { ModelOption } from '../ai/providers'

interface ModelPickerProps {
  models: ModelOption[]
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  placeholder?: string
  loading?: boolean
}

function normalizeText(text: string) {
  return text.toLowerCase().replace(/[-_\s]+/g, '')
}

export default function ModelPicker({
  models,
  value,
  onChange,
  disabled = false,
  placeholder = '选择模型',
  loading = false,
}: ModelPickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const filteredModels = useMemo(() => {
    if (!query.trim()) return models
    const q = normalizeText(query)
    return models.filter(
      model =>
        normalizeText(model.id).includes(q) ||
        normalizeText(model.label || '').includes(q) ||
        normalizeText(model.id + (model.label || '')).includes(q),
    )
  }, [models, query])

  const selectedModel = useMemo(
    () => models.find(m => m.id === value) || null,
    [models, value],
  )

  // Measure and position dropdown when opening
  useEffect(() => {
    if (!isOpen) {
      const timer = window.setTimeout(() => setDropdownPos(null), 0)
      return () => window.clearTimeout(timer)
    }
    const measure = () => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const dropdownHeight = 280
      const gap = 6
      let top = rect.top - dropdownHeight - gap
      // If not enough space above, place below
      if (top < 8) {
        top = rect.bottom + gap
      }
      setDropdownPos({
        top,
        left: rect.left,
        width: rect.width,
      })
    }
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [isOpen])

  // Reset highlight when filtered list changes
  useEffect(() => {
    const timer = window.setTimeout(() => setHighlightedIndex(0), 0)
    return () => window.clearTimeout(timer)
  }, [filteredModels.length])

  // Focus input when opening
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 0)
    } else {
      const timer = window.setTimeout(() => setQuery(''), 0)
      return () => window.clearTimeout(timer)
    }
  }, [isOpen])

  // Close on click outside (check both trigger and dropdown)
  useEffect(() => {
    if (!isOpen) return
    const handleClick = (event: MouseEvent) => {
      const target = event.target as Node
      if (
        !containerRef.current?.contains(target) &&
        !dropdownRef.current?.contains(target)
      ) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [isOpen])

  // Scroll highlighted item into view
  useEffect(() => {
    if (!isOpen || !listRef.current) return
    const item = listRef.current.children[highlightedIndex] as HTMLElement | undefined
    if (item) {
      item.scrollIntoView({ block: 'nearest' })
    }
  }, [highlightedIndex, isOpen])

  const handleSelect = useCallback(
    (modelId: string) => {
      onChange(modelId)
      setIsOpen(false)
      setQuery('')
    },
    [onChange],
  )

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (!isOpen) {
        if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
          event.preventDefault()
          setIsOpen(true)
        }
        return
      }

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault()
          setHighlightedIndex(prev => (prev + 1) % filteredModels.length)
          break
        case 'ArrowUp':
          event.preventDefault()
          setHighlightedIndex(prev => (prev - 1 + filteredModels.length) % filteredModels.length)
          break
        case 'Enter':
          event.preventDefault()
          if (filteredModels[highlightedIndex]) {
            handleSelect(filteredModels[highlightedIndex].id)
          }
          break
        case 'Escape':
          event.preventDefault()
          setIsOpen(false)
          break
        case 'Tab':
          setIsOpen(false)
          break
      }
    },
    [isOpen, filteredModels, highlightedIndex, handleSelect],
  )

  const displayText = selectedModel
    ? `${selectedModel.id}${selectedModel.supportsVision ? ' · 多模态' : ''}`
    : value || placeholder

  const dropdownPanel = (
    <div
      ref={dropdownRef}
      className="overflow-hidden rounded-xl border border-stone-200 bg-[#fffaf2] shadow-[0_18px_36px_rgba(90,67,42,0.14)]"
      style={{
        position: 'fixed',
        top: dropdownPos?.top ?? 0,
        left: dropdownPos?.left ?? 0,
        width: dropdownPos?.width ?? 0,
        maxHeight: 280,
        zIndex: 9999,
      }}
    >
      <div className="sticky top-0 border-b border-stone-200 bg-[#fffaf2] px-3 py-2">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="搜索模型..."
          className="w-full bg-transparent text-[12px] text-stone-700 outline-none placeholder:text-stone-400"
        />
      </div>
      <div ref={listRef} className="overflow-y-auto" style={{ maxHeight: 220 }}>
        {filteredModels.length === 0 ? (
          <div className="px-3 py-3 text-[11px] text-stone-400 text-center">
            未找到匹配的模型
          </div>
        ) : (
          filteredModels.map((model, index) => {
            const isHighlighted = index === highlightedIndex
            return (
              <button
                key={model.id}
                type="button"
                onClick={() => handleSelect(model.id)}
                onMouseEnter={() => setHighlightedIndex(index)}
                className={`w-full text-left px-3 py-2 text-[11px] transition-colors ${
                  isHighlighted ? 'bg-amber-50 text-amber-700' : 'text-stone-700 hover:bg-stone-50'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {model.id}
                  </span>
                  {model.supportsVision && (
                    <span className="shrink-0 rounded-full border border-amber-100 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
                      多模态
                    </span>
                  )}
                </div>
                {model.label && model.label !== model.id && (
                  <div className={`mt-0.5 truncate text-[10px] ${isHighlighted ? 'text-amber-600' : 'text-stone-400'}`}>
                    {model.label}
                  </div>
                )}
              </button>
            )
          })
        )}
      </div>
      <div className="sticky bottom-0 flex items-center justify-between border-t border-stone-200 bg-[#f6efe5] px-3 py-1.5 text-[10px] text-stone-400">
        <span>{filteredModels.length} 个模型</span>
        <span className="text-stone-300">↑↓ 选择 · Enter 确认 · Esc 关闭</span>
      </div>
    </div>
  )

  return (
    <div ref={containerRef} className="relative flex min-w-0 flex-1">
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(prev => !prev)}
        disabled={disabled}
        onKeyDown={handleKeyDown}
        className={`flex min-w-0 flex-1 items-center gap-1.5 rounded-full border border-stone-200 bg-[#fffdf8] pl-3 pr-2 py-1.5 text-left text-[11px] transition-colors ${
          disabled
            ? 'cursor-not-allowed bg-stone-100 text-stone-400'
            : 'text-stone-700 hover:bg-stone-50'
        }`}
        title={selectedModel?.id || value || placeholder}
      >
        <span className="shrink-0 text-stone-500">模型</span>
        <span className="min-w-0 flex-1 truncate">
          {loading ? '模型加载中...' : displayText}
        </span>
        <span className="shrink-0 text-stone-400 text-[10px]">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && dropdownPos && createPortal(dropdownPanel, document.body)}
    </div>
  )
}
