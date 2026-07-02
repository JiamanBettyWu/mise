"""Deterministic extremes gate before sampling (issue #18).

In genuinely extreme weather a slice of the wardrobe is absurd — a down coat
in a tropical heatwave, sandals in deep frost. Dropping those before the
recency sampler keeps them from displacing useful items in the candidate pool
and stops wasting prompt tokens on items the model would reject anyway.

Deliberately a hard gate, not a soft fit multiplier (docs/feedback-loop-design.md,
issue #18): the soft middle of any weather-fit curve is compositional — a
warmth-1 tee scores "bad fit" on a 3°C day yet is the base layer under the
sweater and coat — so only clear absurdities are gated, with generous bands
(inferred warmth can be off by ±1). If the gate misses something, the prompt's
weather guidance is the backstop; nothing downstream recovers from a wrongly
gated base layer, so when in doubt the item stays.

Items with warmth NULL (bags, belts — warmth-irrelevant per #40) are never gated.
"""

import logging

from observability import op
from services.categories import category_of

log = logging.getLogger("wardrobe.weather_gate")

# Daily low at/above this: maximum-warmth items (winter coat, down puffer)
# can't plausibly be worn at any point in the day.
HOT_GATE_LOW_C = 25

# Daily high at/below this: warmth-1 footwear (sandals) is absurd. Only
# footwear — unlike tops and bottoms it can't be layered or paired with
# tights, so it's the one category where minimal warmth has no cold use.
COLD_GATE_HIGH_C = -5


@op  # Weave trace node (#85); no-op unless a launcher called init_weave().
def gate_extremes(wardrobe: list[dict], weather: dict) -> list[dict]:
    """Return the wardrobe minus items absurd for today's temperatures.

    Pure and deterministic — "why wasn't the coat shown?" must have an exact
    answer, not a probabilistic one. In non-extreme weather this is the
    identity function.
    """
    low = weather.get("temp_low_c")
    high = weather.get("temp_high_c")

    gated = wardrobe
    if low is not None and low >= HOT_GATE_LOW_C:
        gated = [item for item in gated if item.get("warmth") != 5]
    if high is not None and high <= COLD_GATE_HIGH_C:
        gated = [
            item
            for item in gated
            if not (
                item.get("warmth") == 1
                and category_of(item.get("type", "")) == "footwear"
            )
        ]

    if len(gated) < len(wardrobe):
        kept = {id(item) for item in gated}
        dropped = [item.get("name") or item.get("id") for item in wardrobe if id(item) not in kept]
        log.info(
            "extremes gate dropped %d item(s) (high %s°C / low %s°C): %s",
            len(dropped),
            high,
            low,
            ", ".join(str(d) for d in dropped),
        )
    return gated
