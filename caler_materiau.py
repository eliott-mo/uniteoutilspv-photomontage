#!/usr/bin/env python3
"""Ecrit les reglages de materiau dans la scene, ou mesure un rendu.

Deux sous-commandes, pour que le balayage se pilote depuis le shell sans
bagarre d'echappement :

    python caler_materiau.py regler scene.json 0.45 0.25
    python caler_materiau.py mesurer rendu.png scene.json
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def regler(scene, rugosite, specular, base=None):
    f = Path(scene)
    d = json.loads(f.read_text(encoding="utf-8"))
    m = d.get("materiaux", {})
    m["module_rugosite"] = float(rugosite)
    m["module_specular"] = float(specular)
    if base:
        m["module_base"] = [float(x) for x in base.split(",")]
    d["materiaux"] = m
    f.write_text(json.dumps(d), encoding="utf-8")


def mesurer(rendu, scene):
    """Luminance des modules lue sur le masque alpha du rendu, sans ambiguite."""
    d = json.loads(Path(scene).read_text(encoding="utf-8"))
    ciel = np.asarray(d.get("ciel", [135, 156, 173]), float)
    a = np.array(Image.open(rendu).convert("RGBA")).astype(float)
    op = a[..., 3] > 200
    if not op.any():
        return None
    ys = np.nonzero(op)[0]
    v0, v1 = ys.min(), ys.max()
    mod = op & (np.arange(a.shape[0])[:, None] < v0 + 0.45 * (v1 - v0))
    rgb = a[..., :3][mod]
    lum = float(np.median(rgb.mean(axis=1)))
    t = rgb.mean(axis=0)
    return {"px": int(mod.sum()), "luminance": lum, "ciel": float(ciel.mean()),
            "rapport": lum / float(ciel.mean()),
            "teinte": [round(float(x), 3) for x in t / t.mean()],
            "ecart_type": float(rgb.mean(axis=1).std())}


if __name__ == "__main__":
    if sys.argv[1] == "regler":
        regler(*sys.argv[2:])
    else:
        r = mesurer(sys.argv[2], sys.argv[3])
        if r is None:
            print("rendu vide")
        else:
            print(f"{r['px']:6d} px | luminance {r['luminance']:6.1f} | rapport "
                  f"{r['rapport']:.3f} (cible 0.266) | ecart-type {r['ecart_type']:5.1f} "
                  f"| teinte {r['teinte']}")
