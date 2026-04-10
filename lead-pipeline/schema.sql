CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_name TEXT NOT NULL,
  website TEXT,
  city_state TEXT,
  industry TEXT,
  practice_area TEXT,
  contact_page TEXT,
  public_email TEXT,
  notes TEXT,
  fit_score INTEGER DEFAULT 0,
  outreach_status TEXT DEFAULT 'new',
  follow_up_status TEXT DEFAULT 'none',
  last_touched_date TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_company_website
  ON leads(company_name, website);

CREATE TABLE IF NOT EXISTS outreach_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  event_note TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);
