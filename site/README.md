# JVT Technologies Website

This is the local-first website project for the outward-facing `JVT Technologies` brand.

## Purpose

- present the company clearly
- position the private document assistant as the first flagship solution under the broader JVT umbrella
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

## Notes

- the public contact email is currently routed through Cloudflare Email Routing to a human inbox
- no fake testimonials, logos, or case studies are included
- the site is static, but the active deployment target is Cloudflare Pages
- values that still need replacing are listed in `launch-values.example.env`
