# Syndra: landing page

Static site for `syndradata.com`. No build step, no runtime network calls.

> Syndra is API-first: there is no application GUI, and that is a product decision. This directory is the marketing surface that explains the product and routes visitors to `/docs` and the demo. (An earlier README here described a planned reading app that was never built and is not on the roadmap.)

```
frontend/
├── index.html      # the page (semantic landmarks, inline SVG only)
├── tokens.css      # THE palette: the only file containing colour values
├── styles.css      # layout + components, referencing tokens by role
├── main.js         # language switch, metric count-up, form validation, mobile menu
├── favicon.svg     # node-graph mark, transparent, restyles for dark UI
├── og-card.png     # 1200×630 social preview
└── fonts/          # self-hosted .woff2: NOT yet present, see below
```

## Deploy

Copy the folder to the VPS and let Caddy serve it:

```
scp -r frontend/* syndra@<host>:/srv/syndra-landing/
```

`/etc/caddy/Caddyfile`:

```caddy
syndradata.com, www.syndradata.com {
    root * /srv/syndra-landing
    encode zstd gzip
    file_server

    # Public OpenAPI docs and the API live on the app container.
    reverse_proxy /docs*    localhost:8000
    reverse_proxy /openapi* localhost:8000
    reverse_proxy /api/*    localhost:8000

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options    "nosniff"
        Referrer-Policy           "strict-origin-when-cross-origin"
        # The page makes no external requests. Keep it that way.
        Content-Security-Policy   "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; base-uri 'none'; frame-ancestors 'none'"
    }
    header /fonts/* Cache-Control "public, max-age=31536000, immutable"
}
```

Then `sudo caddy reload --config /etc/caddy/Caddyfile`.

## Fonts

**Already present** in `frontend/fonts/`: 75 KB total, latin subset, IBM Plex under OFL-1.1:

```
IBMPlexSans-Variable.woff2   45,712 B   variable, covers weights 400-600
IBMPlexMono-Regular.woff2    14,708 B   static 400
IBMPlexMono-Medium.woff2     14,888 B   static 500
```

The latin subset covers English and Spanish in full, accents and inverted punctuation
included, so `latin-ext` is not needed here.

Plex Sans is a variable font: one file serves the whole 400-600 range and is declared
with a weight *range* in a single `@font-face`. Do not split it back into three static
faces: they would all point at the same file and the browser would fetch those 45 KB
three times. Mono genuinely ships as static instances, hence two faces.

Nothing is ever fetched from a font CDN. If the files are removed the page falls back
to the system UI font and system monospace: it degrades, it does not break.

## Swapping the metric figures

The four figures live in one block in `index.html`, marked
`<!-- Swap these four figures after re-running the counts -->`. Each is written twice:
as the visible text (what a JS-disabled visitor and a crawler see) and as
`data-count` / `data-suffix` (what the count-up animates to). **Change both.**

```bash
ssh syndra@<host>
cd ~/syndra-deploy
docker compose exec -T postgres psql -U syndra_user -d syndra_db \
  -c "SELECT count(*) AS raw FROM raw_articles;" \
  -c "SELECT count(*) AS enriched FROM articles;" \
  -c "SELECT count(*) AS pending FROM raw_articles WHERE ingestion_state='pending';"
```

Never publish a figure you have not just measured.

## Brand

Colour is defined once, in [`tokens.css`](./tokens.css). That file is the single
source of truth and the hex values are deliberately not repeated here. Read it before
changing anything visual. Three rules it encodes:

- **The identity is achromatic.** Six neutrals: cream, sand, ink, mid grey, near-black,
  white, and no accent hue. Emphasis comes from contrast, weight, scale and the node
  motif. Adding a seventh chromatic colour is a change to the identity, not a tweak.
- **`--sand` is a surface.** Fills and borders only, never text at any size.
- **Sentiment is the one exception, and it is data, not brand.** Green / grey / red: the
  finance convention, chosen knowingly over a blue↔red scale. It appears only where
  sentiment data is shown, and never as colour alone.

  **The green is light on purpose, and that is the mitigation.** Red/green is the classic
  colour-vision failure, so the poles are separated by *lightness* rather than hue: the
  channel colour-blind viewers keep. The green sits at OKLCH L 0.702 against the red's
  0.548. Darkening it collapses the pair: a mid-green measures ΔE 3.9 against the red under
  deuteranopia, inside the failure band. **Do not make the green more "serious".** The light
  and dark steps differ for the same reason: reusing the light green on the dark surface
  drops it to ΔE 5.5. Re-validate before committing any change to these six values.

  The green buys its lightness at 2.16:1 against the cream, under the 3:1 mark, and the
  label is what makes that legal. Here the colour is applied to the word `"positive"`
  itself, so the two cannot come apart. Any future component showing the swatch without a
  label is broken.

**Colour does not distinguish links.** The gold is a fill; links are ink, so they carry the
gold text step and underline on hover. Buttons are filled, focus rings are visible shapes.
Those affordances are load-bearing here in a way they would not be on a page whose accent
could safely carry text.

Dark mode is a *selected* palette, not an inversion. The cream becomes the ink and the
emphasis role inverts with it. Both schemes are declared under `prefers-color-scheme` and
under `[data-theme]`, so a manual switch can be added later without touching component CSS.

The node-graph geometry from the wordmark is the structural motif: the logo, the
section kickers, the hero constellation, and the joints in the pipeline diagram are all
the same four-node figure. Reuse it instead of introducing new ornament.

## Notes

- **Language.** English is the default for every visitor, unconditionally. Spanish is
  opt-in via the EN/ES switch and only then remembered in `localStorage`. With JS
  disabled the page reads as English. Browser-locale auto-switching was removed
  deliberately: an `es-*` browser silently flipping the page meant the author never
  saw what a visitor actually gets.
- **Accessibility.** Semantic landmarks, skip link, visible focus rings, AA contrast in
  both schemes, `prefers-reduced-motion` respected (the count-up is skipped entirely).
- **The access form** posts via `mailto:` as a deliberate fallback. Point `action` at a
  self-hosted endpoint when one exists; do not introduce a third-party form service.
- **Syntax highlighting** in the code samples is static markup (`.tok-*` spans). There
  is no highlighter at runtime.
