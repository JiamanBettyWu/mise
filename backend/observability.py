"""Weave tracing bootstrap (#85).

Observability only — deliberately kept off the Render request path and the
GitHub-cron hot path. There is NO env-var toggle: the only caller is the manual
launcher jobs/trace_daily.py, so *running that script* is the opt-in. The
scheduled cron calls daily_outfit.py, which never imports this module, so
automated runs stay untraced (see the flag-vs-entry-point discussion behind
#85).
"""

import logging
import os

log = logging.getLogger("wardrobe.weave")

# `op` is the decorator the pipeline files use (`from observability import op`).
# On Render, `weave` is NOT installed (it's dev-only, absent from
# requirements.txt), so a bare `import weave` in a hot-path module would crash
# the backend at import time. This shim resolves to the real `weave.op` when
# weave is present and to an identity decorator when it isn't — so the same
# `@op` works in prod (no-op), locally without init (inert, see #85 check), and
# locally with init (traces). Supports both `@op` and `@op(...)` forms.
try:
    import weave as _weave

    op = _weave.op
except ImportError:  # weave not installed (Render prod path)

    def op(fn=None, *_args, **_kwargs):
        if fn is None:
            return lambda f: f
        return fn


def init_weave() -> bool:
    """Start Weave tracing. Returns True if tracing is live, False otherwise.

    Call once, after load_dotenv and BEFORE importing the pipeline modules, so
    the Anthropic SDK autopatch is installed before any client is built.

    Degrades to a clear warning — never a crash — if `weave` isn't installed or
    auth is missing, so a trace run that can't trace still runs the pipeline.
    """
    project = os.getenv("WEAVE_PROJECT", "wardrobe-ai")
    try:
        _weave.init(project)
        log.info("weave tracing enabled → project %r", project)
        return True
    except NameError:
        log.warning("weave is not installed; running untraced")
        return False
    except Exception:
        log.warning(
            "weave init failed; running untraced (is WANDB_API_KEY set?)",
            exc_info=True,
        )
        return False
