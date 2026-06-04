# Deployment

This guide covers putting Kaggle Replays on the internet. Read the first section
carefully — there are two very different things you might mean by "deploy," and
only one of them can be a public website.

## Two kinds of "deploy"

1. **The public project site (safe, recommended).** A real public website at a
   domain like `https://kaggle-replays.com` that showcases the project — what it
   is, screenshots, and how to run it. This is the static page in `docs/`. Anyone
   can visit it. This is what "deploy to a public website" should mean here.

2. **The live application (local or private only).** The actual app authenticates
   to Kaggle **as you**, using your saved browser session (`auth.json`), and its
   dev login signs every visitor in as the single owner — there is no multi-user
   Kaggle login (Kaggle has no OAuth for the internal API this app uses). So the
   running app **must not** be exposed as an open public service: doing so would
   put your Kaggle credentials on a server, let any visitor act as you, and very
   likely get your Kaggle account rate-limited or banned for server-side scraping.
   Run it locally (see the main `README.md`), or do a locked-down private deploy
   for yourself only (Part 2 below).

---

## Part 1 — Publish the public site (the `docs/` showcase)

Pick one host. All three serve the static `docs/` folder; none require a build.

### Option A: GitHub Pages (uses the workflow in this repo)

A workflow at `.github/workflows/pages.yml` publishes `docs/` on every push to
`main`.

1. Merge this to `main`.
2. In the repository: **Settings -> Pages -> Build and deployment -> Source ->
   GitHub Actions**.
3. The workflow runs and your site goes live at
   `https://AsutoshaNanda.github.io/kaggle-replays/`.

To use your own domain (for example `kaggle-replays.com`):

1. Buy the domain from any registrar (Namecheap, Cloudflare, Google Domains
   successor, etc.) — roughly 10-15 USD per year. (See the trademark note below.)
2. In the repository: **Settings -> Pages -> Custom domain**, enter your domain,
   and Save. GitHub commits a `CNAME` file for you.
3. At your registrar, add DNS records:
   - **Apex domain** (`kaggle-replays.com`) — four `A` records:
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
     (optionally the matching `AAAA` records: `2606:50c0:8000::153`,
     `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`).
   - **`www` subdomain** — a `CNAME` record pointing to `AsutoshaNanda.github.io`.
4. Wait for the DNS check to pass, then tick **Enforce HTTPS**.

### Option B: Netlify (uses `netlify.toml` in this repo)

1. Create a Netlify account and "Add new site -> Import an existing project",
   then pick this GitHub repo. `netlify.toml` already sets the publish directory
   to `docs/`, so no build configuration is needed.
2. Add your custom domain under **Domain management**. Either delegate DNS to
   Netlify (change your registrar's nameservers to Netlify's) or add the records
   Netlify shows you at your existing registrar. HTTPS is provisioned
   automatically.

### Option C: Vercel

1. Create a Vercel account and "Add New -> Project", import this repo.
2. Framework preset: **Other**. Set the **Output Directory** to `docs` and leave
   the build command empty (it is a static folder).
3. Add your domain under the project's **Domains** tab and update DNS as Vercel
   instructs. HTTPS is automatic.

---

## Part 2 — Run the full application privately (advanced, for yourself only)

This is for using the real app from anywhere, reachable only by you — not a
public service. You accept the trade-offs: hosting cost, a heavyweight runtime
(a headless Chromium per the Playwright session), and the requirement to keep it
access-controlled so it never serves strangers (which would risk your Kaggle
account).

High-level shape:

- Containerize the backend: a Python image with the Playwright Chromium
  dependencies installed, running `uvicorn backend.main:app`, plus a MySQL
  service. Build the frontend (`npm run build`) and serve the static `dist/`
  behind the same domain, with `VITE_API_BASE_URL` pointing at the backend.
- Provide secrets as deploy-time secrets (never baked into the image): the
  database URL, `JWT_SECRET`, `JWT_REFRESH_SECRET`, and your `auth.json` mounted
  into the backend's session directory.
- Restrict access: put the whole thing behind authentication (a reverse-proxy
  basic-auth or an allowlist), keep `DEV_LOGIN_ENABLED` off in any shared
  context, and do not link it publicly.
- Host on a small VPS (Docker + Docker Compose) or a platform such as Render or
  Railway that supports a long-running container and a managed MySQL.

This repo does not yet include the Dockerfile/compose for this. If you want it,
ask and it can be generated (Dockerfile, `docker-compose.yml`, and a step-by-step
guide for a VPS or Render), tailored to the host you choose.

---

## Trademark note

"Kaggle" is a trademark of Kaggle/Google. A public site at a `kaggle-*` domain,
especially one built around Kaggle's internal API, could draw a trademark or
terms-of-service complaint. A non-"kaggle" name (for example `replayarena`,
`simreplays`, `episodelab`) avoids that risk. This is your decision.

## What is automated vs. what you do

- Automated by this repo: building the site content (`docs/`), the GitHub Pages
  deploy workflow, and the Netlify config.
- Your steps (they require your accounts and cannot be done for you): buying the
  domain, enabling Pages or connecting Netlify/Vercel, and adding the DNS records.
