// ============================================================
// CẤU HÌNH 5 FIELD CỐ ĐỊNH
// ============================================================
import React, { useState, useEffect, useRef, useCallback } from 'react'

const FIELD_DEFS = [
  { key: 'student_name', label: 'Tên sinh viên', sample: 'Nguyễn Văn A' },
  { key: 'ma_cbsv', label: 'Mã số sinh viên', sample: 'SV001234' },
  { key: 'don_vi', label: 'Khoa / Đơn vị', sample: 'Công tác xã hội' },
  { key: 'issue_date', label: 'Ngày cấp', sample: 'TP.HCM, ngày 3 tháng 7 năm 2026' },
  { key: 'certificate_code', label: 'Mã chứng nhận', sample: 'CC-2026-0001' },
]

const DEFAULT_FIELD_CONFIG = { size: 48, color: '#0646c8', bold: true, align: 'center' }

// pixel thật (theo ảnh gốc) <-> phần trăm (để đặt trong CSS left/top)
function realToPercent(x, y, naturalWidth, naturalHeight) {
  return {
    leftPercent: (x / naturalWidth) * 100,
    topPercent: (y / naturalHeight) * 100,
  }
}

export default function CertificateLayoutDesigner({ eventId, templateImageUrl }) {
  const [savedLayout, setSavedLayout] = useState({})
  const [draftLayout, setDraftLayout] = useState({})
  const [selectedField, setSelectedField] = useState(null)
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 })
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  const imgRef = useRef(null)
  const containerRef = useRef(null)
  const dragOffsetRef = useRef({ dxPercent: 0, dyPercent: 0 })
  const draggingFieldRef = useRef(null)

  const isDirty = JSON.stringify(savedLayout) !== JSON.stringify(draftLayout)

  useEffect(() => {
    let cancelled = false
    async function loadLayout() {
      setLoading(true)
      try {
        // load saved layout from server
        const res = await fetch(`/api/admin/events/${eventId}/certificate-layout`)
        const data = await res.json()
        if (data && data.success && !cancelled) {
          setSavedLayout(data.data || {})
          setDraftLayout(data.data || {})
        }
      } catch (err) {
        // ignore
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    if (eventId) loadLayout()
    return () => { cancelled = true }
  }, [eventId])

  useEffect(() => {
    function handleBeforeUnload(e) {
      if (isDirty) e.returnValue = 'Bạn có thay đổi chưa lưu.'
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [isDirty])

  function handleImageLoad() {
    const img = imgRef.current
    if (!img) return
    setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight })
    setDraftLayout(prev => ({ ...(prev || {}), _meta: { width: img.naturalWidth, height: img.naturalHeight } }))
  }

  function handleAddField(fieldKey) {
    if (!naturalSize.width || !naturalSize.height) return
    const centerX = Math.round(naturalSize.width / 2)
    const centerY = Math.round(naturalSize.height / 2)
    setDraftLayout(prev => ({ ...prev, [fieldKey]: { ...DEFAULT_FIELD_CONFIG, x: centerX, y: centerY } }))
    setSelectedField(fieldKey)
  }

  function handleRemoveField(fieldKey) {
    setDraftLayout(prev => {
      const next = { ...prev }
      delete next[fieldKey]
      return next
    })
    if (selectedField === fieldKey) setSelectedField(null)
  }

  function handleSelectField(fieldKey, e) {
    e.stopPropagation()
    setSelectedField(fieldKey)
  }

  function handleCanvasBackgroundClick() {
    setSelectedField(null)
  }

  // drag handlers
  const handleMouseDownOnField = useCallback((fieldKey, e) => {
    e.preventDefault(); e.stopPropagation()
    setSelectedField(fieldKey)
    draggingFieldRef.current = fieldKey
    const container = containerRef.current
    const field = draftLayout[fieldKey]
    if (!container || !field) return
    const rect = container.getBoundingClientRect()
    const { leftPercent, topPercent } = realToPercent(field.x, field.y, naturalSize.width, naturalSize.height)
    const mouseXPercent = ((e.clientX - rect.left) / rect.width) * 100
    const mouseYPercent = ((e.clientY - rect.top) / rect.height) * 100
    dragOffsetRef.current = { dxPercent: mouseXPercent - leftPercent, dyPercent: mouseYPercent - topPercent }
  }, [draftLayout, naturalSize])

  useEffect(() => {
    function handleMouseMove(e) {
      const fieldKey = draggingFieldRef.current
      if (!fieldKey) return
      const container = containerRef.current
      if (!container || !naturalSize.width || !naturalSize.height) return
      const rect = container.getBoundingClientRect()
      const mouseXPercent = ((e.clientX - rect.left) / rect.width) * 100
      const mouseYPercent = ((e.clientY - rect.top) / rect.height) * 100
      let leftPercent = mouseXPercent - dragOffsetRef.current.dxPercent
      let topPercent = mouseYPercent - dragOffsetRef.current.dyPercent
      leftPercent = Math.max(0, Math.min(100, leftPercent))
      topPercent = Math.max(0, Math.min(100, topPercent))
      const realX = Math.round((leftPercent / 100) * naturalSize.width)
      const realY = Math.round((topPercent / 100) * naturalSize.height)
      setDraftLayout(prev => ({ ...prev, [fieldKey]: { ...prev[fieldKey], x: realX, y: realY } }))
    }
    function handleMouseUp() { draggingFieldRef.current = null }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => { document.removeEventListener('mousemove', handleMouseMove); document.removeEventListener('mouseup', handleMouseUp) }
  }, [naturalSize])

  function updateFieldConfig(fieldKey, patch) {
    setDraftLayout(prev => ({ ...prev, [fieldKey]: { ...prev[fieldKey], ...patch } }))
  }

  async function handleSave() {
    const missing = FIELD_DEFS.filter(f => !draftLayout[f.key]?.x).map(f => f.label)
    if (missing.length > 0) {
      if (!confirm('Có trường chưa được đặt vị trí. Tiếp tục lưu?')) return
    }
    setSaving(true)
    try {
      const res = await fetch(`/api/admin/events/${eventId}/certificate-layout`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layout: draftLayout, base_width: naturalSize.width, base_height: naturalSize.height }) })
      const data = await res.json()
      if (data && data.success) {
        setSavedLayout(draftLayout)
        setSaving(false)
        alert('Đã lưu')
        return
      }
      alert('Lưu thất bại')
    } catch (err) {
      alert('Lỗi khi lưu')
    } finally { setSaving(false) }
  }

  function handleDiscard() { setDraftLayout(savedLayout); setSelectedField(null) }

  if (loading) return <p className="cld-loading">Đang tải bố cục...</p>

  const activeConfig = selectedField ? draftLayout[selectedField] : null
  const activeLabel = selectedField ? FIELD_DEFS.find(f => f.key === selectedField)?.label : null

  return (
    <div className="cld-wrapper">
      <div className="cld-canvas-area" ref={containerRef} onClick={handleCanvasBackgroundClick}>
        <img ref={imgRef} src={templateImageUrl} alt="Ảnh mẫu chứng chỉ" className="cld-template-image" onLoad={handleImageLoad} draggable={false} />

        {FIELD_DEFS.map(def => {
          const config = draftLayout[def.key]
          if (!config || config.x == null || config.y == null) return null
          if (!naturalSize.width) return null
          const { leftPercent, topPercent } = realToPercent(config.x, config.y, naturalSize.width, naturalSize.height)
          const transformMap = { left: 'translateY(-50%)', center: 'translate(-50%, -50%)', right: 'translate(-100%, -50%)' }
          return (
            <div key={def.key}
              className={'cld-field-overlay' + (selectedField === def.key ? ' is-selected' : '')}
              style={{
                left: `${leftPercent}%`,
                top: `${topPercent}%`,
                transform: transformMap[config.align] || transformMap.left,
                fontSize: `${config.size * (containerRef.current?.clientWidth / naturalSize.width || 1)}px`,
                color: config.color,
                fontWeight: config.bold ? 700 : 400,
                textAlign: config.align,
              }}
              onMouseDown={(e) => handleMouseDownOnField(def.key, e)}
              onClick={(e) => handleSelectField(def.key, e)}
            >
              {def.sample}
            </div>
          )
        })}
      </div>

      <div className="cld-sidebar">
        <h3 className="cld-sidebar-title">Thông tin trên chứng chỉ</h3>
        <ul className="cld-field-list">
          {FIELD_DEFS.map(def => {
            const placed = Boolean(draftLayout[def.key]?.x != null)
            return (
              <li key={def.key} className={'cld-field-list-item' + (selectedField === def.key ? ' is-selected' : '')} onClick={() => placed && setSelectedField(def.key)}>
                <span>{def.label}</span>
                {placed ? <span className="cld-badge cld-badge--placed">Đã thêm</span> : <button type="button" className="cld-btn cld-btn--small" onClick={(e) => { e.stopPropagation(); handleAddField(def.key) }} >+ Thêm vào ảnh</button>}
              </li>
            )
          })}
        </ul>

        {activeConfig && (
          <div className="cld-config-panel">
            <div className="cld-config-panel-header">
              <span>{activeLabel}</span>
              <button type="button" className="cld-link-btn cld-link-btn--danger" onClick={() => handleRemoveField(selectedField)}>Xóa khỏi ảnh</button>
            </div>
            <label className="cld-field-row">
              <span>Cỡ chữ</span>
              <input type="number" min={10} max={200} value={activeConfig.size} onChange={(e) => updateFieldConfig(selectedField, { size: Number(e.target.value) })} />
            </label>
            <label className="cld-field-row">
              <span>Màu chữ</span>
              <input type="color" value={activeConfig.color} onChange={(e) => updateFieldConfig(selectedField, { color: e.target.value })} />
            </label>
            <label className="cld-field-row cld-field-row--checkbox">
              <span>In đậm</span>
              <input type="checkbox" checked={activeConfig.bold} onChange={(e) => updateFieldConfig(selectedField, { bold: e.target.checked })} />
            </label>
            <div className="cld-field-row">
              <span>Căn lề</span>
              <div className="cld-align-group">
                {['left', 'center', 'right'].map(align => <button key={align} type="button" className={'cld-align-btn' + (activeConfig.align === align ? ' is-active' : '')} onClick={() => updateFieldConfig(selectedField, { align })}>{align === 'left' ? 'Trái' : align === 'center' ? 'Giữa' : 'Phải'}</button>)}
              </div>
            </div>
          </div>
        )}

        <div className="cld-actions">
          <button type="button" className="cld-btn cld-btn--secondary" onClick={handleDiscard} disabled={!isDirty || saving}>Hủy thay đổi</button>
          <button type="button" className="cld-btn cld-btn--primary" onClick={handleSave} disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu vị trí'}</button>
        </div>
      </div>
    </div>
  )
}
