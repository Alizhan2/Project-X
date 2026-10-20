import { t } from '../i18n'

export default function JourneyHero() {
  return <>
    <section className="journey-hero" aria-labelledby="journey-title">
      <div className="hero-copy">
        <h1 id="journey-title">{t('The whole journey.')}<br />{t('One connected plan.')}</h1>
        <p>{t('Connect buses, trains and taxis for a clear journey all the way to your destination.')}</p>
        <div className="transport-pills" aria-label={t('Travel by bus, train and taxi')}>
          <span>{t('Bus')}</span><i aria-hidden="true">—</i><span>{t('Train')}</span><i aria-hidden="true">—</i><span>{t('Taxi')}</span>
        </div>
      </div>
      <div className="hero-route" aria-label={t('A connected journey from Northgate to Portmouth Marina')}>
        <div className="hero-route-heading"><strong>{t('From your first step to arrival')}</strong><span>{t('3 legs')}</span></div>
        <div className="hero-route-art"><img src="/design/connected-route.svg" width="508" height="178" alt="" /></div>
        <div className="hero-route-places"><strong>Northgate</strong><strong>Portmouth Marina</strong></div>
        <p>{t('Connections, times and the full price. All up front.')}</p>
      </div>
    </section>
  </>
}

export function JourneyBenefits() {
  return <section className="journey-benefits" aria-label={t('Planning with Doedu')}>
    {[
      ['Every leg in one place', 'See your complete journey, including the way to the station and the final taxi.'],
      ['Understand your connections', 'Compare time, price and spare minutes between departures.'],
      ['A new plan when things change', 'If a connection breaks, choose a replacement and review the price difference.'],
    ].map(([title, body]) => <div key={title}><h2>{t(title)}</h2><p>{t(body)}</p></div>)}
  </section>
}
