import os, shutil, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(ROOT, 'apworld')
NAME = 'morrowind_openmw.apworld'

# Synchronizes data from data/ to apworld/morrowind_openmw/data/
data_src = os.path.join(ROOT, 'data')
data_dst = os.path.join(src, 'morrowind_openmw', 'data')
os.makedirs(data_dst, exist_ok=True)
for name in ('quest_items.yaml', 'quest_locks.yaml', 'quest_completions.yaml', 'quest_finals.yaml', 'locations.yaml', 'items.yaml'):
    s = os.path.join(data_src, name)
    if os.path.exists(s):
        shutil.copy2(s, os.path.join(data_dst, name))

# Builds the apworld (once) in apworld/
built = os.path.join(src, NAME)
with zipfile.ZipFile(built, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(src):
        for f in files:
            if f.endswith('.apworld') or f.endswith('.pyc'):
                continue
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, src))

# Directories where Archipelago can load an apworld. We REPLACE all existing
# copies (a stale copy masks the new one: missing options in the Launcher);
# if there are none, we install into worlds/.
bases = []
if os.environ.get('ARCHIPELAGO_DIR'):
    bases.append(os.path.expanduser(os.environ['ARCHIPELAGO_DIR']))
bases.append(os.path.expanduser('~/.local/share/Archipelago'))
if len(sys.argv) > 1:
    bases.insert(0, os.path.expanduser(sys.argv[1]))

targets = []
for b in bases:
    for sub in ('custom_worlds', 'worlds'):
        t = os.path.join(b, sub, NAME)
        if os.path.exists(t) and t not in targets:
            targets.append(t)
    # possible non-zipped directory
    d = os.path.join(b, 'worlds', 'morrowind_openmw')
    if os.path.isdir(d):
        print('WARNING: non-zipped directory', d, '-> remove it (it masks the apworld)')
if not targets:
    t = os.path.join(bases[0], 'worlds', NAME)
    os.makedirs(os.path.dirname(t), exist_ok=True)
    targets.append(t)

for t in targets:
    shutil.copy2(built, t)
    print('installed:', t)
print('Restart the Archipelago Launcher to reload the options.')
