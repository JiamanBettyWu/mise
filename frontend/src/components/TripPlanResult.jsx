const CATEGORY_ORDER = [
  'dresses',
  'tops',
  'bottoms',
  'outerwear',
  'shoes',
  'accessories',
  'other',
];

const CATEGORY_LABELS = {
  dresses: 'Dresses',
  tops: 'Tops',
  bottoms: 'Bottoms',
  outerwear: 'Outerwear',
  shoes: 'Shoes',
  accessories: 'Accessories',
  other: 'Other',
};

export default function TripPlanResult({ plan }) {
  const sortedList = [...(plan.packing_list || [])].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
  );

  return (
    <div className="trip-result">
      <WeatherStrip weather={plan.weather} />

      <div className="trip-result__header">
        <h2>{plan.destination}</h2>
        <p className="muted">
          {plan.start_date} → {plan.end_date} · {plan.duration_days} day
          {plan.duration_days === 1 ? '' : 's'}
        </p>
      </div>

      {plan.reasoning && <p className="trip-result__reasoning">{plan.reasoning}</p>}

      <h3>Packing list</h3>
      {sortedList.length === 0 ? (
        <p className="muted">No items selected from the catalog.</p>
      ) : (
        sortedList.map((section) => (
          <section key={section.category} className="trip-section">
            <h4>{CATEGORY_LABELS[section.category] || section.category}</h4>
            <div className="outfit__items">
              {section.items.map((item) => (
                <div key={item.id} className="outfit__item">
                  <img src={item.photo_url} alt={item.name} />
                  <div className="outfit__item-name">{item.name}</div>
                </div>
              ))}
            </div>
          </section>
        ))
      )}

      {plan.gaps?.length > 0 && (
        <section className="trip-section">
          <h3>Gaps</h3>
          <ul className="trip-gaps">
            {plan.gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </section>
      )}

      {plan.purchase_suggestions?.length > 0 && (
        <section className="trip-section">
          <h3>Purchase suggestions</h3>
          {plan.purchase_suggestions.map((s, i) => (
            <div key={i} className="purchase-block">
              <p className="muted purchase-block__gap">For: {s.gap}</p>
              <div className="purchase-grid">
                {s.results.map((r, j) => (
                  <a
                    key={j}
                    className="purchase-card"
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {r.image_url && (
                      <img src={r.image_url} alt={r.title} className="purchase-card__img" />
                    )}
                    <div className="purchase-card__body">
                      <div className="purchase-card__title">{r.title}</div>
                      <div className="muted purchase-card__meta">
                        {r.retailer}{r.retailer && r.price ? ' · ' : ''}{r.price}
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function WeatherStrip({ weather }) {
  if (!weather) return null;
  return (
    <div className="weather">
      <span>{weather.summary}</span>
    </div>
  );
}
