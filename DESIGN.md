# Design system

The visual language for Wardrobe AI's frontend. The codebase is the source of truth — this doc captures the *principles*, *vocabulary*, and *non-obvious decisions* behind the code so future changes stay coherent.

## Principles

1. **Glass over solid surfaces.** Translucent white panels with `backdrop-filter: blur` layered over a colored gradient. The blur reacting to the gradient is what makes the app feel alive.
2. **One display font, one functional font.** A serif (currently Cormorant Garamond) for headings/names; a sans (currently DM Sans) for body, controls, and metadata. The serif is the typographic identity — it carries from cards to modal to outfit labels and gives the app one voice. The *faces* are swappable via font tokens (see Typography); the *one-serif-one-sans* rule is not.
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

- **Display**: `'Cormorant Garamond', Georgia, serif` — the editorial serif that carries the app's identity. Used for card names, modal headlines, section headings, outfit labels. Applied via the `--font-heading` token; never hardcoded in CSS.
- **Functional**: `'DM Sans', system-ui, sans-serif` via the `--font-body` token. All controls and body copy.
- **Font tokens**: `--font-heading` / `--font-body` / `--font-mono` are set at runtime by `FontProvider` ([frontend/src/fonts.jsx](frontend/src/fonts.jsx)), which also injects the Google Fonts `<link>`. Re-theme the whole app by changing `ACTIVE_COMBO`; a **dev-only** `<FontPicker>` (stripped from production builds) previews combos live. CSS reads the tokens — it must never hardcode a family. The lone exception is the modal close button (`system-ui`, a glyph-safety choice — see decisions log).
- **Letter-spacing**: `0` on serifs (Garamond-family faces have built-in kerning); `-0.005em` on sans-serif display headings for slight tightening.

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

- **Catalog cards** — [ClothingCardGlass.jsx](frontend/src/components/ClothingCardGlass.jsx). Interactive glass tile (photo + serif name + muted metadata + inline toggle chips). Opens modal on click.
- **Toggle chips** — base `.chip` in [styles.css](frontend/src/styles.css) (shared vocabulary); on-state modifiers live next to their components. Pill (999px) that toggles a state on/off. Off = ghost pill (translucent + faint border) so it still reads as pressable, not as metadata text. On-states carry meaning in fill *weight*: `--on-laundry` soft muted fill (passive), `--on-packed` strong ink fill (committed) — both in [ClothingCardGlass.css](frontend/src/components/ClothingCardGlass.css); `--on-verdict` strong ink (committed) for the outfit feedback thumbs in styles.css. Rendered as `<button aria-pressed>` for free focus/keyboard support. Note: every on-state needs its own explicit `:hover` rule — the global `button:hover` outranks a bare `.chip`.
- **Item detail modal** — [ItemDetailModal.jsx](frontend/src/components/ItemDetailModal.jsx). Two-layer glass: backdrop blurs the page underneath, panel frosts on top. Use for *any* focused detail view.
- **Glass nav** — [App.jsx](frontend/src/App.jsx). Sticky floating pill at the top; active page highlighted with a dark filled pill. Uses `NavLink` (not `Link`) for the auto-active class.
- **Buttons**:
  - **Primary glass pill** — global `button` style. Use as default.
  - **Danger** — `.danger` modifier. Same glass pill, red tint.
  - **Ghost** — `.ghost` modifier (transparent background that fills on hover). Use for secondary/quiet actions next to a primary one. `.nav__lock` and `.trip-result__plan-another` are older bespoke instances of the same pattern.
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
- **2026-06-05** — *Today's Outfit "Clear" sits next to Generate in the form's button row, not in a result header.* Unlike Trip (where the form collapses and "Plan another trip" lives in the result header), Today's form stays visible alongside results, so the discard action pairs with the primary button on the same surface. Clear preserves Travel mode — it's a standing preference, not part of a single ask. Surfaced only when there's something to clear (`data || notes`). Ghost styling promoted to a reusable `.ghost` modifier.
- **2026-06-05** — *Catalog card "In laundry" / "Packed" controls are glass toggle chips, not native checkboxes.* Native checkboxes were the one OS-default, un-glassy element on the card (violating principles 1 & 5); a pill is also the shape-correct control for a toggle (principle 4, "shape signals function"). The two on-states use **different fill weights on purpose** — laundry soft/muted (a passive "unavailable" state that also reuses the card's `--unavailable` dimming), packed strong-ink (a deliberate commitment) — staying inside the one-palette rule (ink-alpha on glass, no new colors). Off-state is a ghost pill, kept deliberately distinct from the `type · color` metadata so its tappability is legible. Bonus: the whole pill is a tap target vs a ~16px box (cf. the 44px guideline).
- **2026-06-05** — *Typography moved from a hardcoded `'EB Garamond'` to runtime CSS tokens (`--font-heading/body/mono`), and the active pairing is now **Cormorant Garamond + DM Sans**.* The "one display + one functional font" principle is unchanged — only the faces and the wiring changed. Combos live in [fonts.jsx](frontend/src/fonts.jsx); a dev-only `<FontPicker>` previews them and `ACTIVE_COMBO` sets the shipped default. EB Garamond is kept as a selectable combo. Fonts load via `FontProvider`, not a static `<link>` in [index.html](frontend/index.html).
- **2026-06-10** — *Warmth select uses anchored labels ("3 — moderate"), not bare numbers.* A 1-5 scale with no anchors invites inconsistent ratings; the anchor words are the same ones the tagging prompt uses, so human edits and AI inference share a rubric. Unrated shows as "— not rated" in the select and is simply omitted from the modal's metadata line (no "warmth ?/5" placeholder noise).
- **2026-06-10** — *Outfit feedback thumbs are `.chip` pills in the outfit header row, right-aligned opposite the heading.* Same signal as the email 👍/👎 (#41), so the UI reuses the chip vocabulary rather than inventing a rating control. One on-state for both thumbs (`--on-verdict`, strong ink — a verdict is a commitment, like Packed): the emoji carries polarity, the fill carries "recorded". Tapping the active thumb clears it — the web's advantage over the email link, which can only overwrite. The base `.chip` styles were promoted from ClothingCardGlass.css to styles.css in the same change (the `.ghost` precedent: second consumer = shared vocabulary). Thumbs render only on outfits with a `history_id` (skips have none to vote on).
- **2026-06-12** — *👎 attribution follow-up (#60) is an inline chip composer under the outfit header, not a modal.* The follow-up is strictly optional — a modal would make it feel mandatory and tax the verdict itself (volume is the whole game). It reuses the `.chip` vocabulary: item chips + three reason chips ("The combo" / "Weather call" / "Occasion"), where selecting items implies *specific items* and deselects the reason chips (one reason at most, enforced by interaction rather than validation copy). Selection uses a **soft** fill (`--on-attr`) deliberately distinct from `--on-verdict`'s strong ink: you're composing, not committing — Send is the commitment (same weight logic as laundry-soft vs packed-strong). A ghost Skip dismisses it for this verdict; re-tapping a thumb resets attribution and re-offers.
- **2026-06-05** — *Catalog has one mutually-exclusive view filter: `all · packed · laundry`.* "Packed" is the existing Travel-mode filter; "In laundry" (`!available`) is its mirror, giving laundry the same management view packed already had. Modeled as a single `view` state (not two booleans), so the views are mutually exclusive for free — you manage one slice at a time, which also sidesteps the near-always-empty packed∩laundry intersection. Each active view shows a contextual ghost **bulk reset** (*Unpack all* / *Clear laundry*) — rendered only when that view has items, guarded by a native `confirm`, applied as a client-side `Promise.all` of PATCHes (no bulk endpoint needed at personal scale). Per-item undo is just the card chip; the focused view makes it reachable without scrolling. Catalog's `view` is local page state, so this doesn't disturb the cross-page Travel-mode concept (see the 2026-06-04 placement entry).

- **2026-06-12** — *Lock button moved from the nav pill to the Profile page as a `.ghost` button.* Sign-out under an avatar chip is the universal pattern; it also declutters the nav for the primary four destinations. The `.nav__lock` class is replaced by `.nav__avatar` — a fixed `2rem × 2rem` round chip using the heading serif initial "B", wearing the **global button surface formula** (tint 0.50, blur 8px, ink-alpha border) — its first cut used a white border on the nav's own white glass and was nearly invisible; contrast in this system comes from ink-alpha borders, never new colors. Styled as a `NavLink` so the dark-filled active state is free; its selectors are scoped as `.nav .nav__avatar` because a bare `.nav__avatar` (0-1-0) loses to `.nav a` (0-1-1) — the same specificity trap as `button:hover` vs a bare `.chip` (see the chip entry). Profile is a full page (`.page-header` + `.form-page`), not a modal — two editable lists plus a location field don't fit a modal, and the issue expanded scope to include Home location after initial design discussion.
- **2026-06-12** — *Preference statements are rendered as `.profile__pref-tile` content tiles, not chips.* Chips are for short labels (the #60 reason chips, toggle states); preference statements are sentences — too long for a chip, too important to truncate. The tile surface reuses the `.outfit__item` glass formula (tint 0.45, blur 20px, radius 16px) so it reads as the same kind of "content unit." Inline edit swaps the tile content to input + Save/Cancel in place, following the #60 chip-composer precedent. Inferred prefs (source = 'inferred') carry a soft badge chip (`--on-attr` fill) labeling their evidence count; editing one promotes it to `source = 'user'` and moves it to the "Your aesthetic" section — the movement is the signal that the weekly job will never touch it again (#62 contract, enforced here; saving *unchanged* text on an inferred pref still PATCHes, so “Edit & own” always delivers the promotion it promises). Removing a user-written pref asks a native `confirm` (the Catalog bulk-reset precedent — hand-typed text is gone for good); dismissing an inferred one doesn't, since it's machine-made and tombstoned rather than lost.
- **2026-06-13** — *The "Learned from your feedback" heading carries a muted "Reviewed N days ago" heartbeat (#62), shown as relative time, not a date.* The weekly inference job stamps a last-success timestamp; surfacing it lets a stale value flag a broken/disabled job — staleness is the alarm, which catches even a silently-disabled cron that could never log its own failure. Relative time ("9 days ago") reads the missed-run faster than an absolute date for a weekly cadence; **days is the largest unit on purpose** — "last week"/"last month" are too vague for a health signal. Reuses the existing `.muted` token (no new color); the heading becomes a baseline-aligned `.profile__section-head` flex row that wraps on narrow phones. Only the inferred section gets it — it's the only job-driven list. The now-shipped job also retires the old empty-state copy ("appear once the weekly review job ships") for "No patterns learned yet" once a run has happened.
- **2026-06-26** — *Discrete-choice settings (select / segmented) auto-save on change; free-text and search settings keep an explicit Save button.* The Shopping department field (#82) is a native `<select>` that writes on `onChange` — a 4-option control doesn't earn the dirty-track + Save-button ceremony that the Home location combobox uses, and the rule now separates the two cleanly so the next discrete setting has a home instead of a coin-flip. It reuses the existing glass `select` styling (the warmth-select precedent) rather than inventing a segmented-control component (principle 5). The select is width-constrained (`min-width: 180px`, not the global `width: 100%`) to stay a "narrow input" (principle 3). Auto-save is **optimistic with rollback**: the control flips immediately, then reverts and surfaces a persistent `.error` line if the PUT fails — without rollback the control would silently disagree with the backend (it says "Men's", the row still says "Women's"). Success reuses the same `✓ Saved` `.profile__flash` as the location row, so confirmation/error vocabulary is shared across both save styles. Copy is framed as *retail section to search*, never gender identity, and "No preference" persists as the string `no_preference` (a null would be dropped by `PUT /profile` and read as "unchanged", not "neutral"). **Side effect, app-wide:** all `<select>`s now use a custom SVG chevron (`appearance: none`) instead of the native OS arrow — the native arrow hugs the right edge and *ignores `padding-right`*, so a custom chevron is the only way to control its inset, and it also retires an OS-default control the system already dislikes (cf. the 2026-06-05 native-checkbox→chip entry). This required switching the shared input rule from the `background` shorthand to `background-color` (the shorthand resets `background-image`, wiping the chevron). The warmth select inherits the chevron for free; the dev-only font picker keeps `appearance: auto`.
- **2026-06-12** — *Save confirmations are a lingering "✓ Saved" flash beside the action button, not a button-label swap.* Swapping the label ("Save" → "Saved" → "Save") jitters the button width and vanishes before it registers; the flash holds ~1.5s then fades (`.profile__flash`, remounted per save — the counter is the React key — so consecutive saves restart the animation). Paired rule: **API failures must surface as persistent `.error` lines.** The Profile page initially swallowed them, which read as "my preferences never saved / the list is empty" when the backend simply lacked the endpoints — silent failure is a design bug, not just a code bug.

- **2026-07-02** — *Multi-item upload (#24) is a page-header `.switch` ("Multi-item photo") on Add item, mounting a sibling form rather than adding a mode flag to `AddClothingForm`.* Placement follows the Travel-mode rule (page-level toggles live in `.page-header__actions`), but the control is a glass **switch**, not a native checkbox (2026-06-05: OS-default controls are off-vocabulary) and not a chip — chips label *states and verdicts*; a page-level mode is a *setting you flip*, and the sliding knob carries the on/off polarity better than fill weight alone. No new vocabulary leaks in: the track is the pill radius (999px), off is glass-ghost, on is strong ink — contrast from ink, never new color. Built as `<button role="switch" aria-checked>`; the base rule zeroes the global button glass-pill styles and is grouped with `.switch:hover` because `button:hover` (0-1-1) outranks a bare `.switch` (0-1-0) — the standing specificity trap. The Travel-mode checkboxes are now the leftover, tracked in #95. The switch label is short; the explanatory copy ("best for accessories", per-item crop note) lives as a muted hint under the file input. Each detected item renders as a `.multi-form__card` — the content-tile glass formula (tint 0.45 / blur 20 / radius 16, same as `.outfit__item` and `.profile__pref-tile`: a review card is a "content unit") with form-scale `14px` padding since it holds inputs, not metadata. Since #100 each card opens with its own `.multi-form__thumb` — a `96px` square crop of that item (radius 8, same as `.form__preview`) — replacing the earlier shared-photo-above-the-cards layout: the thumbnail *identifies* the card's item rather than being the subject, hence smaller than `.form__preview`, and it doubles as review-time verification that the crop caught the right item (a bad crop falls back to the full photo, which is self-evident on the card). Cards save/discard independently (card-local status + error, per the persistent-`.error` rule); saved cards collapse to a muted "✓ Saved — name" line instead of disappearing, so the running tally stays visible. "Done" (primary, exits to Catalog) renders **only once every card is saved or discarded** — the earlier ghost-while-cards-remain version was a footgun: mid-review it silently dropped unsaved suggestions and orphaned their uploads. A button whose click destroys work shouldn't exist at reduced weight; it should not exist until it's safe. Bailing mid-review is still possible via the nav.

## Maintaining this doc

- **Edit in the same commit as the code change.** Not in a follow-up commit — it'll never happen.
- **Document the non-obvious only.** If a reader could figure it out by reading the code, leave it out. Save lines for the *why*.
- **Re-read before adding a new component.** The Principles list is the checklist.
- **Replace stale entries.** If a decision reverses, edit the old entry in place. The log captures *current* truth, not historical revisions — git history has those.
