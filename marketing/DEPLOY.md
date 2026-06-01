# Deploy the MoveDefense landing page (~60 seconds)

The page is a single static file: `marketing/index.html`. No build step. Pick one host.

---

## Swap these placeholders first
- `TODO_GOOGLE_SEARCH_CONSOLE_TOKEN` -> your Google Search Console verification token in `index.html` and `privacy.html`.
- `window.MoveDefenseMarketingConfig.analyticsProvider` -> set to `ga4`, `plausible`, `umami`, or keep `none`.
- `ga4MeasurementId`, `plausibleDomain`, or `umamiWebsiteId` -> fill only for the provider you use.
- `https://movedefense.com/` -> your real domain in canonical, OG, `robots.txt`, and `sitemap.xml`.
- `https://movedefense.com/og-image.png` -> add a real 1200x630 social preview image
  named `og-image.png` in the `marketing/` folder (or update the path)

The public marketing site now has first-party attribution, consent categories, and pilot/contact forms. Do not copy `marketing/js/marketing-privacy.js` into the authenticated app templates.

---

## Option A — Netlify Drop (fastest, free, no account math)
1. Go to **app.netlify.com/drop**
2. Drag the entire `marketing/` folder onto the page.
3. Live instantly at a `*.netlify.app` URL. Add your custom domain in Site settings → Domain.

## Option B — Vercel
1. `npm i -g vercel` (or use the web UI / GitHub import).
2. From `marketing/`: `vercel` → follow prompts. Custom domain in dashboard.

## Option C — Cloudflare Pages
1. dash.cloudflare.com → Workers & Pages → Create → Pages → Upload assets.
2. Upload `marketing/`. Free, fast global CDN, easy custom domain.

## Option D — Render static site (you already use Render)
Add to `render.yaml` (or new service in dashboard):
```yaml
  - type: web
    name: movedefense-marketing
    runtime: static
    staticPublishPath: ./marketing
    routes:
      - type: rewrite
        source: /*
        destination: /index.html
```
Keeps marketing + app under one Render account.

---

## Domain split (SEO-correct)
- **Root domain** `movedefense.com` → the **marketing page** (this file).
- **Subdomain** `app.movedefense.com` → the **Flask app** (login/operator portal).
- Keep app dashboards, driver logs, demo data, API routes, internal logs, and customer data out of the marketing analytics scope.

## Right after it's live
1. Add `og-image.png` (1200x630) so social shares render.
2. Verify the domain in **Google Search Console**, then submit `https://movedefense.com/sitemap.xml`.
3. Choose one analytics provider. Analytics runs by default unless a visitor turns it off in Cookie preferences.
4. Leave marketing consent off by default. Do not add ad pixels or remarketing tags unless the consent gate is updated intentionally.
5. Tell me the live URL -> I run `/seo page <url>` + `/seo schema <url>` to score it.
