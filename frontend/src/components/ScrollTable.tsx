import type { ReactNode } from 'react'

/** Lets a wide table scroll sideways inside its card on small screens. Focusable so keyboard users can scroll it. */
export default function ScrollTable({ label, children }: { label: string; children: ReactNode }) {
  return <div className="table-scroll" role="region" aria-label={label} tabIndex={0}>{children}</div>
}
