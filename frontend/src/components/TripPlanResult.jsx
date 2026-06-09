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

// Tolerate either the new shape (object) or the old shape (string) so the UI
// doesn't break while the backend prompt is being tuned.
function normalizeGap(g) {
  if (typeof g === 'string') return { item: g, rationale: '', category: null };
  return { item: g.item, rationale: g.rationale || '', category: g.category || null };
}

export default function TripPlanResult({ plan, onPlanAnother }) {
  const sortedList = [...(plan.packing_list || [])].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
  );

  const allGaps = (plan.gaps || []).map(normalizeGap);
  const gapsByCategory = new Map();
  const uncategorizedGaps = [];
  for (const gap of allGaps) {
    if (gap.category) {
      if (!gapsByCategory.has(gap.category)) gapsByCategory.set(gap.category, []);
      gapsByCategory.get(gap.category).push(gap);
    } else {
      uncategorizedGaps.push(gap);
    }
  }

  // Make sure categories that have ONLY gaps (no catalog items) still render.
  const renderedCategories = new Set(sortedList.map((s) => s.category));
  const gapOnlyCategories = [...gapsByCategory.keys()]
    .filter((c) => !renderedCategories.has(c))
    .sort((a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b));

  return (
    <div className="trip-result">
      <WeatherStrip weather={plan.weather} />

      <div className="trip-result__header">
        <div className="trip-result__title">
          <h2>{plan.destination}</h2>
          <p className="muted">
            {plan.start_date} → {plan.end_date} · {plan.duration_days} day
            {plan.duration_days === 1 ? '' : 's'}
          </p>
        </div>
        {onPlanAnother && (
          <button
            type="button"
            className="trip-result__plan-another"
            onClick={onPlanAnother}
          >
            Plan another trip
          </button>
        )}
      </div>

      {plan.reasoning && <p className="trip-result__reasoning">{plan.reasoning}</p>}

      <h3>Packing list</h3>
      {sortedList.length === 0 && gapOnlyCategories.length === 0 ? (
        <p className="muted">No items selected from the catalog.</p>
      ) : (
        <>
          {sortedList.map((section) => (
            <CategorySection
              key={section.category}
              category={section.category}
              items={section.items}
              gaps={gapsByCategory.get(section.category) || []}
            />
          ))}
          {gapOnlyCategories.map((cat) => (
            <CategorySection
              key={cat}
              category={cat}
              items={[]}
              gaps={gapsByCategory.get(cat) || []}
            />
          ))}
        </>
      )}

      {uncategorizedGaps.length > 0 && (
        <section className="trip-section">
          <h3>Other gaps</h3>
          <ul className="trip-gaps">
            {uncategorizedGaps.map((g, i) => (
              <li key={i}>
                <strong>{g.item}</strong>
                {g.rationale && <span className="muted"> — {g.rationale}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {plan.essentials?.length > 0 && (
        <section className="trip-section">
          <h3>Don't forget</h3>
          <ul className="trip-essentials">
            {plan.essentials.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </section>
      )}

      {plan.purchase_suggestions?.length > 0 && (
        <section className="trip-section">
          <h3>Purchase suggestions</h3>
          {plan.purchase_suggestions.map((s, i) => {
            const gap = normalizeGap(s.gap);
            return (
              <div key={i} className="purchase-block">
                <div className="purchase-block__header">
                  <strong>{gap.item}</strong>
                  {gap.rationale && (
                    <p className="muted purchase-block__rationale">{gap.rationale}</p>
                  )}
                </div>
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
                          {r.retailer}
                          {r.retailer && r.price ? ' · ' : ''}
                          {r.price}
                        </div>
                      </div>
                    </a>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}

function CategorySection({ category, items, gaps }) {
  return (
    <section className="trip-section">
      <h4>{CATEGORY_LABELS[category] || category}</h4>
      {items.length > 0 && (
        <div className="outfit__items">
          {items.map((item) => (
            <div key={item.id} className="outfit__item">
              <img src={item.photo_url} alt={item.name} />
              <div className="outfit__item-name">{item.name}</div>
            </div>
          ))}
        </div>
      )}
      {gaps.length > 0 && (
        <ul className="trip-inline-gaps">
          {gaps.map((g, i) => (
            <li key={i}>
              <span className="trip-inline-gaps__icon" aria-hidden="true">⚠️</span>
              <span>
                Missing: <strong>{g.item}</strong>
                {g.rationale && <span className="muted"> — {g.rationale}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function WeatherStrip({ weather }) {
  if (!weather) return null;
  const coverageLabel = {
    full_forecast: 'Forecast',
    partial_forecast: 'Partial forecast + climate estimate',
    inferred_climate: 'Climate estimate',
  }[weather.coverage];

  return (
    <div className="weather">
      {coverageLabel && <strong className="weather__label">{coverageLabel}</strong>}
      <span>{weather.summary}</span>
    </div>
  );
}
