import os
try:
    import yaml
except Exception:
    yaml = None

# Regions de base
region_table = {
    "Menu": ["Seyda Neen"],
    "Seyda Neen": ["Balmora"],
    "Balmora": ["Ald'ruhn", "Vivec"],
    "Ald'ruhn": [],
    "Vivec": ["Sadrith Mora"],
    "Sadrith Mora": ["Dagoth Ur"],
    "Dagoth Ur": [],
}
