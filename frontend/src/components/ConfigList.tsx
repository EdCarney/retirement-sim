import { toggleTheme, useTheme } from '../theme'
import type { Plan } from '../types'

interface Props {
  plans: Plan[]
  selected: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDuplicate: () => void
  onRename: () => void
  onDelete: () => void
  onUpload: () => void
}

const GOAL_TAGS: Record<string, string> = {
  retirement_income: 'income',
  target_amount: 'target',
}

export function ConfigList({
  plans,
  selected,
  onSelect,
  onCreate,
  onDuplicate,
  onRename,
  onDelete,
  onUpload,
}: Props) {
  const theme = useTheme()
  return (
    <nav className="sidebar">
      <h1>
        Retirement Simulator
        <small>Monte Carlo plan analysis</small>
      </h1>
      {plans.map((plan) => (
        <div
          key={plan.id}
          className={`config-item${plan.id === selected ? ' selected' : ''}`}
          onClick={() => onSelect(plan.id)}
        >
          <span className="name">{plan.name}</span>
          <span className="goal-tag">{GOAL_TAGS[plan.config.goal?.type ?? ''] ?? ''}</span>
        </div>
      ))}
      {plans.length === 0 && <div className="config-item">no plans yet</div>}
      {/* One wrapping container so the buttons reflow per viewport: two per
          row on desktop (flex-basis 40%), a single row on phones. */}
      <div className="actions">
        <button onClick={onCreate}>new</button>
        <button onClick={onUpload}>upload</button>
        <button onClick={onDuplicate} disabled={!selected}>
          duplicate
        </button>
        <button onClick={onRename} disabled={!selected}>
          rename
        </button>
        <button onClick={onDelete} disabled={!selected}>
          delete
        </button>
      </div>
      <span className="spacer" />
      <button
        className="theme-toggle"
        onClick={toggleTheme}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      >
        <span className="icon">{theme === 'dark' ? '☀' : '☾'}</span>
        {theme === 'dark' ? 'Light mode' : 'Dark mode'}
      </button>
    </nav>
  )
}
