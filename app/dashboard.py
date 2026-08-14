from datetime import datetime, timezone

SHOP_PHONE_DISPLAY = "+1 (659) 234-7944"
SHOP_PHONE_TEL = "+16592347944"  # tel: links need clean digits, no spaces/parens

_LANG_LABELS = {"en": "English", "hi": "Hindi"}


def _relative_time(updated_at: str) -> str:
    try:
        then = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return updated_at
    delta = datetime.now(timezone.utc) - then
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _escape(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _lead_row(lead: dict) -> str:
    name = _escape(lead.get("customer_name") or "Unnamed caller")
    phone = _escape(lead.get("phone_number") or "")
    requirement = _escape(lead.get("requirement_summary") or "Not specified")
    visit = _escape(lead.get("visit_preference") or "")
    lang = _LANG_LABELS.get(lead.get("language"), lead.get("language") or "—")
    when = _relative_time(lead.get("updated_at", ""))

    phone_html = f'<a href="tel:{phone}">{phone}</a>' if phone else '<span class="muted">—</span>'
    visit_html = f'<div class="visit">📅 {visit}</div>' if visit else ""

    return f"""
      <div class="lead-card">
        <div class="lead-top">
          <div class="lead-name">{name}</div>
          <span class="badge badge-{lead.get('language', 'en')}">{lang}</span>
        </div>
        <div class="lead-phone">{phone_html}</div>
        <div class="lead-requirement">{requirement}</div>
        {visit_html}
        <div class="lead-time">{when}</div>
      </div>
    """


def render_dashboard(all_leads: list) -> str:
    total = len(all_leads)
    hindi_count = sum(1 for lead in all_leads if lead.get("language") == "hi")
    english_count = sum(1 for lead in all_leads if lead.get("language") == "en")
    with_visit = sum(1 for lead in all_leads if lead.get("visit_preference"))

    if all_leads:
        rows_html = "\n".join(_lead_row(lead) for lead in all_leads)
        leads_section = f'<div class="lead-grid">{rows_html}</div>'
    else:
        leads_section = f"""
          <div class="empty-state">
            <div class="empty-icon">📞</div>
            <div class="empty-title">No leads yet</div>
            <div class="empty-subtitle">
              Call <a href="tel:{SHOP_PHONE_TEL}">{SHOP_PHONE_DISPLAY}</a> to try the agent live —
              captured leads will show up here automatically.
            </div>
          </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Metro Property Shop — Leads Dashboard</title>
<style>
  :root {{
    --bg: #0b0d12;
    --surface: #12151c;
    --surface-2: #191d27;
    --border: #262b38;
    --text: #eef0f4;
    --text-dim: #9aa1b2;
    --accent: #f0a94e;
    --accent-2: #5ec9a8;
    --en: #5b8ef2;
    --hi: #f0a94e;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: radial-gradient(circle at top left, #151a24 0%, var(--bg) 55%);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    min-height: 100vh;
    padding: 32px 20px 64px;
  }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  header {{ margin-bottom: 32px; }}
  .eyebrow {{
    color: var(--accent);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }}
  h1 {{ margin: 0 0 6px; font-size: 30px; font-weight: 700; letter-spacing: -0.02em; }}
  .subtitle {{ color: var(--text-dim); font-size: 15px; }}
  .subtitle a {{ color: var(--accent-2); text-decoration: none; }}
  .subtitle a:hover {{ text-decoration: underline; }}

  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin: 28px 0 36px;
  }}
  .stat {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
  }}
  .stat-value {{ font-size: 26px; font-weight: 700; }}
  .stat-label {{ color: var(--text-dim); font-size: 13px; margin-top: 4px; }}

  .lead-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }}
  .lead-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
    transition: border-color 0.15s ease, transform 0.15s ease;
  }}
  .lead-card:hover {{ border-color: #3a4152; transform: translateY(-1px); }}
  .lead-top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 8px;
  }}
  .lead-name {{ font-weight: 650; font-size: 16px; }}
  .badge {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    padding: 3px 9px;
    border-radius: 999px;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .badge-en {{ background: rgba(91,142,242,0.15); color: var(--en); }}
  .badge-hi {{ background: rgba(240,169,78,0.15); color: var(--hi); }}
  .lead-phone a {{ color: var(--accent-2); text-decoration: none; font-size: 14px; }}
  .lead-phone a:hover {{ text-decoration: underline; }}
  .lead-requirement {{ color: var(--text); font-size: 14px; margin-top: 10px; line-height: 1.5; }}
  .visit {{ color: var(--text-dim); font-size: 13px; margin-top: 8px; }}
  .lead-time {{ color: var(--text-dim); font-size: 12px; margin-top: 12px; }}
  .muted {{ color: var(--text-dim); }}

  .empty-state {{
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: 16px;
    padding: 56px 24px;
    text-align: center;
  }}
  .empty-icon {{ font-size: 36px; margin-bottom: 12px; }}
  .empty-title {{ font-size: 18px; font-weight: 650; margin-bottom: 8px; }}
  .empty-subtitle {{ color: var(--text-dim); font-size: 14px; }}
  .empty-subtitle a {{ color: var(--accent-2); text-decoration: none; }}
  .empty-subtitle a:hover {{ text-decoration: underline; }}

  footer {{
    margin-top: 48px;
    color: var(--text-dim);
    font-size: 12px;
    text-align: center;
  }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="eyebrow">Metro Property Shop</div>
      <h1>Leads Dashboard</h1>
      <div class="subtitle">Captured automatically from calls to <a href="tel:{SHOP_PHONE_TEL}">{SHOP_PHONE_DISPLAY}</a></div>
    </header>

    <div class="stats">
      <div class="stat"><div class="stat-value">{total}</div><div class="stat-label">Total leads</div></div>
      <div class="stat"><div class="stat-value">{with_visit}</div><div class="stat-label">Site visits requested</div></div>
      <div class="stat"><div class="stat-value">{english_count}</div><div class="stat-label">English calls</div></div>
      <div class="stat"><div class="stat-value">{hindi_count}</div><div class="stat-label">Hindi calls</div></div>
    </div>

    {leads_section}

    <footer>Bilingual AI voice agent · faster-whisper + Claude Haiku + edge-tts · <a href="/leads" style="color:var(--text-dim)">raw JSON</a></footer>
  </div>
</body>
</html>"""
