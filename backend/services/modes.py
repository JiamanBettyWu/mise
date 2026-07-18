"""The canonical outfit modes and their prompt descriptions.

Moved out of jobs/daily_outfit.py for #145: the refinement graph's regenerate
node needs a mode's description to rerun the pipeline for one mode, and a
service can't import from jobs/. The daily job imports DAILY_MODES from here;
the first entry (Smart casual) remains the calendar floor mode (#64).
"""

DAILY_MODES = [
    {
        "name": "Smart casual",
        "description": (
            "Default mode for a normal day. Polished but relaxed — workable in "
            "an office without a strict dress code, and equally good for going "
            "out afterward. Avoid athleisure or formal-only pieces."
        ),
    },
    {
        "name": "Athleisure",
        "description": (
            "Workout-friendly, casual, comfortable for active days. Think "
            "joggers, leggings, sneakers, breathable layers. Skip dress shirts, "
            "blazers, heels, or anything restrictive."
        ),
    },
    {
        "name": "Elevated",
        "description": (
            "Polished and elegant for nicer occasions — date night, dinner, "
            "events. Lean into formal or smart-casual pieces, refined fabrics, "
            "and dressier shoes. Avoid athleisure or rugged casual."
        ),
    },
]


def mode_by_name(name: str) -> dict | None:
    """The full mode dict for a stored outfit_history mode label, or None.

    Web-generated rows carry mode "(default)" (no modes were passed), which
    has no description — callers treat None as "regenerate without modes".
    """
    for mode in DAILY_MODES:
        if mode["name"] == name:
            return mode
    return None
