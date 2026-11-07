import os
try:
    import yaml
except Exception:
    yaml = None

# Base regions
region_table = {
    "Menu": ["Seyda Neen"],
    "Seyda Neen": ["Balmora"],
    "Balmora": ["Ald'ruhn", "Vivec"],
    "Ald'ruhn": [],
    "Vivec": ["Sadrith Mora"],
    "Sadrith Mora": ["Dagoth Ur"],
    "Dagoth Ur": [],
}
