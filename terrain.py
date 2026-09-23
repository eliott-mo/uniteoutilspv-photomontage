#!/usr/bin/env python3
"""Altitude du sol (RGE ALTI de l'IGN) et orthophoto, en Lambert 93.

Deux raisons de ne jamais se fier a l'altitude fournie ailleurs :
  - l'altitude GPS d'un telephone est ellipsoidale, environ 44 m au-dessus du
    NGF en France, et bruitee de plus ou moins 10 m ;
  - certains plans BE n'ont aucune couche topographique (cas de Saint-Cyr).

Les donnees sont mises en cache sur disque : un site deja telecharge ne
redeclenche aucun appel reseau.
"""
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import requests
from pyproj import Transformer

URL_ALTI = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
URL_WMS = "https://data.geopf.fr/wms-r/wms"
COUCHE_ORTHO = "ORTHOIMAGERY.ORTHOPHOTOS"
TAILLE_LOT = 5000
CACHE = Path(__file__).resolve().parent / ".cache_ign"
_VERS_WGS = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)
_VERS_L93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)


def l93(lon, lat):
    x, y = _VERS_L93.transform(lon, lat)
    return float(x), float(y)


def _cle(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


class Mnt:
    """Grille reguliere d'altitudes NGF en Lambert 93, avec interpolation bilineaire."""

    def __init__(self, x0, y0, pas, z):
        self.x0, self.y0, self.pas = float(x0), float(y0), float(pas)
        self.z = np.asarray(z, dtype=float)          # (lignes = Y croissant, colonnes = X croissant)

    @property
    def forme(self):
        return self.z.shape

    def altitude(self, x, y):
        """Altitude NGF interpolee. Accepte des scalaires ou des tableaux."""
        x = np.atleast_1d(np.asarray(x, dtype=float))
        y = np.atleast_1d(np.asarray(y, dtype=float))
        fx = (x - self.x0) / self.pas
        fy = (y - self.y0) / self.pas
        nj, ni = self.z.shape
        i0 = np.clip(np.floor(fx).astype(int), 0, ni - 2)
        j0 = np.clip(np.floor(fy).astype(int), 0, nj - 2)
        tx = np.clip(fx - i0, 0.0, 1.0)
        ty = np.clip(fy - j0, 0.0, 1.0)
        z00 = self.z[j0, i0]; z10 = self.z[j0, i0 + 1]
        z01 = self.z[j0 + 1, i0]; z11 = self.z[j0 + 1, i0 + 1]
        z = (z00 * (1 - tx) * (1 - ty) + z10 * tx * (1 - ty)
             + z01 * (1 - tx) * ty + z11 * tx * ty)
        return z if z.size > 1 else float(z[0])

    def vers_json(self, arrondi=2):
        return {"x0": round(self.x0, 2), "y0": round(self.y0, 2), "pas": self.pas,
                "nj": int(self.z.shape[0]), "ni": int(self.z.shape[1]),
                "z": [round(float(v), arrondi) for v in self.z.ravel()]}


def charger_mnt(bbox_l93, pas=5.0, marge=60.0, verbose=True):
    """Telecharge une grille RGE ALTI couvrant bbox_l93 elargie de `marge`."""
    xmin, ymin, xmax, ymax = bbox_l93
    xmin -= marge; ymin -= marge; xmax += marge; ymax += marge
    ni = int(np.ceil((xmax - xmin) / pas)) + 1
    nj = int(np.ceil((ymax - ymin) / pas)) + 1
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"mnt_{_cle(round(xmin), round(ymin), ni, nj, pas)}.npz"
    if f.exists():
        d = np.load(f)
        if verbose:
            print(f"  MNT depuis le cache : {nj}x{ni} points, pas {pas} m")
        return Mnt(d["x0"], d["y0"], d["pas"], d["z"])

    xs = xmin + np.arange(ni) * pas
    ys = ymin + np.arange(nj) * pas
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = _VERS_WGS.transform(gx.ravel(), gy.ravel())
    n = lon.size
    z = np.full(n, np.nan)
    lots = (n + TAILLE_LOT - 1) // TAILLE_LOT
    if verbose:
        print(f"  MNT RGE ALTI : {nj}x{ni} = {n} points, pas {pas} m, {lots} requete(s)")
    for k in range(lots):
        a, b = k * TAILLE_LOT, min((k + 1) * TAILLE_LOT, n)
        r = requests.post(URL_ALTI, json={
            "lon": "|".join(f"{v:.7f}" for v in lon[a:b]),
            "lat": "|".join(f"{v:.7f}" for v in lat[a:b]),
            "resource": "ign_rge_alti_wld", "delimiter": "|", "zonly": "true",
        }, timeout=90)
        r.raise_for_status()
        vals = np.array(r.json().get("elevations", []), dtype=float)
        if vals.size != b - a:
            raise RuntimeError(f"lot {k}: {vals.size} altitudes recues pour {b - a} demandees")
        z[a:b] = vals
    z[z <= -99000] = np.nan
    if np.isnan(z).any():
        moy = np.nanmean(z)
        z = np.where(np.isnan(z), moy, z)
    z = z.reshape(nj, ni)
    np.savez_compressed(f, x0=xmin, y0=ymin, pas=pas, z=z)
    if verbose:
        print(f"  altitudes NGF de {z.min():.1f} a {z.max():.1f} m")
    return Mnt(xmin, ymin, pas, z)


def charger_ortho(bbox_l93, resolution=0.25, max_px=5000, verbose=True):
    """Telecharge l'orthophoto IGN. Renvoie (bytes JPEG, bbox utilisee, largeur, hauteur)."""
    xmin, ymin, xmax, ymax = bbox_l93
    larg = int(round((xmax - xmin) / resolution))
    haut = int(round((ymax - ymin) / resolution))
    if max(larg, haut) > max_px:
        k = max(larg, haut) / max_px
        resolution *= k
        larg = int(round((xmax - xmin) / resolution))
        haut = int(round((ymax - ymin) / resolution))
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"ortho_{_cle(round(xmin), round(ymin), round(xmax), round(ymax), larg, haut)}.jpg"
    if f.exists():
        if verbose:
            print(f"  orthophoto depuis le cache : {larg}x{haut} px, {resolution:.2f} m/px")
        return f.read_bytes(), (xmin, ymin, xmax, ymax), larg, haut
    r = requests.get(URL_WMS, params={
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": COUCHE_ORTHO,
        "STYLES": "", "CRS": "EPSG:2154", "BBOX": f"{xmin},{ymin},{xmax},{ymax}",
        "WIDTH": larg, "HEIGHT": haut, "FORMAT": "image/jpeg",
    }, timeout=120)
    r.raise_for_status()
    if "image" not in r.headers.get("content-type", ""):
        raise RuntimeError(f"reponse WMS inattendue : {r.text[:200]}")
    f.write_bytes(r.content)
    if verbose:
        print(f"  orthophoto : {larg}x{haut} px, {resolution:.2f} m/px, {len(r.content)/1e6:.2f} Mo")
    return r.content, (xmin, ymin, xmax, ymax), larg, haut


if __name__ == "__main__":
    import lecture_dxf
    from pathlib import Path
    HERE = Path(__file__).resolve().parent
    sc = lecture_dxf.lire(HERE / "exemples" / "saint-cyr" / "20260903_SCV_IND06.dxf")
    x0, y0, x1, y1 = sc.bbox()
    print("Saint-Cyr :", sc.resume().splitlines()[0])
    mnt = charger_mnt((x0, y0, x1, y1), pas=5.0, marge=80.0)
    q = np.array([t.q for t in sc.tables])
    bas = q[:, 2:, :].reshape(-1, 3)
    sol = mnt.altitude(bas[:, 0], bas[:, 1])
    res = bas[:, 2] - sol
    print(f"\n  coins bas des tables - sol RGE ALTI : moyenne {res.mean():.3f} m, "
          f"ecart-type {res.std():.3f}, min {res.min():.2f}, max {res.max():.2f}")
    print(f"  -> le point bas des tables est donc a {res.mean():.2f} m du sol dans ce plan")
