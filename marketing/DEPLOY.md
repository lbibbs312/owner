# Deploy the MoveDefense landing page (~60 seconds)

The page is a single static file: `marketing/index.html`. No build step. Pick one host.

---

## ⚠️ Swap these placeholders FIRST (in `index.html`)
- `bibbstechnology@gmail.com` → your real demo/contact email (appears in the demo CTA + footer)
- `/login` → the real URL of the Flask app login (e.g. `https://app.movedefense.com/login`)
- `https://movedefense.com/` → your real domain (in `<link rel="canonical">`, OG tags)
- `https://movedefense.com/og-image.png` → add a real 1200×630 social preview image
  named `og-image.png` in the `marketing/` folder (or update the path)

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
- Point the "Operator login" link + the app's external links accordingly.

## Right after it's live
1. Add `og-image.png` (1200×630) so social shares render.
2. Verify the domain in **Google Search Console**, submit the URL.
3. Tell me the live URL → I run `/seo page <url>` + `/seo schema <url>` to score it.
4. Add a `sitemap.xml` + `robots.txt` (I can generate via `/seo sitemap`).
