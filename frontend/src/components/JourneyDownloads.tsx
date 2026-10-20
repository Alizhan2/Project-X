import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useState } from 'react'
import { downloadJourney } from '../api'

export default function JourneyDownloads({ reference, disrupted = false }: { reference: string; disrupted?: boolean }) {
  useLanguage()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  async function download(kind: 'calendar' | 'pdf') {
    setBusy(kind); setError('')
    try { await downloadJourney(reference, kind) }
    catch (e) { setError(e instanceof Error ? e.message : t("Download failed. Please try again.")) }
    finally { setBusy(null) }
  }
  return <div className="journey-downloads">
    <div className="actions">
      <button className="secondary" disabled={busy !== null || disrupted} onClick={() => download('calendar')}>{busy === 'calendar' ? t("Preparing calendar…") : t("Add to calendar (.ics)")}</button>
      <button className="secondary" disabled={busy !== null} onClick={() => download('pdf')}>{busy === 'pdf' ? t("Preparing PDF…") : t("Download journey PDF")}</button>
    </div>
    <p className="muted small">{t("Downloaded copies do not update automatically. Re-download after a timetable change. All journeys are simulated.")}</p>
    {disrupted && <p className="warn small">{t("Resolve the disruption before adding this journey to your calendar. The PDF includes a disruption warning.")}</p>}
    {error && <p className="status-bad" role="alert">{t(error)}</p>}
  </div>
}
