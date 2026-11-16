import { useEffect, useId, useState } from 'react'
import type { CSSProperties } from 'react'
import { api } from '../api'
import type { DocGraph, DocumentInfo, Reference } from '../api'
import { errorMessage } from '../errors'

type Props = { documents: DocumentInfo[]; selectedIds: Set<string> }
type Node = DocGraph['nodes'][number]
type Edge = DocGraph['edges'][number]

const typeColors: Record<string, string> = {
  Person: 'var(--concept-person)', Team: 'var(--concept-team)',
  Service: 'var(--concept-service)', Concept: 'var(--concept-idea)',
}
const color = (type: string) => typeColors[type] ?? 'var(--concept-other)'
const shortName = (name: string) => Array.from(name).length > 18 ? `${Array.from(name).slice(0, 17).join('')}…` : name

export function ConceptMap({ documents, selectedIds }: Props) {
  const [chosenId, setChosenId] = useState('')
  const document = documents.find((doc) => doc.id === chosenId)
    ?? documents.find((doc) => selectedIds.has(doc.id)) ?? documents[0]

  return (
    <section className="panel concept-map" aria-label="Concept map">
      <h2>Concept map</h2>
      {documents.length === 0 ? <p className="muted">Upload a document to explore its concepts.</p> : <>
        <label className="concept-document">
          Document
          <select value={document.id} onChange={(event) => setChosenId(event.target.value)}>
            {documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.filename}</option>)}
          </select>
        </label>
        <DocumentGraph key={document.id} document={document} />
      </>}
    </section>
  )
}

function DocumentGraph({ document }: { document: DocumentInfo }) {
  const [graph, setGraph] = useState<DocGraph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [run, setRun] = useState({ build: false, attempt: 0 })

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    async function read() {
      try {
        const result = await api.getDocGraph(document.id)
        if (cancelled) return
        setGraph(result)
        setLoading(false)
        if (result.status === 'building') timer = setTimeout(() => { void read() }, 2000)
      } catch (e) {
        if (!cancelled) {
          setError(`Could not load the concept map: ${errorMessage(e)}`)
          setLoading(false)
        }
      }
    }
    async function start() {
      if (run.build) {
        try {
          await api.buildDocGraph(document.id)
        } catch (e) {
          if (!cancelled) {
            setError(`Could not build the concept map: ${errorMessage(e)}`)
            setLoading(false)
          }
          return
        }
      }
      if (!cancelled) await read()
    }
    void start()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [document.id, run])

  function retry(build: boolean) {
    setError(null)
    setLoading(true)
    setRun((previous) => ({ build, attempt: previous.attempt + 1 }))
  }

  if (loading) return <p className="muted" role="status">{run.build ? 'Starting the concept map…' : 'Loading the concept map…'}</p>
  if (error) return <div><p className="error-text" role="alert">{error}</p><button type="button" onClick={() => retry(false)}>Try again</button></div>
  if (!graph) return <p className="muted">The concept map is unavailable.</p>
  if (graph.status === 'none') return <div>
    <p>No concept map yet for this document. Building it reads every passage with the AI model (about {document.n_chunks} calls).</p>
    <button type="button" onClick={() => retry(true)}>Build concept map</button>
  </div>
  if (graph.status === 'building') return <div className="concept-progress" role="status">
    <label htmlFor={`concept-progress-${document.id}`}>Reading passage {graph.progress.done} of {graph.progress.total}…</label>
    <progress id={`concept-progress-${document.id}`} value={graph.progress.done} max={Math.max(1, graph.progress.total)} />
  </div>
  if (graph.status === 'error') return <div>
    <p className="error-text" role="alert">{graph.error || 'The AI model could not build this concept map.'}</p>
    <button type="button" onClick={() => retry(true)}>Try again</button>
  </div>
  return <ReadyGraph graph={graph} />
}

function ReadyGraph({ graph }: { graph: DocGraph }) {
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const counts = new Map(graph.nodes.map((node) => [node.id, 0]))
  for (const edge of graph.edges) {
    counts.set(edge.source, (counts.get(edge.source) ?? 0) + 1)
    if (edge.target !== edge.source) counts.set(edge.target, (counts.get(edge.target) ?? 0) + 1)
  }
  const sorted = [...graph.nodes].sort((a, b) => (counts.get(b.id) ?? 0) - (counts.get(a.id) ?? 0) || a.name.localeCompare(b.name))
  const selected = graph.nodes.find((node) => node.id === selectedId) ?? sorted[0]
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]))
  const links = selected ? graph.edges.filter((edge) => edge.source === selected.id || edge.target === selected.id) : []
  const stats = graph.stats

  return <>
    {stats && <p className="muted small">{stats.nodes} concepts · {stats.edges} links · built with {stats.model} in {stats.seconds} s ({stats.llm_calls} AI calls, {stats.tokens} tokens)</p>}
    {!selected ? <p>The AI model found no concepts in this document.</p> : <>
      <div className="concept-layout">
        <aside className="concept-browser" aria-label="Concepts">
          <label className="concept-search">Find a concept
            <input type="search" placeholder="Find a concept" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <ul className="concept-list">
            {sorted.filter((node) => node.name.toLowerCase().includes(search.toLowerCase())).map((node) => <li key={node.id}>
              <button type="button" aria-pressed={selected.id === node.id} onClick={() => setSelectedId(node.id)}>
                <span>{node.name}</span>
                <span className="concept-type" style={{ '--concept-color': color(node.type) } as CSSProperties}>{node.type}</span>
                <span className="muted small">{counts.get(node.id) ?? 0} links</span>
              </button>
            </li>)}
          </ul>
          {!sorted.some((node) => node.name.toLowerCase().includes(search.toLowerCase())) && <p className="muted small">No matching concepts.</p>}
        </aside>
        <div className="concept-canvas">
          <NeighbourMap selected={selected} links={links} nodesById={nodesById} onSelect={setSelectedId} />
        </div>
      </div>
      <h3>Links for {selected.name}</h3>
      {links.length === 0 && <p className="muted">This concept has no links.</p>}
      <ul className="concept-links" key={selected.id}>
        {links.map((edge, index) => <li key={index}>
          <PassageLink edge={edge} source={nodesById.get(edge.source)?.name ?? edge.source} target={nodesById.get(edge.target)?.name ?? edge.target} />
        </li>)}
      </ul>
    </>}
  </>
}

function NeighbourMap({ selected, links, nodesById, onSelect }: {
  selected: Node; links: Edge[]; nodesById: Map<string, Node>; onSelect: (id: string) => void
}) {
  const markerId = useId()
  const neighbourIds = [...new Set(links.flatMap((edge) => [edge.source, edge.target]))]
    .filter((id) => id !== selected.id && nodesById.has(id))
  const visible = neighbourIds.slice(0, 14)
  const positions = new Map(visible.map((id, index) => {
    const angle = index * Math.PI * 2 / visible.length - Math.PI / 2
    return [id, { x: 300 + 230 * Math.cos(angle), y: 200 + 156 * Math.sin(angle) }]
  }))
  function nodeShape(node: Node, x: number, y: number, interactive: boolean) {
    return <g key={node.id} className={interactive ? 'concept-svg-node concept-svg-neighbour' : 'concept-svg-node'}
      transform={`translate(${x} ${y})`} role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined} aria-label={interactive ? `Explore ${node.name}` : undefined}
      onClick={interactive ? () => onSelect(node.id) : undefined}
      onKeyDown={interactive ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(node.id) }
      } : undefined}>
      <title>{node.name} ({node.type})</title>
      <circle r={interactive ? 19 : 27} style={{ fill: color(node.type) }} />
      <text y={interactive ? 36 : 44} textAnchor="middle">{shortName(node.name)}</text>
    </g>
  }
  return <svg className="concept-svg" width="100%" viewBox="0 0 600 420" role="group" aria-label={`Direct neighbours of ${selected.name}`}>
    <defs><marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" className="concept-arrow" />
    </marker></defs>
    {links.map((edge, index) => {
      const neighbourId = edge.source === selected.id ? edge.target : edge.source
      if (neighbourId === selected.id) return <g key={index}>
        <path d="M 280 180 C 245 110 355 110 320 180" className="concept-edge" markerEnd={`url(#${markerId})`} />
        <text x="300" y="130" textAnchor="middle" className="concept-relation">{edge.relation}</text>
      </g>
      const position = positions.get(neighbourId)
      if (!position) return null
      const dx = position.x - 300, dy = position.y - 200
      const length = Math.hypot(dx, dy), ux = dx / length, uy = dy / length
      const parallel = links.filter((link) => (link.source === selected.id ? link.target : link.source) === neighbourId)
      const offset = (parallel.indexOf(edge) - (parallel.length - 1) / 2) * 16
      const start = { x: 300 + ux * 31 - uy * offset, y: 200 + uy * 31 + ux * offset }
      const end = { x: position.x - ux * 24 - uy * offset, y: position.y - uy * 24 + ux * offset }
      const outgoing = edge.source === selected.id
      return <g key={index}>
        <line x1={outgoing ? start.x : end.x} y1={outgoing ? start.y : end.y}
          x2={outgoing ? end.x : start.x} y2={outgoing ? end.y : start.y}
          className="concept-edge" markerEnd={`url(#${markerId})`} />
        <text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 5} textAnchor="middle" className="concept-relation">{edge.relation}</text>
      </g>
    })}
    {nodeShape(selected, 300, 200, false)}
    {visible.map((id) => nodeShape(nodesById.get(id)!, positions.get(id)!.x, positions.get(id)!.y, true))}
    {neighbourIds.length > 14 && <text x="300" y="410" textAnchor="middle" className="concept-relation">+{neighbourIds.length - 14} more</text>}
  </svg>
}

function PassageLink({ edge, source, target }: { edge: Edge; source: string; target: string }) {
  const [open, setOpen] = useState(false)
  const [passage, setPassage] = useState<Reference | null>(null)
  const [error, setError] = useState<string | null>(null)
  const chunkId = edge.chunk_ids[0]
  useEffect(() => {
    if (!open || !chunkId || passage) return
    let cancelled = false
    api.getChunk(chunkId).then((result) => {
      if (!cancelled) setPassage(result)
    }).catch((e: unknown) => {
      if (!cancelled) setError(`Could not load the passage: ${errorMessage(e)}`)
    })
    return () => { cancelled = true }
  }, [open, chunkId, passage])

  return <>
    <div className="concept-link-row">
      <span>{source} —{edge.relation}→ {target}</span>
      <button type="button" className="link-button" aria-expanded={open} disabled={!chunkId}
        onClick={() => { setError(null); setOpen((previous) => !previous) }}>Passage</button>
    </div>
    {!chunkId && <p className="muted small">No passage is available for this link.</p>}
    {open && <div aria-live="polite">
      {error ? <p className="error-text" role="alert">{error}</p> : passage ? <>
        <p className="muted small">{passage.filename} · passage {passage.chunk_index + 1}</p>
        <blockquote className="chunk-text">{passage.text}</blockquote>
      </> : <p className="muted small">Loading the passage…</p>}
    </div>}
  </>
}
