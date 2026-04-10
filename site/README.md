# JVT Technologies Website

This is the local-first website project for the outward-facing `JVT Technologies` brand.

## Purpose

- present the company clearly
- position the private document assistant offer
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

## Notes

- the contact email shown in the site is a placeholder until a real domain mailbox is configured
- no fake testimonials, logos, or case studies are included
- the site is static so it can later be deployed to Netlify, Cloudflare Pages, GitHub Pages, or a simple nginx host
- values that still need replacing are listed in `launch-values.example.env`
