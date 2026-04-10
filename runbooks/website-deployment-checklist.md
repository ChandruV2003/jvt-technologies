# Website Deployment Checklist

## Current Local Site

- source path: `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site`
- local preview command: `python3 -m http.server 8080`
- swap-value file: `../site/launch-values.example.env`
- deploy command: `./deploy.sh`
- active Cloudflare Pages project: `jvt-technologies-site`
- active public domains: `jvt-technologies.com`, `www.jvt-technologies.com`

## Values To Replace Before Going Public

- final public site URL
- contact email and mailto target
- booking/demo-request URL if used
- Open Graph image absolute URL
- analytics mode and script URL if used

## Recommended Launch Stack

- static hosting: Cloudflare Pages
- registrar: No-IP
- DNS + email routing: Cloudflare
- analytics: Plausible or Fathom if you want a privacy-aware option

## Launch Sequence

1. finalize the domain
2. configure the mailbox
3. replace the placeholder values in the site
4. preview locally one last time
5. deploy the static site with `./deploy.sh`
6. verify Pages custom domains and HTTPS
7. confirm the contact CTA reaches a human-reviewed path

## Final Checks

- mobile layout looks clean
- no placeholder domain or email remains
- Open Graph image resolves
- favicon and manifest load
- the contact path is real
