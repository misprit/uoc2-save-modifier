"""B10: load the game's entity type database; validate whole save files."""
import sys, numpy, yaml, os, copy, collections, inspect
sys.path.append(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")
import importlib
from types import SimpleNamespace

PKG = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages"
OUT = r"D:\MiniMax\_analysis\extracted"
PKGS = ["base", "dlc1", "dlc2", "dlc3", "dlc4", "dlc5", "dlc6", "dlc7", "dlc8", "dlc9", "dlc10"]

def load_dir_yml(pkg, sub):
    """Merge all *.yml under <pkg>/data/entity_types/<sub> into {stem: data}."""
    out = {}
    for p in PKGS:
        d = os.path.join(PKG, p, "data", "entity_types", sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".yml"):
                continue
            fp = os.path.join(d, f)
            try:
                raw = yaml.safe_load(open(fp, encoding="utf-8").read())
            except Exception:
                continue
            if raw is None:
                continue
            if isinstance(raw, dict):
                out[f[:-4]] = raw
    return out

def load_single_yml(pkg, name):
    for p in PKGS:
        fp = os.path.join(PKG, p, "data", "entity_types", name)
        if os.path.isfile(fp):
            return yaml.safe_load(open(fp, encoding="utf-8").read())
    return None

print("=" * 80)
print("A) entity type subdirs")
print("=" * 80)
base_et = os.path.join(PKG, "base", "data", "entity_types")
for sub in sorted(os.listdir(base_et)):
    p = os.path.join(base_et, sub)
    if os.path.isdir(p):
        print(f"  {sub}/ ({len(os.listdir(p))} files)")

unit_types = load_dir_yml(None, "unit_types")
hq_types = load_dir_yml(None, "hq_types")
specialists = load_dir_yml(None, "specialists")
cards = load_dir_yml(None, "cards")
factions = load_single_yml(None, "factions.yml")
nationalities = load_single_yml(None, "nationalities.yml")
card_meta = load_single_yml(None, "card_meta_types.yml")
print(f"\n  loaded: unit_types={len(unit_types)} hq_types={len(hq_types)} "
      f"specialists={len(specialists)} cards={len(cards)}")
print(f"  nationalities keys: {list(nationalities)[:12] if isinstance(nationalities, dict) else type(nationalities)}")
print(f"  factions keys: {list(factions) if isinstance(factions, dict) else type(factions)}")
print(f"  card_meta type: {type(card_meta).__name__} len={len(card_meta) if hasattr(card_meta,'__len__') else '-'}")

print("\n  sample unit_type (us_inf_42):")
print("   ", unit_types.get("us_inf_42"))
print("\n  sample hq_type (uk_hq_mid_hard):")
print("   ", hq_types.get("uk_hq_mid_hard"))
print("\n  sample specialist:", list(specialists.items())[:2])
print("\n  sample card:", list(cards.items())[:1])

print()
print("=" * 80)
print("B) max_st / max_spec distributions (step & specialist caps)")
print("=" * 80)
ms = collections.Counter(v.get("max_st") for v in unit_types.values() if isinstance(v, dict))
mx = collections.Counter(v.get("max_spec") for v in unit_types.values() if isinstance(v, dict))
print("  max_st histogram:", dict(sorted(ms.items(), key=lambda x: (x[0] is None, x[0]))))
print("  max_spec histogram:", dict(sorted(mx.items(), key=lambda x: (x[0] is None, x[0]))))
no_st = [k for k, v in unit_types.items() if isinstance(v, dict) and v.get("max_st") is None]
print(f"  unit types without max_st: {len(no_st)} e.g. {no_st[:5]}")
by_fac = collections.Counter(v.get("faction") for v in unit_types.values() if isinstance(v, dict))
print("  faction histogram:", dict(by_fac))

print()
print("=" * 80)
print("C) validate REAL save files against the game's validators")
print("=" * 80)
cam = importlib.import_module("uoc2.state.campaign.campaign_data_validation")
um = importlib.import_module("uoc2.state.entities.data_validation.unit")
hm = importlib.import_module("uoc2.state.entities.data_validation.hq")
cm = importlib.import_module("uoc2.state.entities.data_validation.card")

ctx = SimpleNamespace(
    unit_types=unit_types, hq_types=hq_types, card_types=cards,
    specialist_types=specialists, nationality_types=nationalities,
    faction_types=factions, general_types=None,
)
def load(p):
    return yaml.safe_load(open(p, "r", encoding="utf-8").read())

def V(label, fn, data):
    try:
        r = fn(data)
        print(f"   PASS  {label}")
        return r
    except Exception as e:
        print(f"   FAIL  {label}\n         {type(e).__name__}: {str(e)[:400]}".replace("\n", " "))
        return None

base = os.path.join(OUT, "conf3")
print("\n-- conf3 --")
V("root units.yml  -> campaign_units_schema", lambda d: cam.campaign_units_schema(d, ctx),
  load(os.path.join(base, "units.yml")))
V("root hqs.yml    -> campaign_hqs_schema", lambda d: cam.campaign_hqs_schema(d, ctx),
  load(os.path.join(base, "hqs.yml")))
V("root cards.yml  -> cards_schema", lambda d: cm.cards_schema(d, ctx),
  load(os.path.join(base, "cards.yml")))
V("root store.yml  -> campaign_store_schema", lambda d: cam.campaign_store_schema(d, ctx),
  load(os.path.join(base, "store.yml")))
V("root main.yml   -> campaign_schema", lambda d: cam.campaign_schema(d, ctx),
  load(os.path.join(base, "main.yml")))
V("document/units.yml -> doc_units_schema", lambda d: cam.doc_units_schema(d, ctx),
  load(os.path.join(base, "document", "units.yml")))
V("document/hqs.yml   -> doc_hqs_schema", lambda d: cam.doc_hqs_schema(d, ctx),
  load(os.path.join(base, "document", "hqs.yml")))
g = os.path.join(base, "games", "avalanche")
V("games/<x>/units.yml -> units_schema(from_scenario_data)", lambda d: um.units_schema(d, False, ctx),
  load(os.path.join(g, "units.yml")))
V("games/<x>/hqs.yml   -> hqs_schema(from_scenario_data)", lambda d: hm.hqs_schema(d, False, ctx),
  load(os.path.join(g, "hqs.yml")))
