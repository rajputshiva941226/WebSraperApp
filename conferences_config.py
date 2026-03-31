"""
conferences_config.py
─────────────────────
Central registry mapping short conference codes → display names.

• CONFERENCES dict is the single source of truth for all hardcoded conferences.
• seed_conferences(app) is called once at startup (in app.py) to push the
  registry into the Conference DB table; safe to re-run (skips existing codes).
• Admin can create additional conferences at runtime via the admin panel —
  those live only in the DB and are NOT added back to CONFERENCES.
"""

from typing import Dict

# ── Master registry: code → full display name ──────────────────────────────
CONFERENCES: Dict[str, str] = {
    "NWC":    "Neurology World Conference",
    "DWC":    "Dementia World Conference",
    "AWC":    "Addiction World Conference",
    "PSYWC":  "Psychiatry World Conference",
    "GNC":    "Global Nursing Conference",
    "CGC":    "Cancer Global Conference",
    "PMC":    "Preventive Medicine Conference",
    "PDRC":   "Pharma Drug Research Conference",
    "INC":    "International Neurology Conference",
    "CWC":    "Cosmetology World Conference",
    "PHWC":   "Public Health World Conference",
    "PSWC":   "Plastic Surgery World Conference",
    "PMBC":   "Plant and Molecular Biology Conference",
    "WNRC":   "World Nursing Research Conference",
    "CGTC":   "Cell & Gene Therapy Conference",
    "PHMC":   "Public Health & Midwifery Conference",
    "IDWC":   "Infectious Diseases World Conference",
    "VRDS":   "Vaccine Research & Development Summit",
    "DIAWC":  "Diabetes World Conference",
    "IOC":    "International Obesity Conference",
    "AGWC":   "Agriculture World Conference",
    "GYNWC":  "Gynecology World Conference",
    "WHGC":   "Women's Health Global Conference",
    "NEON":   "Neonatal Conference",
    "MHWC":   "Mental Health World Conference",
    "PEDWC":  "Pediatrics World Conference",
    "CARDWC": "Cardiology World Conference",
    "HDWC":   "Heart Diseases World Conference",
    "TMWC":   "Traditional Medicine World Conference",
    "NTGC":   "Natural Therapies Global Conference",
    "NANOWC": "Nanotechnology World Conference",
    "MSWC":   "Materials Science World Conference",
}


def seed_conferences(app) -> None:
    """
    Populate the Conference table from CONFERENCES registry.
    Skips codes that already exist — safe to call on every startup.

    Add to app.py after init_db(app):
        from conferences_config import seed_conferences
        with app.app_context():
            seed_conferences(app)
    """
    with app.app_context():
        from models import db, Conference
        added = 0
        for code, display_name in CONFERENCES.items():
            if not Conference.query.filter_by(code=code).first():
                db.session.add(Conference(
                    code=code,
                    display_name=display_name,
                    is_active=True,
                    created_by='system',
                ))
                added += 1
        if added:
            db.session.commit()
            print(f"[Conferences] Seeded {added} conference(s) into DB.")
        else:
            print("[Conferences] All conferences already present — nothing to seed.")


def get_all_active(app=None) -> Dict[str, str]:
    """
    Return {code: display_name} for all active conferences from the DB.
    Falls back to the static CONFERENCES dict if DB is unavailable.
    Used by the frontend dropdown builder.
    """
    try:
        from models import Conference
        rows = Conference.query.filter_by(is_active=True).order_by(Conference.display_name).all()
        return {r.code: r.display_name for r in rows}
    except Exception:
        return {k: v for k, v in CONFERENCES.items()}