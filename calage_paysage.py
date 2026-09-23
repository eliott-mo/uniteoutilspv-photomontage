#!/usr/bin/env python3
"""Cale une photo sans EXIF sur des reperes du paysage.

Une photo tiree d'un rapport de bureau d'etudes n'a plus ni focale, ni GPS, ni date.
On retrouve la pose a partir de deux signaux presents dans l'image :

  1. les MATS D'EOLIENNES, dont les positions sont connues par OpenStreetMap.
     Leurs abscisses donnent l'azimut et la focale. Attention : trois mats pour deux
     inconnues laissent des centaines de solutions numeriquement bonnes. C'est la
     TAILLE apparente (hauteur du moyeu au-dessus de l'horizon) qui leve l'ambiguite.
  2. la SILHOUETTE DES BOISEMENTS, comparee a celle que donne l'orthophoto IGN.
     Elle fixe la position, mais a +/- 50 m seulement.

Le tangage vient de l'horizon mesure dans l'image ; ne jamais le recalculer a la
main, `camera.Camera.horizon_v()` est la reference (le signe s'inverse trop vite).

Usage :
    import calage_paysage as cp
    prof = cp.silhouette("photo.jpg")
    mats = cp.mats("photo.jpg", 250, 272)
    pose = cp.caler(...)
"""
import itertools
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent


def silhouette(chemin, seuil_lum=95, seuil_bleu=4):
    """Ordonnee du bas du ciel pour chaque colonne (NaN si pas de ciel)."""
    a = np.array(Image.open(chemin).convert("RGB")).astype(float)
    ciel = (a.mean(axis=2) > seuil_lum) & (a[..., 2] - a[..., 0] > seuil_bleu)
    prof = np.full(a.shape[1], np.nan)
    for x in range(a.shape[1]):
        col = np.nonzero(ciel[:, x])[0]
        if not len(col):
            continue
        k = 0
        while k + 1 < len(col) and col[k + 1] <= col[k] + 2:   # ciel continu depuis le haut
            k += 1
        prof[x] = col[k]
    return prof


def horizon(prof, x0, x1):
    """Horizon lu sur une portion degagee de la silhouette (mediane, ecart-type)."""
    s = prof[x0:x1]
    s = s[np.isfinite(s)]
    return float(np.median(s)), float(s.std())


def mats(chemin, y0, y1, seuil=4.0, ecart=4):
    """Abscisses des mats : colonnes nettement plus claires que le ciel voisin."""
    g = np.array(Image.open(chemin).convert("RGB")).astype(float).mean(axis=2)
    prof = g[y0:y1].mean(axis=0)
    fond = np.convolve(prof, np.ones(31) / 31, mode="same")
    e = prof - fond
    return [(x, round(float(e[x]), 1)) for x in range(ecart, len(e) - ecart)
            if e[x] > seuil and e[x] == max(e[x - ecart:x + ecart + 1])]


def positions_le_long_des_voies(chemin_voies, bbox, pas=5.0):
    voies = json.loads(Path(chemin_voies).read_text())
    out = []
    for v in voies:
        p = np.array(v["pts"], float)
        for i in range(len(p) - 1):
            L = math.hypot(*(p[i + 1] - p[i]))
            for s in np.arange(0, L, pas):
                q = p[i] + (p[i + 1] - p[i]) * (s / L)
                if bbox[0] < q[0] < bbox[2] and bbox[1] < q[1] < bbox[3]:
                    out.append(q)
    return np.array(out)


def masque_boisements(bbox, resolution=0.60, max_px=2000, seuil_lum=75, seuil_tex=12):
    """Points boises de l'orthophoto IGN : sombres ET textures.

    OSM ne cartographie pas les haies dans ce secteur ; il faut passer par l'image.
    """
    import io
    from scipy import ndimage
    import terrain
    o, bb, lw, lh = terrain.charger_ortho(bbox, resolution=resolution,
                                          max_px=max_px, verbose=False)
    a = np.array(Image.open(io.BytesIO(o)).convert("RGB")).astype(float)
    lum = a.mean(axis=2)
    moy = ndimage.uniform_filter(lum, 9)
    tex = np.sqrt(np.maximum(ndimage.uniform_filter(lum ** 2, 9) - moy ** 2, 0))
    m = (lum < seuil_lum) & (tex > seuil_tex)
    m = ndimage.binary_closing(ndimage.binary_opening(m, np.ones((3, 3))), np.ones((5, 5)))
    res = (bb[2] - bb[0]) / lw
    ys, xs = np.nonzero(m)
    return bb[0] + (xs + 0.5) * res, bb[3] - (ys + 0.5) * res


BINS = np.arange(-36, 37, 1.5)


def _accord_silhouette(E, N, az0, F, W, prof, TE, TN, dmin=25.0, dmax=450.0,
                       horizon_v=286.0):
    """`horizon_v` separe « il y a un boisement dans ce secteur » de « il n'y en
    a pas » : un massif proche remonte la silhouette au-dessus de l'horizon.
    C'etait une constante 286, c'est-a-dire l'horizon de la vue 9 en 509 px de
    haut. Toute image d'une autre taille etait donc jugee de travers.
    """
    u = np.arange(W)
    rel_u = np.degrees(np.arctan((u - W / 2) / F))
    ok = np.isfinite(prof)
    mes = np.full(len(BINS) - 1, np.nan)
    for k in range(len(BINS) - 1):
        s = ok & (rel_u >= BINS[k]) & (rel_u < BINS[k + 1])
        if s.sum():
            mes[k] = 1.0 if np.nanmedian(prof[s]) < horizon_v else 0.0
    d = np.hypot(TE - E, TN - N)
    pr = (d > dmin) & (d < dmax)
    if pr.sum() < 50:
        return 0.0
    az = (np.degrees(np.arctan2(TE[pr] - E, TN[pr] - N)) + 360) % 360
    h, _ = np.histogram(((az - az0 + 180) % 360) - 180, bins=BINS)
    pred = (h > 12).astype(float)
    val = np.isfinite(mes)
    return float((pred[val] == mes[val]).mean())


def caler(U, prof, candidats, eoliennes, W, TE, TN, f_min=250.0, f_max=1400.0,
          rms_max=6.0, triples=None, verbose=True, PX=None, h_moyeu=(60.0, 100.0),
          ecart_taille=1.25):
    """Ajuste (position, azimut, focale) sur les mats puis la silhouette.

    U         : abscisses mesurees des mats, de gauche a droite
    PX        : hauteur du moyeu au-dessus de l'horizon, en px, pour chaque mat.
                C'est le controle d'echelle, et il est indispensable : sans lui,
                trois mats pour deux inconnues donnent des centaines de solutions
                numeriquement bonnes et geometriquement absurdes. Un moyeu a la
                distance d doit voir px * d constant d'un mat a l'autre, et le
                rapport donne la hauteur de moyeu, qui doit rester plausible.
    candidats : positions L93 possibles (N x 2)
    eoliennes : liste de dicts {id, E, N}
    """
    cx = W / 2.0
    U = np.asarray(U, float)
    out = []
    for c in candidats:
        azc = np.array([(math.degrees(math.atan2(e["E"] - c[0], e["N"] - c[1])) + 360) % 360
                        for e in eoliennes])
        # les mats se lisent de gauche a droite : les combinaisons doivent suivre
        # l'azimut croissant, pas l'ordre de la liste, sinon la bonne affectation
        # est ecartee d'office.
        ordre = np.argsort(azc)
        jeux = triples if triples is not None else list(
            itertools.combinations(range(len(eoliennes)), len(U)))
        for tri0 in jeux:
            tri = [int(ordre[i]) for i in tri0] if triples is None else list(tri0)
            az = azc[tri]
            if np.any(np.diff(az) <= 0.25) or az[-1] - az[0] > 62:
                continue

            def f(p, az=az):
                rel = np.radians(((az - p[0] + 180) % 360) - 180)
                if np.any(np.abs(rel) > 1.15):
                    return np.full(len(U), 1e3)
                return cx + p[1] * np.tan(rel) - U

            a_init = float(min(max(az.mean(), -89.0), 269.0))   # azimuts pres de 360 :
            s = least_squares(f, [a_init, 600.0],               # garder le depart dans les bornes
                              bounds=([-90, f_min], [270, f_max]))
            rms = float(np.sqrt(np.mean(s.fun ** 2)))
            if rms > rms_max:
                continue
            a0, F = s.x[0] % 360, s.x[1]
            dd = np.array([math.hypot(eoliennes[i]["E"] - c[0],
                                      eoliennes[i]["N"] - c[1]) for i in tri])
            hm = None
            if PX is not None:                      # controle d'echelle
                pxd = np.asarray(PX, float) * dd
                if pxd.max() / pxd.min() > ecart_taille:
                    continue
                hm = float(pxd.mean() / F)
                if not (h_moyeu[0] <= hm <= h_moyeu[1]):
                    continue
            sc = _accord_silhouette(c[0], c[1], a0, F, W, prof, TE, TN)
            out.append({"score": sc - rms / 40, "accord": sc, "rms": rms, "azimut": a0,
                        "f_px": F, "est": float(c[0]), "nord": float(c[1]), "h_moyeu": hm,
                        "ids": [eoliennes[i]["id"] for i in tri], "d": [float(x) for x in dd]})
    out.sort(key=lambda r: -r["score"])
    if verbose:
        vus = []
        for r in out:
            if any(math.hypot(r["est"] - e, r["nord"] - n) < 25 for e, n in vus):
                continue
            vus.append((r["est"], r["nord"]))
            print(f"  score {r['score']:.3f} | silhouette {r['accord']*100:5.1f}% | "
                  f"mats {r['rms']:5.2f} px | az {r['azimut']:6.2f} | f {r['f_px']:6.1f} px | "
                  f"E={r['est']:.0f} N={r['nord']:.0f} | d {[round(x) for x in r['d']]}"
                  + (f" | moyeu {r['h_moyeu']:.0f} m" if r.get("h_moyeu") else ""))
            if len(vus) >= 8:
                break
    return out


def taille_attendue(d, hauteur_moyeu=76.0, rayon=41.0, f_px=550.0):
    """Controle d'echelle : moyeu au-dessus de l'horizon, et rayon du rotor, en px."""
    return f_px * hauteur_moyeu / d, f_px * rayon / d
