#!/usr/bin/env python3
"""Confronte le modele de camera du projet a celui de Blender.

C'est le meme role que la confrontation a OpenCV dans test_geometrie.py : une
implementation totalement independante doit retrouver les memes pixels. Tant
que ce test n'est pas vert, rien ne doit etre rendu dans Blender.

Le piege est connu et documente : le repere camera du projet est GAUCHER
(det R = -1), Blender est droitier et sa camera regarde vers son -Z. Une erreur
de signe retourne le projet sans rien signaler.

Usage :
    python parite_blender.py                 # cherche Blender tout seul
    python parite_blender.py <blender.exe>
"""
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from camera import Camera

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "blender_camera.py"
CANDIDATS = [
    Path(os.environ.get("BLENDER", "")),
    Path.home() / "AppData/Local/Programs/blender-4.5.9-windows-x64/blender.exe",
    Path("C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"),
]


def trouver_blender():
    for c in CANDIDATS:
        if c and c.exists():
            return c
    import shutil
    w = shutil.which("blender")
    return Path(w) if w else None


def points_de_controle(cam, n=24, graine=3):
    """Points repartis dans le champ, a des distances et hauteurs variees."""
    rng = np.random.default_rng(graine)
    pts = []
    for _ in range(n):
        d = rng.uniform(8.0, 400.0)
        rel = math.radians(rng.uniform(-1, 1) * math.degrees(math.atan(cam.W / 2 / cam.f_px)) * 0.85)
        a = math.radians(cam.azimut) + rel
        z = rng.uniform(-2.0, 12.0)
        pts.append([d * math.sin(a), d * math.cos(a), z])
    return pts


CAS = [
    ("vue au sol, plein nord",   dict(azimut=0.0,    tangage=0.0,    roulis=0.0,   h=1.60)),
    ("azimut quelconque",        dict(azimut=33.9,   tangage=0.98,   roulis=0.0,   h=1.60)),
    ("tangage negatif",          dict(azimut=157.4,  tangage=-8.5,   roulis=0.0,   h=1.60)),
    ("roulis non nul",           dict(azimut=250.8,  tangage=8.19,   roulis=-2.09, h=1.60)),
    ("vue de drone plongeante",  dict(azimut=355.6,  tangage=-12.58, roulis=-2.09, h=29.1)),
    ("azimut proche de 360",     dict(azimut=357.45, tangage=3.40,   roulis=0.0,   h=1.60)),
]


def cameras():
    for nom, p in CAS:
        cam = Camera(1600, 1200, p["azimut"], p["tangage"], p["roulis"], 26.0, p["h"])
        cam.f_px = 1200.0
        yield nom, cam


def preparer(chemin):
    """Ecrit le fichier de parametres que Blender lira, un bloc par cas."""
    cas = []
    for nom, cam in cameras():
        cas.append({"largeur": cam.W, "hauteur": cam.H, "f_px": cam.f_px,
                    "position": [0.0, 0.0, cam.h],
                    "R": [[float(x) for x in ligne] for ligne in cam.R],
                    "points": points_de_controle(cam)})
    Path(chemin).write_text(json.dumps(cas), encoding="utf-8")
    print(f"{len(cas)} cas ecrits dans {chemin}")


def comparer(chemin_params, chemin_sortie):
    """Confronte les pixels de Blender a ceux de camera.py."""
    cas = json.loads(Path(chemin_params).read_text(encoding="utf-8"))
    res = json.loads(Path(chemin_sortie).read_text(encoding="utf-8"))
    pire = 0.0
    for (nom, cam), p, r in zip(cameras(), cas, res):
        mien = cam.projeter(p["points"])
        leur = np.array(r["uv"], float)
        devant = leur[:, 2] > 0
        ecart = np.abs(mien[devant] - leur[devant, :2])
        m = float(ecart.max()) if len(ecart) else float("nan")
        pire = max(pire, m)
        print(f"  {nom:28s} {int(devant.sum()):2d} points devant, ecart max {m:9.5f} px  "
              f"(lens {r['lens_mm']:.3f} mm)")
    print()
    print(f"ecart maximal sur tous les cas : {pire:.5f} px")
    if pire < 0.05:
        print("PARITE VERIFIEE : Blender retrouve les memes pixels que camera.py")
        return 0
    print("ECHEC : conventions discordantes, ne rien rendre avant correction")
    return 1


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "preparer":
        preparer(sys.argv[2]); return 0
    if len(sys.argv) >= 4 and sys.argv[1] == "comparer":
        return comparer(sys.argv[2], sys.argv[3])
    print(__doc__)
    print("Le sandbox interdit de lancer blender.exe depuis Python : passer par le shell.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
