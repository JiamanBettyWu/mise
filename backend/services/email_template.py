from html import escape


def render_outfit_email(weather: dict, outfits: list[dict], date_label: str) -> str:
    weather_line = (
        f"<strong>{weather['temp_high_c']}°C</strong> high "
        f"· <strong>{weather['temp_low_c']}°C</strong> low "
        f"· {escape(weather['conditions'])} "
        f"· {int(weather['precip_chance'] * 100)}% precip "
        f"· {weather['wind_kmh']} km/h wind"
    )

    if not outfits:
        body = (
            "<p style='color:#666'>No outfits to suggest — nothing available "
            "in the wardrobe today.</p>"
        )
    else:
        body = "".join(_render_outfit(i, o) for i, o in enumerate(outfits))

    return f"""\
<!doctype html>
<html><body style="font-family:-apple-system,system-ui,sans-serif;
                   max-width:600px;margin:0 auto;padding:16px;color:#222;">
  <h1 style="margin:0 0 4px;">Today's outfit</h1>
  <div style="color:#666;font-size:14px;margin-bottom:8px;">{escape(date_label)}</div>
  <div style="font-size:14px;padding:10px 12px;border:1px solid #ddd;
              border-radius:8px;margin-bottom:16px;">{weather_line}</div>
  {body}
</body></html>
"""


def _render_outfit(index: int, outfit: dict) -> str:
    reasoning = escape(outfit.get("reasoning", ""))
    label = outfit.get("label") or f"Option {index + 1}"

    if not outfit.get("items"):
        return f"""\
<div style="border:1px dashed #ccc;border-radius:10px;padding:12px;
            margin-bottom:12px;background:#fafafa;">
  <h3 style="margin:0 0 4px;color:#999;">{escape(label)}</h3>
  <p style="margin:0;color:#777;font-size:14px;">{reasoning}</p>
</div>
"""

    items_html = "".join(
        f"""<td style="padding:4px;text-align:center;vertical-align:top;width:33%;">
          <img src="{escape(item['photo_url'])}" alt="{escape(item['name'])}"
               style="width:100%;max-width:180px;aspect-ratio:1/1;object-fit:cover;
                      border-radius:6px;background:#eee;display:block;" />
          <div style="font-size:12px;margin-top:4px;line-height:1.3;">
            {escape(item['name'])}
          </div>
        </td>"""
        for item in outfit["items"]
    )
    return f"""\
<div style="border:1px solid #ddd;border-radius:10px;padding:12px;margin-bottom:12px;">
  <h3 style="margin:0 0 4px;">{escape(label)}</h3>
  <p style="margin:0 0 10px;color:#555;font-size:14px;">{reasoning}</p>
  <table cellpadding="0" cellspacing="0" border="0" width="100%"
         style="border-collapse:collapse;"><tr>{items_html}</tr></table>
  {_render_feedback_links(outfit.get("feedback_urls"))}
</div>
"""


def _render_feedback_links(urls: dict | None) -> str:
    """👍/👎 anchor pair (issue #39). Plain styled <a> tags — buttons and JS
    don't survive email clients. Empty string when the job didn't attach
    links (e.g. FEEDBACK_SECRET unset), so the email renders fine without."""
    if not urls:
        return ""
    link_style = (
        "display:inline-block;padding:6px 14px;margin-right:8px;"
        "border:1px solid #ccc;border-radius:16px;text-decoration:none;"
        "color:#333;font-size:13px;background:#f7f7f7;"
    )
    return f"""\
<div style="margin-top:10px;">
    <a href="{escape(urls['up'])}" style="{link_style}">👍 Good pick</a>
    <a href="{escape(urls['down'])}" style="{link_style}">👎 Not for me</a>
  </div>"""
