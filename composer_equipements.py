#!/usr/bin/env python3
"""Compose un rendu Blender d'equipement sur le fond neutre, avec l'echelle.

Le fond — ciel degrade et prairie procedurale — reste calcule en numpy par
`fiche_equipements.fond`, comme pour les photomontages ou l'herbe rase vient du
lancer de rayon. Blender apporte les volumes et leurs ombres de contact.

Usage :
    python composer_equipements.py eq_poste.json rendu.png sortie.jpg "titre" "legende"
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import fiche_equipements as FE
import montage as M
from camera import Camera


def composer(scene, rendu, sortie, titre="", legende=()):
    d = json.loads(Path(scene).read_text(encoding="utf-8"))
    v = d["vue"]
    W, H = int(d["camera"]["largeur"]), int(d["camera"]["hauteur"])
    mnt = FE.SolPlat(v["z_sol"])
    cam1 = Camera(W, H, v["azimut"], FE.TANGAGE, 0.0, 26.0, 1.60)
    cam1.f_px = d["camera"]["f_px"]
    rng = np.random.default_rng(3)
    img, v0 = FE.fond(cam1, v["est"], v["nord"], v["z_sol"], mnt, rng)

    r = Image.open(rendu).convert("RGBA")
    if r.size != (W, H):
        r = r.resize((W, H), Image.LANCZOS)
    calque = np.array(r).astype(float)
    a = calque[..., 3:4] / 255.0
    out = img.astype(float) * (1 - a) + calque[..., :3] * a
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    d2 = ImageDraw.Draw(im, "RGBA")
    # silhouette de 1,75 m, devant le sujet et legerement de cote
    ap = math.radians(v["azimut"])
    dp = max(10.0, v["distance"] * 0.42)
    lat = -min(8.0, 0.16 * v["distance"])
    px = dp * math.sin(ap) + lat * math.cos(ap)
    py = dp * math.cos(ap) - lat * math.sin(ap)
    P = cam1.projeter([[px, py, 0.0]])[0]
    Q = cam1.projeter([[px, py, 1.75]])[0]
    if np.isfinite(P).all() and np.isfinite(Q).all():
        ht = P[1] - Q[1]
        ep = ht / 1.75
        x = Q[0]
        tete = 0.11 * ep
        d2.ellipse([x - tete, Q[1], x + tete, Q[1] + 2 * tete], fill=(54, 56, 62, 240))
        d2.polygon([(x - 0.24 * ep, Q[1] + 2.2 * tete), (x + 0.24 * ep, Q[1] + 2.2 * tete),
                    (x + 0.19 * ep, Q[1] + 0.72 * ht), (x + 0.20 * ep, P[1]),
                    (x + 0.05 * ep, P[1]), (x + 0.03 * ep, Q[1] + 0.78 * ht),
                    (x - 0.03 * ep, Q[1] + 0.78 * ht), (x - 0.05 * ep, P[1]),
                    (x - 0.20 * ep, P[1]), (x - 0.19 * ep, Q[1] + 0.72 * ht)],
                   fill=(54, 56, 62, 240))
        d2.text((x + 0.30 * ep, Q[1] + 0.3 * ht), "1,75 m", fill=(52, 52, 58))
    d2.rectangle([0, 0, W, 30], fill=(22, 22, 22))
    d2.text((10, 9), titre, fill=(255, 228, 120))
    if legende:
        d2.rectangle([0, H - 46, W, H], fill=(22, 22, 22, 225))
        for k, ligne in enumerate(legende):
            d2.text((10, H - 38 + k * 15), ligne, fill=(198, 198, 198))
    im.save(sortie, quality=93)
    print(f"compose : {sortie}  ({int((a > 0.02).sum())} px de rendu 3D)")
    return im


if __name__ == "__main__":
    titre = sys.argv[4] if len(sys.argv) > 4 else ""
    leg = sys.argv[5].split("|") if len(sys.argv) > 5 else ()
    composer(sys.argv[1], sys.argv[2], sys.argv[3], titre, leg)
