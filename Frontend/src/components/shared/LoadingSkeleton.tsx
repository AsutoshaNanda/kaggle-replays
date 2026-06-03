// Shimmer skeleton placeholders.

import type { CSSProperties, JSX } from 'react'

type Shape = 'card' | 'row' | 'text' | 'circle'

interface LoadingSkeletonProps {
  width?: string
  height?: string
  borderRadius?: string
  className?: string
  shape?: Shape
}

const SHAPE_STYLE: Record<Shape, CSSProperties> = {
  card: { width: '100%', height: '160px', borderRadius: 16 },
  row: { width: '100%', height: '40px', borderRadius: 8 },
  text: { width: '80%', height: '14px', borderRadius: 6 },
  circle: { width: '36px', height: '36px', borderRadius: '50%' },
}

export function LoadingSkeleton({
  width,
  height,
  borderRadius,
  className = '',
  shape,
}: LoadingSkeletonProps): JSX.Element {
  const base = shape ? SHAPE_STYLE[shape] : {}
  const style: CSSProperties = {
    ...base,
    ...(width !== undefined ? { width } : {}),
    ...(height !== undefined ? { height } : {}),
    ...(borderRadius !== undefined ? { borderRadius } : {}),
  }
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />
}

// Convenience: a card-shaped skeleton matching CompetitionCard.
export function SkeletonCard(): JSX.Element {
  return (
    <div
      className="glass-card overflow-hidden"
      style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <LoadingSkeleton width="80px" height="22px" borderRadius="999px" />
      <LoadingSkeleton width="90%" height="20px" />
      <LoadingSkeleton width="50%" height="12px" />
      <div style={{ marginTop: 'auto' }}>
        <LoadingSkeleton width="40%" height="14px" />
      </div>
    </div>
  )
}
