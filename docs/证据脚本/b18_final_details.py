"""B18: final details -- campaign constants, per-table unit field sets."""
import os, yaml, json, collections

OUT = r"D:\MiniMax\_analysis\extracted"

def load(p):
    return yaml.safe_load(open(p, "r", encoding="utf-8").read())

base = os.path.join(OUT, "conf3")
dm = load(os.path.join(base, "document", "main.yml"))
print("=" * 80)
print("document/main.yml  (campaign constants, copied from the game package)")
print("=" * 80)
for k, v in dm.items():
    if k == "milestones":
        print(f"  {k}: <{len(v)} milestones>")
        for mid, m in v.items():
            print(f"      {mid:42s} do_not_take={m.get('do_not_take')} scenario={m.get('scenario_name')} objective={m.get('objective')}")
    elif isinstance(v, (dict, list)) and len(v) > 6:
        print(f"  {k}: <{len(v)} entries> {str(v)[:150]}")
    else:
        print(f"  {k}: {v!r}")

print()
print("=" * 80)
print("UNIT TABLE FIELD SETS (exact keys per layer)")
print("=" * 80)
root_u = load(os.path.join(base, "units.yml"))
print(f"  root units.yml            n={len(root_u):4d} keys={sorted(root_u[0])}")
doc_u = load(os.path.join(base, "document", "units.yml"))
print(f"  document/units.yml        n={len(doc_u):4d} keys={sorted(doc_u[0])}")
for g in ["avalanche", "tunis", "monte_cassino"]:
    p = os.path.join(base, "games", g, "units.yml")
    if os.path.isfile(p):
        u = load(p)
        print(f"  games/{g}/units.yml   n={len(u):4d} keys={sorted(u[0])}")
import zipfile
with zipfile.ZipFile(os.path.join(base, "games", "avalanche", "archive")) as az:
    names = sorted({n.split("/")[0] for n in az.namelist()})
    withcu = [n for n in names if f"{n}/campaign_units.yml" in az.namelist()]
    last = withcu[-1] if withcu else names[-1]
    cu = yaml.safe_load(az.read(f"{last}/campaign_units.yml").decode("utf-8"))
    print(f"  archive/{last}/campaign_units.yml n={len(cu):4d} keys={sorted(cu[0])}")
    try:
        en = yaml.safe_load(az.read(f"{last}/enroute_units.yml").decode("utf-8"))
    except KeyError:
        en = None
    if en:
        print(f"  archive/{last}/enroute_units.yml   n={len(en):4d} keys={sorted(en[0])}")
        print(f"      sample: {en[0]}")

print()
print("=" * 80)
print("HQ TABLE FIELD SETS")
print("=" * 80)
root_h = load(os.path.join(base, "hqs.yml"))
print(f"  root hqs.yml              n={len(root_h):4d} keys={sorted(root_h[0])}")
doc_h = load(os.path.join(base, "document", "hqs.yml"))
print(f"  document/hqs.yml          n={len(doc_h):4d} keys={sorted(doc_h[0])}")
gh = load(os.path.join(base, "games", "avalanche", "hqs.yml"))
print(f"  games/avalanche/hqs.yml   n={len(gh):4d} keys={sorted(gh[0])}")

print()
print("=" * 80)
print("ROOT main.yml FULL (conf3) + key set")
print("=" * 80)
rm = load(os.path.join(base, "main.yml"))
print(f"  keys: {sorted(rm)}")
print(f"  in_state keys: {sorted(rm['in_state'])}")
print(f"  in_state.fronts[france] keys: {sorted(rm['in_state']['fronts']['france'])}")
print(f"  in_state.fronts[italy]  keys: {sorted(rm['in_state']['fronts']['italy'])}")

print()
print("=" * 80)
print("STORE / CARD structures")
print("=" * 80)
st = load(os.path.join(base, "store.yml"))
for front, v in st.items():
    print(f"  store[{front}]: keys={sorted(v)}  n_store={len(v.get('store') or [])}")
    for item in (v.get("store") or [])[:4]:
        print(f"      {item}")
cd = load(os.path.join(base, "cards.yml"))
print(f"  cards.yml: {cd}")
print(f"  main.yml card_store = {rm.get('card_store')}")
lc = load(os.path.join(base, "last_conference", "main.yml"))
print(f"  last_conference card_store:")
for c in (lc.get("card_store") or []):
    print(f"      {c}")
