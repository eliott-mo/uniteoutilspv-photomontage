import json, sys
from pathlib import Path
f = Path(sys.argv[1]); d = json.loads(f.read_text(encoding="utf-8"))
if sys.argv[2] == "isoler":
    d["seulement"] = ["module"]
else:
    d.pop("seulement", None)
if len(sys.argv) > 3:
    m = d.get("materiaux", {}); m["module_base"] = [float(x) for x in sys.argv[3].split(",")]
    if len(sys.argv) > 4: m["module_rugosite"] = float(sys.argv[4])
    if len(sys.argv) > 5: m["module_specular"] = float(sys.argv[5])
    d["materiaux"] = m
f.write_text(json.dumps(d), encoding="utf-8")
