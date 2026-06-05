# Design system

The visual language for Wardrobe AI's frontend. The codebase is the source of truth — this doc captures the *principles*, *vocabulary*, and *non-obvious decisions* behind the code so future changes stay coherent.

## Principles

1. **Glass over solid surfaces.** Translucent white panels with `backdrop-filter: blur` layered over a colored gradient. The blur reacting to the gradient is what makes the app feel alive.
2. **One display font, one functional font.** EB Garamond for headings/names; system-ui sans for body, controls, and metadata. The serif is the typographic identity — it carries from cards to modal to outfit labels and gives the app one voice.
3. **Funnel layout: narrow input, wide output.** Forms live in left-aligned columns; results expand to the container width. The shift signals "you've moved from deciding to consuming."
4. **Shape signals function.** Pills (radius `999px`) for actions, gently-rounded rectangles (radius `12px`) for text input, soft cards (radius `16–24px`) for content. Never mix — each shape carries meaning.
5. **Restraint over decoration.** One palette, one serif, consistent radii. New components should reuse the existing vocabulary, not introduce new shapes or colors.

## Visual vocabulary

### Color palette

Global gradient backdrop ([frontend/src/styles.css](frontend/src/styles.css), `body`):

| Stop                | Color     | Position    |
|---------------------|-----------|-------------|
| Periwinkle          | `#d7e0f8` | 15% / 10%   |
| Dusty mauve         | `#E5DBE6` | 30% / 20%   |
| Warm rose           | `#E7DAE3` | 85% / 80%   |
| Base                | `#eef1f8` | (fill)      |

Other ink:
- **Text**: `rgba(20, 20, 40, *)` at alpha `0.55–0.95` depending on emphasis. Never pure black.
- **Warning**: `rgba(184, 134, 11, *)` — warm gold, only used for inline gap callouts.
- **Danger**: `#b3261e` — destructive actions only.

### Typography

- **Display**: `'EB Garamond', Georgia, 'Times New Roman', serif` — loaded via Google Fonts in [frontend/index.html](frontend/index.html). Used for card names, modal headlines, section headings, outfit labels.
- **Functional**: inherits `system-ui, -apple-system, sans-serif` from `:root`. All controls and body copy.
- **Letter-spacing**: `0` on serifs (EB Garamond has built-in kerning); `-0.005em` on sans-serif display headings for slight tightening.

### Glass surface formula

Each glass surface tunes three knobs (codified as CSS variables on cards and modal):

| Surface         | Tint        | Blur  | Radius | File |
|-----------------|-------------|-------|--------|------|
| Card            | 0.30        | 90px  | 22px   | [ClothingCardGlass.css](frontend/src/components/ClothingCardGlass.css) |
| Modal           | 0.55–0.80   | 60px  | 24px   | [ItemDetailModal.css](frontend/src/components/ItemDetailModal.css) |
| Modal backdrop  | (n/a — tint 0.18, just blurs) | 10px | — | same |
| Nav             | 0.55        | 20px  | 999px  | [styles.css](frontend/src/styles.css) `.nav` |
| Button          | 0.50        | 8px   | 999px  | [styles.css](frontend/src/styles.css) `button` |
| Input / textarea| 0.55        | 8px   | 12px   | [styles.css](frontend/src/styles.css) inputs |
| Outfit tile     | 0.45        | 20px  | 16px   | [styles.css](frontend/src/styles.css) `.outfit__item` |
| Purchase card   | 0.50        | 20px  | 18px   | [styles.css](frontend/src/styles.css) `.purchase-card` |
| Weather strip   | 0.50        | 12px  | 16px   | [styles.css](frontend/src/styles.css) `.weather` |

**Pattern**: surfaces with more text get *higher* tint (readability); decorative tiles get *lower* tint (atmosphere). Border radius scales with surface size.

### Border radius scale

- `999px` — buttons, nav, nav links (cylindrical = "short action")
- `12px` — text inputs, file input (rounded rectangle = "type something")
- `16–18px` — small content tiles (outfit items, purchase cards, weather)
- `22–24px` — cards and modal (soft and present)

### Spacing rhythm

- `.form-page` and `.outfit__items` use `gap: 0.75–0.9rem`
- Section spacing uses `1.25–2rem` margins
- Card / tile internal `padding: 8–14px` depending on scale

Keep new layouts in these ranges. Off-grid values like `13px` or `1.1rem` arbitrary signal accidental design.

## Component patterns

- **Catalog cards** — [ClothingCardGlass.jsx](frontend/src/components/ClothingCardGlass.jsx). Interactive glass tile (photo + serif name + muted metadata + inline toggles). Opens modal on click.
- **Item detail modal** — [ItemDetailModal.jsx](frontend/src/components/ItemDetailModal.jsx). Two-layer glass: backdrop blurs the page underneath, panel frosts on top. Use for *any* focused detail view.
- **Glass nav** — [App.jsx](frontend/src/App.jsx). Sticky floating pill at the top; active page highlighted with a dark filled pill. Uses `NavLink` (not `Link`) for the auto-active class.
- **Buttons**:
  - **Primary glass pill** — global `button` style. Use as default.
  - **Danger** — `.danger` modifier. Same glass pill, red tint.
  - **Ghost** — transparent background that fills on hover. Pattern: `.nav__lock`, `.trip-result__plan-another`. Use for secondary/quiet actions next to a primary one.
- **Form pages** — [TodayOutfit.jsx](frontend/src/pages/TodayOutfit.jsx), [TripPlan.jsx](frontend/src/pages/TripPlan.jsx). `.page-header` row for title + any page-level toggles (top-right). `.form-page` wrapper below for form content in a left-aligned column with consistent vertical rhythm.
- **Small content tiles** — `.outfit__item` is the shared mini-tile pattern (TodayOutfit results, Trip packing lists). Reuse it; don't invent a new tile shape.

## Decisions log

Append-only. Date each entry. When a decision reverses, *replace* the old entry (don't add a "(superseded)" note — that's how docs rot).

- **2026-06-04** — *Travel mode toggle lives in `.page-header__actions` on every page where it exists.* Consistency of placement trumps local context, even though it's a view-filter on Catalog and a generation-input on Today.
- **2026-06-04** — *Modal backdrop padding is `2rem 1.5rem`.* Phone viewports needed bigger tap-to-close margins; the original `1rem` violated Apple's 44px touch-target guideline.
- **2026-06-04** — *Serifs use `letter-spacing: 0`.* EB Garamond is designed with kerning built in; tightening it makes it feel cramped. Negative letter-spacing is a sans-serif move only.
- **2026-06-04** — *Form pages are left-aligned at `#root` width.* Centered narrow forms felt formal in a way that didn't match the calm/intentional tone.
- **2026-06-04** — *Generate stays in the form area; "Plan another trip" lives in the result header.* They're opposite actions (regenerate same trip vs discard and restart), so they pair with the surfaces they act on.
- **2026-06-04** — *Trip date inputs capped at `180px` each.* Dates only need ~10 characters; stretching them with `1fr` looked silly.
- **2026-06-04** — *Glass tint inversely scales with content density.* Cards: low tint (0.30) for atmosphere; modal: higher tint (0.55+) for readability. This isn't aesthetic preference — flattening it breaks readability.
- **2026-06-04** — *Focus indicators are a `box-shadow` halo, not `outline`.* Default browser outlines fought the glass language; the halo is the accessibility-respecting replacement. Don't `outline: none` without adding a halo.
- **2026-06-04** — *Modal close button uses `system-ui` font, `display: flex` centering, `padding: 0`.* EB Garamond was bleeding into the `×` glyph; flex centering avoids glyph-metric variance.
- **2026-06-04** — *App-wide gradient applies to `body` directly, not scoped via `:has(.glass-card)`.* Glass is the app's design language now — every page should read as one continuous surface.
- **2026-06-04** — *Editorial variant (Fraunces serif, flat layout) was explored and dropped from the app.* Kept as a potential landing/marketing-page direction; recoverable from git history (`feat/glass-card-design`) if revisited.
- **2026-06-04** — *Destination combobox dropdown uses the same `12px` radius and glass tint as text inputs, but a higher tint (0.92) than cards.* The menu is a transient decision surface — readability beats atmosphere; matching the input's radius keeps the field + menu reading as one component.

## Maintaining this doc

- **Edit in the same commit as the code change.** Not in a follow-up commit — it'll never happen.
- **Document the non-obvious only.** If a reader could figure it out by reading the code, leave it out. Save lines for the *why*.
- **Re-read before adding a new component.** The Principles list is the checklist.
- **Replace stale entries.** If a decision reverses, edit the old entry in place. The log captures *current* truth, not historical revisions — git history has those.
