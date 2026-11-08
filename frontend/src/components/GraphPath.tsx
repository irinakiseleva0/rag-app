import type { GraphPath as GraphPathData } from '../api'

export function GraphPath({ path }: { path: GraphPathData | null }) {
  if (path === null) return null

  return (
    <section className="graph-path" aria-label="Graph retrieval path">
      {path.entities.length === 0 ? (
        <p className="muted">No entity from the graph was found in the question.</p>
      ) : (
        <>
          <h3>Entities in the question:</h3>
          <ul className="graph-entities">
            {path.entities.map((entity, index) => (
              <li className="graph-entity-chip" key={`${entity}-${index}`}>{entity}</li>
            ))}
          </ul>
          <h3>Edges followed:</h3>
          <ul className="graph-edges">
            {path.edges.map((edge, index) => (
              <li className="graph-edge" key={`${edge.chunk_id}-${index}`}>
                <span>{edge.from} —{edge.relation}→ {edge.to}</span>
                <small className="muted">{edge.chunk_id}</small>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
