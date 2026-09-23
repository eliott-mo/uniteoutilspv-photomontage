#!/usr/bin/env python3
"""Compose le rendu Blender sur la photo, puis mesure le resultat.

Le sol (herbe rase, pistes) reste peint par `montage.peindre_sol` en numpy : il
part du lancer de rayon sur le MNT et de la couleur de la photo elle-meme, ce que
Blender ne ferait pas mieux. Blender apporte les VOLUMES et leurs ombres.

La mesure finale passe par `charte_rendu.mesurer`, exactement comme pour les
references : c'est le seul moyen de dire si le rendu 3D se rapproche vraiment de
ce que fait le prestataire, au lieu d'en juger a l'oeil.

Usage :
    python composer_blender.py 10 rendu.png sortie.jpg
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import lecture_dxf
import montage as M
import terrain
from camera import Camera

HERE = Path(__file__).resolve().parent
DOSSIER = HERE / "exemples" / "sarnois-B" / "reportage-BE"


def composer(num, rendu, sortie, avec_sol=True):
    pose = json.loads((DOSSIER / f"pose_PV{num}.json").read_text(encoding="utf-8"))
    base = Image.open(DOSSIER / pose["photo"]).convert("RGB")
    W, H = base.size
    arr = np.array(base).astype(np.uint8)

    if avec_sol:
        scn = lecture_dxf.lire(M.DXF)
        q = np.array([t.q for t in scn.tables])
        mnt = terrain.charger_mnt((q[:, :, 0].min(), q[:, :, 1].min(),
                                   q[:, :, 0].max(), q[:, :, 1].max()), pas=5.0, marge=350.0)
        z0 = float(mnt.altitude(pose["est"], pose["nord"]))
        cam1 = Camera(W, H, pose["azimut"], pose["tangage"], pose.get("roulis", 0.0),
                      26.0, pose.get("hauteur_oeil", 1.60))
        cam1.f_px = pose["f_px"]
        rng = np.random.default_rng(7)
        arr, _, _ = M.peindre_sol(arr, scn, cam1, pose["est"], pose["nord"], z0, mnt,
                                  float(pose["horizon"]), rng)

    r = Image.open(rendu).convert("RGBA")
    if r.size != (W, H):
        r = r.resize((W, H), Image.LANCZOS)
    calque = np.array(r).astype(float)
    a = calque[..., 3:4] / 255.0
    out = np.array(arr).astype(float) * (1 - a) + calque[..., :3] * a
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    im.save(sortie, quality=95)
    print(f"compose : {sortie}  ({int((a > 0.02).sum())} px du rendu 3D)")
    return im


if __name__ == "__main__":
    num = sys.argv[1] if len(sys.argv) > 1 else "10"
    rendu = sys.argv[2]
    sortie = sys.argv[3] if len(sys.argv) > 3 else f"montage3d_PV{num}.jpg"
    composer(num, rendu, sortie)
    import charte_rendu as ch
    pose = json.loads((DOSSIER / f"pose_PV{num}.json").read_text(encoding="utf-8"))
    m, *_ = ch.mesurer(DOSSIER / pose["photo"], sortie)
    ref = json.loads((HERE / "charte_dossiers.json").read_text(encoding="utf-8"))["charte"]
    print(f"\n{'mesure':30s} {'rendu 3D':>10s} {'reference':>10s}")
    for k in ("panneau_luminance_sur_ciel", "panneau_ecart_type",
              "aeration_dans_la_bande", "ombre_rapport", "bord_douceur"):
        if k in m and k in ref:
            print(f"{k:30s} {m[k]:>10} {ref[k]:>10}")
    if "panneau_teinte" in m:
        print(f"{'panneau_teinte':30s} {str([round(x,2) for x in m['panneau_teinte']]):>10} "
              f"{str([round(x,2) for x in ref['panneau_teinte']]):>10}")
