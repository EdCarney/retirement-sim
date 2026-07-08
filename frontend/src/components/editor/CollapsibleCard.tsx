import type { KeyboardEvent, ReactNode } from 'react'
import { useCollapsed } from '../../collapse'

interface Props {
  /** Stable storage key for this section's collapsed state. */
  id: string
  title: string
  /** Optional header content (e.g. a running total) that stays visible even
   *  when the card is collapsed. */
  extra?: ReactNode
  children: ReactNode
}

// A `section.card` whose body collapses behind a clickable header. The collapsed
// state persists per section id (see collapse.ts). The body stays mounted and is
// hidden with the `hidden` attribute so in-progress field edits aren't discarded.
export function CollapsibleCard({ id, title, extra, children }: Props) {
  const [collapsed, toggle] = useCollapsed(id)
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggle()
    }
  }
  return (
    <section className="card">
      <div
        className="card-head"
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        onClick={toggle}
        onKeyDown={onKeyDown}
      >
        <span className={`chevron${collapsed ? ' collapsed' : ''}`} aria-hidden="true">
          ▾
        </span>
        <h3>{title}</h3>
        {extra !== undefined && <span className="card-head-extra">{extra}</span>}
      </div>
      <div className="card-body" hidden={collapsed}>
        {children}
      </div>
    </section>
  )
}
