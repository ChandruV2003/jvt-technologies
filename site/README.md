# JVT Technologies Website

This is the local-first website project for the outward-facing `JVT Technologies` brand.

## Purpose

- present the company clearly
- position the private document assistant as the first flagship solution under the broader JVT umbrella
- reflect the umbrella-company story without drifting into generic "we do all AI" language
- give a prospect a believable, modern landing experience
- support future domain deployment without changing the core copy
- keep contact and analytics values easy to swap once real accounts exist

## Local Preview

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site
python3 -m http.server 8080
```

Then open:

- `http://127.0.0.1:8080`

## Deployment

The live Cloudflare Pages project is:

- `jvt-technologies-site`

The current public domains are:

- `https://jvt-technologies.com`
- `https://www.jvt-technologies.com`

Deploy from this Mac with:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site
./deploy.sh
```

Current operational note:

- The normal deploy host is the M4 Mac mini at `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site`.
- Wrangler is expected on the M4 at `/opt/homebrew/bin/wrangler`.
- If the local edit mirror does not have `wrangler`, that only blocks local deploy from that shell; it does not mean the M4 lacks Wrangler.
- Raw SSH calls to Wrangler need `/opt/homebrew/bin` in PATH so Node can be found. `site/deploy.sh` already sets this.
- Recent deploy blocker is Cloudflare Pages API auth error `10000` for project `jvt-technologies-site`, not missing site files and not missing M4 Wrangler.
- For non-interactive deploys, create `site/.env.local` from `site/.env.local.example` with `CLOUDFLARE_ACCOUNT_ID` and a `CLOUDFLARE_API_TOKEN` that has Account / Cloudflare Pages / Edit access.

## Notes

- the public contact email is currently routed through Cloudflare Email Routing to a human inbox
- no fake testimonials, logos, or case studies are included
- the site now includes a real sample demo video and honest synthetic use-case examples
- the current public positioning is legal first, with adjacent document-heavy professional teams as the next expansion lane
- the site is static, but the active deployment target is Cloudflare Pages
- values that still need replacing are listed in `launch-values.example.env`
