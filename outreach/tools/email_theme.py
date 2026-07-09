#!/usr/bin/env python3

from __future__ import annotations

import html


DEFAULT_SITE_URL = "https://jvt-technologies.com"
DEFAULT_REPLY_TO = "hello@jvt-technologies.com"


def text_to_email_blocks(text: str) -> str:
    blocks: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        if not list_items:
            return
        blocks.append(
            '<ul style="margin:0 0 18px 22px;padding:0;color:#f8f3ea;font-size:16px;line-height:1.7;">'
            + "".join(list_items)
            + "</ul>"
        )
        list_items.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_list()
            continue
        if stripped.startswith("- "):
            list_items.append(
                f'<li style="margin:0 0 6px;color:#f8f3ea;">{html.escape(stripped[2:])}</li>'
            )
            continue
        flush_list()
        blocks.append(
            f'<p class="jvt-text" style="margin:0 0 18px;color:#f8f3ea;font-size:16px;line-height:1.72;">{html.escape(stripped)}</p>'
        )

    flush_list()
    return "\n".join(blocks)


def render_text_email_html(
    text: str,
    *,
    title: str,
    preheader: str = "",
    site_url: str = DEFAULT_SITE_URL,
    reply_to_email: str = DEFAULT_REPLY_TO,
) -> str:
    safe_title = html.escape(title.strip() or "JVT Technologies")
    safe_preheader = html.escape(preheader.strip() or "A short JVT Technologies note.")
    safe_site_url = html.escape(site_url.strip() or DEFAULT_SITE_URL, quote=True)
    safe_reply_to = html.escape(reply_to_email.strip() or DEFAULT_REPLY_TO, quote=True)
    body_blocks = text_to_email_blocks(text)

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="color-scheme" content="light only" />
    <meta name="supported-color-schemes" content="light only" />
    <style>
      :root {{
        color-scheme: light only;
        supported-color-schemes: light;
      }}
      body,
      table,
      td,
      p,
      a {{
        -webkit-text-size-adjust: 100%;
      }}
      .jvt-body,
      .jvt-bg {{
        background-color: #071512 !important;
        color: #f8f3ea !important;
      }}
      .jvt-card,
      .jvt-panel {{
        background-color: #0b1d19 !important;
        color: #f8f3ea !important;
      }}
      .jvt-hero,
      .jvt-callout,
      .jvt-footer {{
        background-color: #071512 !important;
        color: #f8f3ea !important;
      }}
      .jvt-text,
      .jvt-strong {{
        color: #f8f3ea !important;
      }}
      .jvt-muted {{
        color: #cbbfaa !important;
      }}
      .jvt-gold {{
        color: #dcbf8a !important;
      }}
      .jvt-link {{
        color: #85f0d7 !important;
      }}
      .jvt-cta {{
        background-color: #15a08e !important;
      }}
      .jvt-cta-link {{
        color: #ffffff !important;
      }}
      @media (prefers-color-scheme: dark) {{
        .jvt-body,
        .jvt-bg,
        .jvt-hero,
        .jvt-callout,
        .jvt-footer {{
          background-color: #071512 !important;
          color: #f8f3ea !important;
        }}
        .jvt-card,
        .jvt-panel {{
          background-color: #0b1d19 !important;
          color: #f8f3ea !important;
        }}
        .jvt-text,
        .jvt-strong {{
          color: #f8f3ea !important;
        }}
        .jvt-muted {{
          color: #cbbfaa !important;
        }}
        .jvt-gold {{
          color: #dcbf8a !important;
        }}
        .jvt-link {{
          color: #85f0d7 !important;
        }}
        .jvt-cta {{
          background-color: #15a08e !important;
        }}
      }}
      a[x-apple-data-detectors] {{
        color: inherit !important;
        text-decoration: none !important;
      }}
    </style>
  </head>
  <body class="jvt-body" style="margin:0;padding:0;background-color:#071512;color:#f8f3ea;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">
      {safe_preheader}
    </div>
    <table class="jvt-bg" role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#071512" style="width:100%;background-color:#071512;background-image:radial-gradient(circle at 10% 0%, rgba(21,160,142,0.28), transparent 280px),radial-gradient(circle at 88% 10%, rgba(91,140,255,0.24), transparent 260px),radial-gradient(circle at 92% 100%, rgba(220,191,138,0.16), transparent 260px),linear-gradient(180deg,#071512 0%,#090b12 48%,#0b1d19 100%);padding:32px 14px;color:#f8f3ea;">
      <tr>
        <td align="center">
          <table class="jvt-card" role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#0b1d19" style="max-width:660px;width:100%;background-color:#0b1d19;border:1px solid rgba(248,243,234,0.16);border-radius:26px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,0.28);color:#f8f3ea;">
            <tr>
              <td class="jvt-hero" bgcolor="#071512" style="background-color:#071512;background-image:linear-gradient(135deg,#071512 0%,#0d302a 48%,#111625 100%);padding:24px 26px 22px;border-bottom:1px solid rgba(248,243,234,0.12);">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td width="58" valign="middle" style="width:58px;padding-right:14px;">
                      <img src="{safe_site_url}/logo-mark-email.png" width="52" height="52" alt="JVT" style="display:block;width:52px;height:52px;border:0;border-radius:14px;" />
                    </td>
                    <td valign="middle">
                      <p class="jvt-text" style="margin:0;color:#f8f3ea;font-size:22px;line-height:1.12;font-weight:800;letter-spacing:-0.02em;">JVT Technologies LLC</p>
                      <p class="jvt-gold" style="margin:6px 0 0;color:#dcbf8a;font-size:11px;line-height:1.4;letter-spacing:0.18em;text-transform:uppercase;font-weight:700;">AI ops for real workflow mess</p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="jvt-panel" bgcolor="#0b1d19" style="background-color:#0b1d19;padding:28px 28px 8px;color:#f8f3ea;">
                <table class="jvt-callout" role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#071512" style="width:100%;background-color:#071512;border:1px solid rgba(248,243,234,0.13);border-radius:20px;margin:0 0 22px;">
                  <tr>
                    <td style="padding:20px 20px 18px;">
                      <p class="jvt-gold" style="margin:0 0 8px;color:#dcbf8a;font-size:11px;line-height:1.4;letter-spacing:0.18em;text-transform:uppercase;font-weight:800;">JVT Technologies</p>
                      <p class="jvt-text" style="margin:0;color:#f8f3ea;font-size:22px;line-height:1.22;font-weight:800;letter-spacing:-0.03em;">{safe_title}</p>
                    </td>
                  </tr>
                </table>
                {body_blocks}
              </td>
            </tr>
            <tr>
              <td class="jvt-panel" bgcolor="#0b1d19" style="background-color:#0b1d19;padding:0 28px 28px;color:#f8f3ea;">
                <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 0 22px;">
                  <tr>
                    <td class="jvt-cta" bgcolor="#15a08e" style="background-color:#15a08e;background-image:linear-gradient(135deg,#5b8cff 0%,#15a08e 56%,#85f0d7 100%);border-radius:999px;">
                      <a class="jvt-cta-link" href="mailto:{safe_reply_to}" style="display:inline-block;padding:12px 18px;color:#ffffff;text-decoration:none;font-size:14px;line-height:1;font-weight:800;">Reply to JVT</a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="jvt-footer" bgcolor="#071512" style="background-color:#071512;padding:18px 28px 20px;border-top:1px solid rgba(248,243,234,0.12);">
                <p class="jvt-gold" style="margin:0 0 6px;color:#dcbf8a;font-size:12px;line-height:1.6;font-weight:700;">JVT Technologies LLC</p>
                <p class="jvt-muted" style="margin:0;color:#9fb2ad;font-size:12px;line-height:1.7;">
                  Human-reviewed outreach · AI ops for real workflow mess ·
                  <a class="jvt-link" href="{safe_site_url}" style="color:#85f0d7;text-decoration:none;">{safe_site_url}</a> ·
                  <a class="jvt-link" href="mailto:{safe_reply_to}" style="color:#85f0d7;text-decoration:none;">{safe_reply_to}</a>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
