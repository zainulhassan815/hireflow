# Design

Written from the built result, not from intentions.

## World: Neutral Ink

Achromatic chrome, one ink, colour reserved for meaning. The interface is
greyscale from the page ground to the sidebar; the only saturated things on
screen are the logo, a document-type chip, and a status. When everything is
neutral, the one coloured thing is information.

This replaces the F90.b editorial system (Fraunces display, `--radius: 0`,
blue primary). Two reasons it went: a display serif over a resume table was
decoration rather than a decision, and a zero-radius surface reads as
unfinished rather than severe when the content is soft — chat bubbles,
uploaded PDFs, candidate cards.

## Colour

Neutrals are **chroma 0**. The incumbent's greys carried a blue cast
(0.028 chroma at hue 261) which is shadcn's default and reads as one.

**Primary is ink, not a hue.** `oklch(0.145 0 0)` in light, inverted to
`oklch(0.985 0 0)` in dark. A black button on white is the whole grammar of
this world; a coloured primary is the single change that would make it
generic again.

Strategy is **Restrained** — neutrals plus semantic accents. Correct for an
Operate surface, where expression must not compete with state.

Semantic (`success` / `warning` / `info` / `destructive`) and categorical
(`cat-1..5`, nominal, for document type and intent class) roles survive from
F90.c with chroma pulled down: against neutral chrome the old values shouted.

Dark ground is `oklch(0.145 0 0)`, deliberately not pure black — an OLED
black leaves no room to lift a card or draw a hairline.

## Radius

`--radius: 0.625rem` (10px). Past the 6–8px that reads as "default rounded",
short of the pill that makes dense data look like a toy.

F90.e had collapsed `--radius-2xl/3xl/4xl` to zero; restoring the
progression is what turned squircle on across the app, because components
already asked for `rounded-lg/xl/2xl` in 111 places. `4xl` is deliberately
*smaller* than `2xl` — buttons want a soft rectangle, not a capsule.

## Type

**Geist** for text and display, **Geist Mono** for filenames, ids and
figures. There is no second face: hierarchy comes from scale, weight and
tracking (`-0.02em` on headings), which is why `--font-display` resolves to
the same family. Fraunces and Inter-as-display are both training-data
defaults, and an Operate surface is well served by a workhorse UI face.

`font-variant-numeric: tabular-nums` and Geist's `cv11`/`ss01` are on
globally — counts, dates and scores must not change width as they update.

## Elevation

Hairline borders carry structure; shadows only lift what genuinely floats.
Four steps (`--elevation-xs` … `-lg`), each with an offset **and** a soft
blur. Dark mode raises opacity because a light shadow does not register on a
dark ground.

## Browser surfaces

Themed rather than left to the browser: text selection (inverted ink),
scrollbars (border-coloured thumb, transparent track, inset via
`background-clip`), focus ring (`--ring` = foreground), underline offset,
and the native date input's calendar indicator — including inverting it in
dark mode and muting an unset `dd/mm/yyyy` mask so an empty filter does not
look like a set one.

## Layout

The shell is a fixed sidebar plus a `h-dvh` scrolling content area with
`p-6`. A route opts out with `data-full-bleed`, which the shell reads via
`has-[[data-full-bleed]]` — chat needs the full height to pin its composer
to the bottom, every other page wants the padded frame.

Filters on the documents page are **collapsed behind a disclosure** with an
active-count badge. Left open they were taller than a phone's first
viewport, putting every document below the fold.

## Bans observed

No colour on the primary action. No `border-left` accent above 1px (one was
removed from the dashboard heading — a leftover from the editorial world).
No second display face. No gradient text. No zero-offset shadow halos.

## Not covered

Populated data views were not visually reviewed — the review account had an
empty library, so tables, candidate cards and the Kanban were verified by
token inheritance rather than by eye. Search, Jobs, Candidates and Settings
have had no per-page pass.
