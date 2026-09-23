#!/usr/bin/env python3
"""V4 : calcul de la pose de la camera a partir de points cliques (relevement).

Le chef de projet clique un point sur la photo et le meme point sur
l'orthophoto. L'orthophoto donne X et Y en Lambert 93, le modele de terrain
donne l'altitude. Avec quatre correspondances ou plus, on calcule ensemble la
position de la camera, son orientation et, si les points ne sont pas tous au
sol, sa focale.

Parametres (dans cet ordre) :
    est, nord   position de la camera en Lambert 93 (m)
    hauteur     hauteur de l'oeil au-dessus du sol (m)
    azimut      direction de visee (deg, 0 = Nord, sens horaire)
    tangage     positif = camera relevee (deg)
    roulis      (deg)
    f_px        focale en pixels (optionnelle)

Points au sol et focale : si toutes les correspondances sont au sol, le terrain
etant plat, la focale ne se separe pas du tangage et de la hauteur. Dans ce cas
il faut garder la focale fixee sur la valeur EXIF. Le solveur le detecte et le
signale.
"""
import math

import numpy as np
from scipy.optimize import least_squares

from camera import Camera

NOMS = ("est", "nord", "hauteur", "azimut", "tangage", "roulis", "f_px")


def _camera(p, largeur, hauteur_img):
    c = Camera(largeur, hauteur_img, p[3], p[4], p[5], 24.0, p[2])
    c.f_px = p[6]
    return c


def projeter(p, monde, mnt, largeur, hauteur_img):
    """Projette des points L93 (n,3) avec la pose p. Renvoie des pixels (n,2)."""
    monde = np.atleast_2d(np.asarray(monde, dtype=float))
    z_sol_cam = float(mnt.altitude(p[0], p[1]))
    local = np.column_stack([monde[:, 0] - p[0], monde[:, 1] - p[1], monde[:, 2] - z_sol_cam])
    return _camera(p, largeur, hauteur_img).projeter(local)


def residus(p, monde, pixels, mnt, largeur, hauteur_img, sigma_px):
    uv = projeter(p, monde, mnt, largeur, hauteur_img)
    d = (uv - pixels) / sigma_px
    d[~np.isfinite(d)] = 1e4              # point passe derriere la camera
    return d.ravel()


def points_coplanaires(monde, seuil=0.5):
    """Vrai si les points tiennent dans une tranche horizontale de `seuil` metres."""
    z = np.asarray(monde, dtype=float)[:, 2]
    return bool(z.max() - z.min() < seuil)


def resoudre(monde, pixels, depart, mnt, largeur, hauteur_img,
             libre=("est", "nord", "hauteur", "azimut", "tangage", "roulis"),
             sigma_px=2.0, bornes=None):
    """Ajuste la pose. `depart` est un dict, `libre` la liste des parametres ajustes.

    Renvoie un dict : pose, residus par point, RMS, ecarts-types, correlations.
    """
    monde = np.atleast_2d(np.asarray(monde, dtype=float))
    pixels = np.atleast_2d(np.asarray(pixels, dtype=float))
    if len(monde) != len(pixels):
        raise ValueError("autant de points monde que de pixels")
    n = len(monde)
    if 2 * n < len(libre):
        raise ValueError(f"{n} correspondances insuffisantes pour {len(libre)} inconnues")
    if "f_px" in libre and points_coplanaires(monde):
        raise ValueError("focale libre impossible : tous les points sont au sol "
                         "(focale, tangage et hauteur ne se separent pas)")

    p0 = np.array([float(depart[k]) for k in NOMS])
    idx = [NOMS.index(k) for k in libre]
    defaut = {"est": 60.0, "nord": 60.0, "hauteur": 1.2, "azimut": 40.0,
              "tangage": 25.0, "roulis": 15.0, "f_px": 0.5 * p0[6]}
    bornes = bornes or {}
    lo, hi = [], []
    for k in libre:
        d = bornes.get(k, defaut[k])
        v = p0[NOMS.index(k)]
        lo.append(v - d); hi.append(v + d)

    def f(x):
        p = p0.copy()
        p[idx] = x
        return residus(p, monde, pixels, mnt, largeur, hauteur_img, sigma_px)

    r = least_squares(f, p0[idx], bounds=(lo, hi), x_scale="jac", method="trf")
    p = p0.copy()
    p[idx] = r.x

    uv = projeter(p, monde, mnt, largeur, hauteur_img)
    err = uv - pixels
    dist = np.hypot(err[:, 0], err[:, 1])
    ddl = 2 * n - len(libre)
    rms = float(np.sqrt((dist ** 2).mean()))

    sigmas, correl = {}, None
    if ddl > 0:
        try:
            JtJ = r.jac.T @ r.jac
            cov = np.linalg.inv(JtJ) * max(1.0, (r.fun ** 2).sum() / ddl)
            s = np.sqrt(np.diag(cov))
            sigmas = {k: float(v * sigma_px) for k, v in zip(libre, s)}
            with np.errstate(invalid="ignore"):
                correl = cov / np.outer(s, s)
        except np.linalg.LinAlgError:
            pass

    return {
        "pose": {k: float(v) for k, v in zip(NOMS, p)},
        "libre": list(libre),
        "residus": dist.tolist(),
        "rms_px": rms,
        "max_px": float(dist.max()),
        "ddl": ddl,
        "sigmas": sigmas,
        "correlations": correl.tolist() if correl is not None else None,
        "convergence": bool(r.success),
        "coplanaires": points_coplanaires(monde),
    }


class MntPlat:
    """Terrain plat d'altitude constante, pour les tests."""

    def __init__(self, z=95.0):
        self.z = float(z)

    def altitude(self, x, y):
        x = np.atleast_1d(np.asarray(x, dtype=float))
        out = np.full(x.shape, self.z)
        return out if out.size > 1 else float(out[0])


def _test_synthetique():
    """Pose connue -> points projetes -> bruit -> on doit retrouver la pose."""
    rng = np.random.default_rng(12345)
    W, H = 4080, 3060
    mnt = MntPlat(95.0)
    vraie = {"est": 622900.0, "nord": 6750500.0, "hauteur": 1.62, "azimut": 13.8,
             "tangage": -2.5, "roulis": 1.1, "f_px": 2607.0}
    p_vraie = np.array([vraie[k] for k in NOMS])

    print("=== 1. points au sol, focale fixee (cas Saint-Cyr) ===")
    for n_pts, bruit in ((4, 0.0), (6, 2.0), (10, 2.0), (20, 5.0)):
        ok = 0
        for essai in range(20):
            ang = rng.uniform(-32, 32, n_pts)
            dist = rng.uniform(40, 400, n_pts)
            a = np.radians(vraie["azimut"] + ang)
            monde = np.column_stack([vraie["est"] + dist * np.sin(a),
                                     vraie["nord"] + dist * np.cos(a),
                                     np.full(n_pts, 95.0)])
            uv = projeter(p_vraie, monde, mnt, W, H)
            if not np.isfinite(uv).all():
                continue
            uv = uv + rng.normal(0, bruit, uv.shape)
            depart = dict(vraie, est=vraie["est"] + rng.uniform(-8, 8),
                          nord=vraie["nord"] + rng.uniform(-8, 8),
                          azimut=vraie["azimut"] + rng.uniform(-22, 22),
                          tangage=0.0, roulis=0.0, hauteur=1.60)
            r = resoudre(monde, uv, depart, mnt, W, H, sigma_px=max(bruit, 1.0))
            d_pos = math.hypot(r["pose"]["est"] - vraie["est"], r["pose"]["nord"] - vraie["nord"])
            d_az = abs(r["pose"]["azimut"] - vraie["azimut"])
            if d_pos < 3.0 and d_az < 1.0:
                ok += 1
        print(f"  {n_pts:2d} points, bruit {bruit:.0f} px : {ok}/20 poses retrouvees "
              f"(position < 3 m et azimut < 1 deg)")

    print("\n=== 2. detail d'un cas : 8 points au sol, bruit 2 px ===")
    ang = np.linspace(-30, 30, 8) + rng.normal(0, 3, 8)
    dist = rng.uniform(50, 380, 8)
    a = np.radians(vraie["azimut"] + ang)
    monde = np.column_stack([vraie["est"] + dist * np.sin(a),
                             vraie["nord"] + dist * np.cos(a), np.full(8, 95.0)])
    uv = projeter(p_vraie, monde, mnt, W, H) + rng.normal(0, 2.0, (8, 2))
    depart = dict(vraie, est=vraie["est"] + 6, nord=vraie["nord"] - 5, azimut=vraie["azimut"] + 18,
                  tangage=0.0, roulis=0.0, hauteur=1.60)
    r = resoudre(monde, uv, depart, mnt, W, H, sigma_px=2.0)
    print(f"  RMS {r['rms_px']:.2f} px, max {r['max_px']:.2f} px, {r['ddl']} degres de liberte")
    for k in r["libre"]:
        print(f"    {k:8s} = {r['pose'][k]:12.3f}  (vrai {vraie[k]:12.3f}, "
              f"ecart {r['pose'][k]-vraie[k]:+8.3f}, sigma {r['sigmas'].get(k, float('nan')):.3f})")

    print("\n=== 3. focale libre : refusee si tout est au sol, acceptee sinon ===")
    try:
        resoudre(monde, uv, depart, mnt, W, H,
                 libre=("est", "nord", "hauteur", "azimut", "tangage", "roulis", "f_px"))
        print("  PROBLEME : la focale libre aurait du etre refusee")
    except ValueError as e:
        print(f"  refus attendu : {e}")
    hauts = monde.copy()
    hauts[::2, 2] += rng.uniform(4, 12, len(hauts[::2]))     # sommets d'arbres, poteaux
    uv2 = projeter(p_vraie, hauts, mnt, W, H) + rng.normal(0, 2.0, (8, 2))
    depart2 = dict(depart, f_px=2400.0)
    r2 = resoudre(hauts, uv2, depart2, mnt, W, H,
                  libre=("est", "nord", "hauteur", "azimut", "tangage", "roulis", "f_px"),
                  sigma_px=2.0)
    print(f"  avec des points en hauteur : RMS {r2['rms_px']:.2f} px, "
          f"f_px = {r2['pose']['f_px']:.0f} (vrai 2607, depart 2400, "
          f"sigma {r2['sigmas'].get('f_px', float('nan')):.0f})")


if __name__ == "__main__":
    _test_synthetique()
