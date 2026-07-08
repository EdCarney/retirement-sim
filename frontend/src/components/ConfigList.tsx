import { toggleTheme, useTheme } from '../theme'
import type { ConfigListEntry } from '../types'

interface Props {
  configs: ConfigListEntry[]
  selected: string | null
  onSelect: (name: string) => void
  onCreate: () => void
  onDuplicate: () => void
  onRename: () => void
  onDelete: () => void
}

const GOAL_TAGS: Record<string, string> = {
  retirement_income: 'income',
  target_amount: 'target',
}

export function ConfigList({
  configs,
  selected,
  onSelect,
  onCreate,
  onDuplicate,
  onRename,
  onDelete,
}: Props) {
  const theme = useTheme()
  return (
    <nav className="sidebar">
      <h1>
        Retirement Simulator
        <small>Monte Carlo plan analysis</small>
      </h1>
      {configs.map((entry) => (
        <div
          key={entry.name}
          className={`config-item${entry.name === selected ? ' selected' : ''}`}
          onClick={() => onSelect(entry.name)}
          title={entry.error ?? undefined}
        >
          <span className="name">{entry.name.replace(/\.yaml$/, '')}</span>
          <span className="goal-tag">
            {entry.error ? '⚠' : GOAL_TAGS[entry.goal_type ?? ''] ?? ''}
          </span>
        </div>
      ))}
      {configs.length === 0 && <div className="config-item">no configs yet</div>}
      <div className="actions">
        <button onClick={onCreate}>new</button>
        <button onClick={onDuplicate} disabled={!selected}>
          duplicate
        </button>
      </div>
      <div className="actions">
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
