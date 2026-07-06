import { dump } from 'js-yaml'
import type { RawConfig } from '../../types'

// Read-only preview of what will be written to disk on save.
export function YamlPreview({ config }: { config: RawConfig }) {
  let text: string
  try {
    text = dump(config, { sortKeys: false, noRefs: true })
  } catch (error) {
    text = `could not serialize: ${error}`
  }
  return <pre className="yaml">{text}</pre>
}
