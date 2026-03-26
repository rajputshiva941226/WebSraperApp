"""
Conference Configuration
Maps short forms to full forms for storage and display
"""

CONFERENCE_MAPPINGS = {
    'NWC': 'Neurology World Conference',
    'DWC': 'Dementia World Conference',
    'AWC': 'Addiction World Conference',
    'PWC': 'Psychiatry World Conference',
    'GNC': 'Global Nursing Conference',
    'CGC': 'Cancer Global Conference',
    'PMC': 'Preventive Medicine Conference',
    'PDRC': 'Pharma Drug Research Conference',
    'INC': 'International Neurology Conference',
    'CWC': 'Cosmetology World Conference',
    'PHWC': 'Public Health World Conference',
    'PSWC': 'Plastic Surgery World Conference',
    'PMBC': 'Plant and Molecular Biology Conference',
    'WNRC': 'World Nursing Research Conference',
    'CGTC': 'Cell & Gene Therapy Conference',
    'PHMC': 'Public Health & Midwifery Conference',
    'IDWC': 'Infectious Diseases World Conference',
    'VRDС': 'Vaccine Research & Development Summit',
    'DWC2': 'Diabetes World Conference',
    'IOC': 'International Obesity Conference',
    'AGC': 'Agriculture World Conference',
    'GYC': 'Gynecology World Conference',
    'WHGC': 'Women\'s Health Global Conference',
    'NC': 'Neonatal Conference',
    'MHWC': 'Mental Health World Conference',
    'PEC': 'Pediatrics World Conference',
    'CWC2': 'Cardiology World Conference',
    'HDWC': 'Heart Diseases World Conference',
    'TMWC': 'Traditional Medicine World Conference',
    'NTGC': 'Natural Therapies Global Conference',
    'NTC': 'Nanotechnology World Conference',
    'MSC': 'Materials Science World Conference',
}

# Reverse mapping for quick lookup
SHORT_FORM_TO_FULL = CONFERENCE_MAPPINGS
FULL_FORM_TO_SHORT = {v: k for k, v in CONFERENCE_MAPPINGS.items()}


def get_short_form(full_form):
    """Get short form from full form"""
    return FULL_FORM_TO_SHORT.get(full_form, full_form)


def get_full_form(short_form):
    """Get full form from short form"""
    return SHORT_FORM_TO_FULL.get(short_form, short_form)


def get_all_conferences():
    """Get all conferences as list of dicts with short and full forms"""
    return [
        {
            'short_form': short,
            'full_form': full
        }
        for short, full in sorted(SHORT_FORM_TO_FULL.items())
    ]
