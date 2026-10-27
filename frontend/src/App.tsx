import { useCallback, useEffect, useRef, useState } from 'react'
import { api, useMock } from './api'
import type { DocumentInfo, Settings } from './api'
import { errorMessage } from './errors'
import { DocumentsPanel } from './components/DocumentsPanel'
import { SettingsPanel } from './components/SettingsPanel'
import { AskPanel } from './components/AskPanel'
import './App.css'

export default function App() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [docsError, setDocsError] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const [settings, setSettings] = useState<Settings | null>(null)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsError, setSettingsError] = useState<string | null>(null)

  // Ids seen in the previous list: lets us auto-select only newly uploaded documents.
  const knownIds = useRef<Set<string>>(new Set())

  const applyDocuments = useCallback((docs: DocumentInfo[]) => {
    const known = knownIds.current
    knownIds.current = new Set(docs.map((d) => d.id))
    setDocuments(docs)
    // New documents start selected; deleted ones disappear from the selection.
    setSelectedIds(
      (prev) => new Set(docs.filter((d) => prev.has(d.id) || !known.has(d.id)).map((d) => d.id)),
    )
    setDocsError(null)
    setDocsLoading(false)
  }, [])

  const showDocumentsError = useCallback((e: unknown) => {
    setDocsError(errorMessage(e))
    setDocsLoading(false)
  }, [])

  const loadDocuments = useCallback(async () => {
    try {
      applyDocuments(await api.listDocuments())
    } catch (e) {
      showDocumentsError(e)
    }
  }, [applyDocuments, showDocumentsError])

  // Initial load of documents and settings.
  useEffect(() => {
    api.listDocuments().then(applyDocuments).catch(showDocumentsError)
    api
      .getSettings()
      .then(setSettings)
      .catch((e: unknown) => setSettingsError(`Could not load settings: ${errorMessage(e)}`))
  }, [applyDocuments, showDocumentsError])

  function toggle(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function saveSettings(next: Settings) {
    setSettingsSaving(true)
    setSettingsError(null)
    try {
      setSettings(await api.saveSettings(next))
      await loadDocuments() // chunk counts change after re-indexing
    } catch (e) {
      setSettingsError(`Settings were not saved: ${errorMessage(e)}`)
    } finally {
      setSettingsSaving(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Corpus Q&amp;A</h1>
        <p className="muted">Answers are built only from the passages shown under each answer.</p>
        {useMock && <p className="mock-badge">Mock mode: no backend is called.</p>}
      </header>

      <div className="layout">
        <aside className="sidebar">
          <DocumentsPanel
            documents={documents}
            loading={docsLoading}
            selectedIds={selectedIds}
            onToggle={toggle}
            onChanged={loadDocuments}
          />
          {docsError && <p className="error-text" role="alert">Could not load documents: {docsError}</p>}
          {/* The key resets the form whenever new settings arrive from the server. */}
          <SettingsPanel
            key={settings ? JSON.stringify(settings) : 'loading'}
            settings={settings}
            saving={settingsSaving}
            error={settingsError}
            onSave={saveSettings}
          />
        </aside>

        <main>
          <AskPanel
            selectedIds={documents.filter((d) => selectedIds.has(d.id)).map((d) => d.id)}
            topK={settings?.top_k ?? null}
          />
        </main>
      </div>
    </div>
  )
}
