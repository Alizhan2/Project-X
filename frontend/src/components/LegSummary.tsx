import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import type { Itinerary, Tri } from '../api'
import { money } from '../format'
import Timeline from './Timeline'
import ScrollTable from './ScrollTable'

const tri = (v: Tri) => (v === 'yes' ? t('yes') : v === 'no' ? t('no') : t("not known"))

export default function LegSummary({ it }: { it: Itinerary }) {
  useLanguage()
  return (
    <>
      <Timeline buffers={it.transfer_buffers} legs={it.legs.map((l) => ({
        departs_at: l.departs_at, arrives_at: l.arrives_at, from: l.from.name, to: l.to.name, mode: l.mode,
        operator: l.operator, route_code: l.route_code,
        note: l.status === 'delayed' ? t("Delayed by {0} min (times include the delay)", {0: l.delay_minutes}) : undefined,
      }))} />
      <ScrollTable label={t("Fare and accessibility per leg")}>
      <table className="legs">
        <caption className="sr-only">{t("Fare and accessibility per leg")}</caption>
        <thead><tr><th scope="col">{t("Leg")}</th><th scope="col">{t("Fare")}</th><th scope="col">{t("Accessibility")}</th><th scope="col">{t("Cancellation")}</th></tr></thead>
        <tbody>
          {it.legs.map((l) => (
            <tr key={`${l.route_code}-${l.departs_at}`}>
              <th scope="row">{l.route_code} {placeName(l.from.name)} → {placeName(l.to.name)}</th>
              <td>{money(l.unit_price, it.currency)} {l.price_basis === 'vehicle' ? t("per taxi (up to 4 passengers)") : t("per passenger")}</td>
              <td>{t("Wheelchair vehicle:")} {tri(l.accessibility.wheelchair_vehicle)}<br />{t("Step-free at boarding:")} {tri(l.accessibility.origin_step_free)}<br />{t("Step-free at arrival:")} {tri(l.accessibility.destination_step_free)}</td>
              <td>{t(l.cancellation_policy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </ScrollTable>
    </>
  )
}
