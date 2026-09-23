#!/usr/bin/env python3
"""Mesure la luminance des modules DANS le rendu Blender, sans passer par la photo.

`charte_rendu.mesurer` classe en panneaux ce qui s'est ASSOMBRI par rapport a la
photo. Quand le rendu sort trop clair, ce masque n'attrape plus les modules et
les chiffres ne veulent plus rien dire. Ici on utilise le masque alpha du rendu,
qui est sans ambiguite.
"""
import json, sys
import numpy as np
from PIL import Image

a = np.array(Image.open(sys.argv[1]).convert("RGBA")).astype(float)
op = a[..., 3] > 200
ys = np.nonzero(op)[0]
v0, v1 = ys.min(), ys.max()
mod = op & (np.arange(a.shape[0])[:, None] < v0 + 0.45 * (v1 - v0))
rgb = a[..., :3][mod]
ciel = np.array(json.loads(sys.argv[2]))
lum = float(np.median(rgb.mean(axis=1)))
cible = float(np.mean(ciel))
t = rgb.mean(axis=0)
print(f"modules : {mod.sum():6d} px | luminance {lum:6.1f} | ciel {cible:5.1f} | "
      f"rapport {lum/cible:.3f} (cible 0.266) | teinte {np.round(t/t.mean(), 2)}")
