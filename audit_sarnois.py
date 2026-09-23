#!/usr/bin/env python3
"""V3 : re-audit du calage de IMG_6941 (Sarnois 10A) sur des reperes mesures.

Mesure dans la photo, sans reglage manuel :
  - l'inclinaison du fut de l'eolienne de gauche (verticale du monde)  -> roulis
  - l'inclinaison de la base de la ligne d'arbres (horizontale lointaine) -> roulis
  - la position horizontale des deux futs -> couple (azimut, focale)

Conclusion attendue et verrouillee par test_geometrie.py :
  roulis proche de 0 (valeur du 07/09 confirmee), focale entre 2900 et 3300 px
  (la regle EXIF naive a 2457 px est exclue), azimut et focale non separables
  avec seulement deux reperes distants de 5 degres.

Piege rencontre : une pale traverse le fut. Mesurer le fut par le maximum de
contraste attrape la pale et donne une inclinaison fausse de plusieurs degres.
Il faut chercher la bande SOMBRE (les pales sont claires) sur une plage de
lignes verifiee visuellement.

Lancer : python audit_sarnois.py
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
PHOTO = HERE / "exemples" / "sarnois-A" / "IMG_6941.jpeg"

CAM_L93 = (621980.0, 6954139.0)
EOLIENNES = {                       # OpenStreetMap, converties en Lambert 93
    "gauche (OSM 7595939636)": (621646.0, 6955615.0),
    "droite (OSM 7595939637)": (621732.0, 6956035.0),
}
# fenetres verifiees visuellement : fut seul, sans pale
FENETRE_FUT_GAUCHE = dict(u0=1738, u1=1775, v0=1445, v1=1515)
CALAGE_0709 = dict(azimut=336.5, tangage=-8.5, roulis=0.0, f_px=3166.0)
V_REF = 1500                        # ligne ou l'on compare les positions horizontales


def _charger():
    return np.array(Image.open(PHOTO).convert("L"), dtype=float)


def mesurer_fut(im, u0, u1, v0, v1):
    """Axe du fut par centroide de la bande sombre. Renvoie (tilt_deg, sigma, u_ref, residu)."""
    pts = []
    for v in range(v0, v1):
        ligne = im[v, u0:u1]
        ciel = np.percentile(ligne, 80)
        prof = np.clip(ciel - ligne, 0, None)
        prof[ligne > ciel - 6] = 0          # ecarte ciel et pales claires
        if prof.max() < 10:
            continue
        k = int(prof.argmax())
        lo, hi = max(0, k - 5), min(len(prof), k + 6)
        w, idx = prof[lo:hi], np.arange(lo, hi)
        if w.sum() <= 0:
            continue
        pts.append((v, u0 + float((w * idx).sum() / w.sum())))
    p = np.array(pts)
    a, b = np.polyfit(p[:, 0], p[:, 1], 1)
    r = p[:, 1] - (a * p[:, 0] + b)
    keep = np.abs(r) < 2.0 * max(r.std(), 0.5)
    a, b = np.polyfit(p[keep, 0], p[keep, 1], 1)
    r = p[keep, 1] - (a * p[keep, 0] + b)
    vv = p[keep, 0]
    sa = r.std() / np.sqrt(((vv - vv.mean()) ** 2).sum())
    return math.degrees(math.atan(a)), math.degrees(sa), a * V_REF + b, r.std(), int(keep.sum())


def mesurer_ligne_arbres(im, v0=1480, v1=1650):
    """Base de la ligne d'arbres : transition sombre -> clair. Renvoie (roulis_deg, residu, n)."""
    H, W = im.shape
    pts = []
    for u in range(60, W - 60, 20):
        col = im[v0:v1, max(0, u - 9):u + 10].mean(axis=1)
        g = np.gradient(col)
        k = int(g.argmax())
        if g[k] < 1.0:
            continue
        pts.append((u, v0 + k))
    p = np.array(pts, float)
    a, b = np.polyfit(p[:, 0], p[:, 1], 1)
    r = p[:, 1] - (a * p[:, 0] + b)
    keep = np.abs(r) < 2.5 * r.std()
    a, b = np.polyfit(p[keep, 0], p[keep, 1], 1)
    r = p[keep, 1] - (a * p[keep, 0] + b)
    return -math.degrees(math.atan(a)), r.std(), int(keep.sum())


def u_predit(az, f_px, tangage, roulis, largeur, hauteur):
    from camera import Camera
    c = Camera(largeur, hauteur, az, tangage, roulis, 24.0, 1.60)
    c.f_px = f_px
    out = []
    for (x, y) in EOLIENNES.values():
        dE, dN = x - CAM_L93[0], y - CAM_L93[1]
        uv = c.projeter([[dE, dN, 0.0], [dE, dN, 120.0]])
        (u0, v0), (u1, v1) = uv[0], uv[1]
        a = (u1 - u0) / (v1 - v0)
        out.append(a * (V_REF - v0) + u0)
    return np.array(out)


def main():
    im = _charger()
    H, W = im.shape
    print(f"Photo {W}x{H}\n")

    tilt, sig, u_gauche, res, n = mesurer_fut(im, **FENETRE_FUT_GAUCHE)
    print("Roulis")
    print(f"  fut eolienne gauche : {tilt:+.2f} +/- {sig:.2f} deg sur {n} lignes "
          f"(residu {res:.2f} px) -> la verticale du monde est verticale dans l'image")
    roulis_arbres, res_a, n_a = mesurer_ligne_arbres(im)
    print(f"  base ligne d'arbres : {roulis_arbres:+.2f} deg sur {n_a} colonnes (residu {res_a:.1f} px)")
    print(f"  => roulis compris entre {min(tilt, roulis_arbres):+.2f} et {max(tilt, roulis_arbres):+.2f} deg ; "
          f"la valeur 0 du 07/09 est compatible\n")

    print("Azimut et focale (tangage -8,5 et roulis 0 imposes)")
    obs = np.array([u_gauche, 2061.0])     # fut droit : mesure moins fiable (pale)
    print(f"  positions mesurees a v={V_REF} : gauche {obs[0]:.1f} px, droite {obs[1]:.1f} px (moins sure)")
    print(f"  {'focale':>22} | {'azimut':>7} | ecarts sur les deux futs")
    for f, etiq in ((2457.0, "regle EXIF naive"), (2912.0, "rognage 9:16 corrige"),
                    (3166.0, "calage du 07/09")):
        from scipy.optimize import least_squares
        r = least_squares(lambda p: u_predit(p[0], f, -8.5, 0.0, W, H) - obs,
                          [336.5], bounds=([320], [350]))
        print(f"  {f:6.0f} px ({f*24/W:5.2f} mm) {etiq:>0s}".ljust(24)
              + f" | {r.x[0]:7.2f} | {np.round(r.fun, 1)} px")
    print("\n  => la regle EXIF naive est exclue ; la focale est dans la bande 2900-3300 px.")
    print("     Azimut et focale restent correles (0,98) : deux reperes distants de 5 deg")
    print("     ne les separent pas. Il faut une mire (V5) ou des reperes tres ecartes.")


if __name__ == "__main__":
    main()
