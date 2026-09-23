#!/usr/bin/env python3
"""Departage deux poses concurrentes par le PROFIL D'ELEVATION des boisements.

Le probleme : position et focale sont couplees. Une focale plus longue se
compense par un recul de la camera, et les mats d'eoliennes, tous a 1,5 km,
ne separent pas les deux — a Sarnois, 6 % de focale valent 100 m de position.
Il faut donc un repere PROCHE, dont la parallaxe soit forte.

Les boisements le sont : entre 100 et 500 m. Leur cime, vue de la photo, donne
un angle d'elevation par azimut ; l'orthophoto IGN et le MNT en donnent un
autre, calcule. La pose juste est celle qui les fait coincider. Contrairement
au test booleen de `calage_paysage._accord_silhouette`, on compare ici des
ANGLES, ce qui est sensible au deplacement et non seulement a la presence.

Usage :
    python arbitre_silhouette.py mesures_PV9.json pose_a.json pose_b.json ...
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

import calage_paysage as cp

HERE = Path(__file__).resolve().parent
H_ARBRE = 15.0                 # m, hauteur type d'une haie ou d'un boisement de plaine


def profil_mesure(photo, F, W, horizon_v, pas=1.0):
    """Elevation de la cime, en degres, par bin d'azimut relatif."""
    prof = cp.silhouette(photo)
    u = np.arange(W)
    rel = np.degrees(np.arctan((u - W / 2) / F))
    ok = np.isfinite(prof)
    bins = np.arange(-32, 32 + pas, pas)
    out = np.full(len(bins) - 1, np.nan)
    for k in range(len(bins) - 1):
        s = ok & (rel >= bins[k]) & (rel < bins[k + 1])
        if s.sum() > 2:
            out[k] = math.degrees(math.atan(float(np.median(horizon_v - prof[s])) / F))
    return bins, out


def profil_predit(E0, N0, az0, bins, TE, TN, ZT, z_oeil, dmin=40.0, dmax=900.0):
    d = np.hypot(TE - E0, TN - N0)
    pr = (d > dmin) & (d < dmax)
    if pr.sum() < 40:
        return np.full(len(bins) - 1, np.nan)
    az = (np.degrees(np.arctan2(TE[pr] - E0, TN[pr] - N0)) + 360) % 360
    rel = ((az - az0 + 180) % 360) - 180
    el = np.degrees(np.arctan((ZT[pr] + H_ARBRE - z_oeil) / d[pr]))
    out = np.full(len(bins) - 1, np.nan)
    idx = np.digitize(rel, bins) - 1
    for k in range(len(bins) - 1):
        s = idx == k
        if s.sum() > 3:
            out[k] = float(np.percentile(el[s], 92))     # la cime, pas la moyenne
    return out


def arbitrer(mesures, poses, verbose=True):
    import terrain
    m = json.loads(Path(mesures).read_text(encoding="utf-8"))
    W = m["largeur"]
    c0 = m["autour"]
    bb = (c0[0] - 1000, c0[1] - 1000, c0[0] + 1000, c0[1] + 1000)
    TE, TN = cp.masque_boisements(bb)
    mnt = terrain.charger_mnt(bb, pas=20.0, marge=0.0)
    ZT = np.array([float(mnt.altitude(e, n)) for e, n in zip(TE, TN)])
    if verbose:
        print(f"{len(TE)} points boises entre 40 et 900 m\n")
        print("  pose                                   f_px   horizon ajuste        ecart median     ecart quadratique  bins")
    res = []
    for p in poses:
        q = json.loads(Path(p).read_text(encoding="utf-8"))
        F = q["f_px"] * W / q["largeur"]
        hv = q["horizon"] * W / q["largeur"]
        z_oeil = float(mnt.altitude(q["est"], q["nord"])) + q.get("hauteur_oeil", 1.6)
        # L'horizon decale TOUT le profil d'un bloc : le laisser libre, sinon on
        # compare des poses a des reglages d'horizon differents et le test mesure
        # l'horizon, pas la position.
        meilleur = None
        for dh in np.arange(-30, 30.1, 1.5):
            bins, mes = profil_mesure(HERE / m["photo"], F, W, hv + dh)
            pred = profil_predit(q["est"], q["nord"], q["azimut"], bins, TE, TN, ZT, z_oeil)
            val = np.isfinite(mes) & np.isfinite(pred)
            if val.sum() < 20:
                continue
            e = mes[val] - pred[val]
            r = float(np.sqrt(np.mean(e ** 2)))
            if meilleur is None or r < meilleur[0]:
                meilleur = (r, float(np.median(np.abs(e))), float(hv + dh), int(val.sum()))
        rms, med, hbest, nb = meilleur
        res.append((rms, med, p, nb))
        if verbose:
            print(f"  {Path(p).name:36s} {F:7.1f}  horizon {hbest:6.1f} "
                  f"(lu {hv:.1f})  median {med:6.3f} deg  rms {rms:6.3f} deg  {nb:4d}")
    res.sort()
    if verbose:
        print(f"\n  -> {Path(res[0][2]).name} colle le mieux au relief boise")
    return res


if __name__ == "__main__":
    arbitrer(sys.argv[1], sys.argv[2:])
