#!/usr/bin/env python3
"""Vues de synthese des equipements techniques, sans photo.

Sert a montrer a quoi ressembleront le poste de transformation et la citerne
incendie avant d'avoir une photo du bon endroit. Le fond est neutre — ciel et
prairie procedurale — pour qu'on juge le volume et l'echelle, pas le paysage.

Les dimensions ne sont pas inventees : elles sortent des blocs du plan PVcase.
  - UNI_PTR       : batiment de 10,00 x 3,00 m dans une emprise de 13,5 x 7,0 m
  - citerne : bache SOUPLE de 120 m3, rectangulaire et bombee, environ
    12,0 x 10,0 m pour 1,35 m au centre (le nom de bloc CIT_RIGID du plan est
    trompeur, c'est bien une bache souple)
  - le bac de retention fait 16,0 x 11,3 m, soit 127 m3 sous 0,70 m de merlon

Usage : python fiche_equipements.py
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter

import lecture_dxf
import montage as M
from camera import Camera

HERE = Path(__file__).resolve().parent
SORTIE = HERE / "equipements_sarnois-B"
W, H = 1180, 740
CHAMP = 52.0                 # degres : perspective naturelle, sans deformation
TANGAGE = -1.2               # degres : on regarde legerement vers le bas


class SolPlat:
    """Terrain horizontal : on juge le volume, pas le relief."""

    def __init__(self, z):
        self.z = float(z)

    def altitude(self, x, y):
        x = np.atleast_1d(np.asarray(x, float))
        return np.full(x.shape, self.z) if x.size > 1 else self.z


def geometrie_equipements(chemin):
    """Centre et orientation reels du batiment PTR et de la cuve, lus dans le DXF."""
    import ezdxf
    msp = ezdxf.readfile(chemin).modelspace()
    out = {}

    # Ouvrages definis par une EMPRISE sur un calque, sans bloc nomme : le
    # poste de livraison, le local de stockage et la citerne de refroidissement
    # de Sarnois sont dans ce cas. Ils etaient donc invisibles au rendu alors
    # qu'ils figurent au plan.
    EMPRISES = {"uni_pdl": "pdl", "uni_local_stockage": "stockage",
                "uni_bess_refroidissement": "refroidissement"}
    for e in msp:
        cle = EMPRISES.get(e.dxf.layer.lower())
        if cle is None or e.dxftype() not in ("LWPOLYLINE", "HATCH"):
            continue
        if e.dxftype() == "HATCH":
            pts = [(v[0], v[1]) for b in e.paths for v in getattr(b, "vertices", [])]
        else:
            pts = [tuple(x) for x in e.get_points("xy")]
        a = np.array(pts, float)
        if len(a) < 4:
            continue
        c = a.mean(axis=0)
        _, _, vt = np.linalg.svd(a - c, full_matrices=False)
        pr = (a - c) @ vt.T
        L, l = float(np.ptp(pr[:, 0])), float(np.ptp(pr[:, 1]))
        if L < 1.0 or l < 0.5:
            continue
        d = {"centre": c, "angle": math.degrees(math.atan2(vt[0, 1], vt[0, 0])),
             "L": L, "l": l}
        if cle not in out or L * l > out[cle]["L"] * out[cle]["l"]:
            out[cle] = d
    for e in msp:
        if e.dxftype() != "INSERT":
            continue
        lay = M.__dict__.get("_sa", lambda s: s)(e.dxf.layer) if False else e.dxf.layer
        if e.dxf.name == "UNI_PTR":
            meil = None
            for ve in e.virtual_entities():
                if ve.dxftype() != "LWPOLYLINE":
                    continue
                p = np.array([tuple(x) for x in ve.get_points("xy")])
                c = p.mean(axis=0)
                _, _, vt = np.linalg.svd(p - c, full_matrices=False)
                pr = (p - c) @ vt.T
                L, l = np.ptp(pr[:, 0]), np.ptp(pr[:, 1])
                if 9.0 < L < 11.0 and 2.0 < l < 4.0:      # le batiment, pas l'emprise
                    meil = (c, math.degrees(math.atan2(vt[0, 1], vt[0, 0])), L, l)
            if meil:
                out["poste"] = {"centre": meil[0], "angle": meil[1], "L": meil[2], "l": meil[3]}
        elif "CIT_RIGID" in e.dxf.name:
            pts = []
            for ve in e.virtual_entities():
                if ve.dxftype() == "POLYLINE":
                    pts += [tuple(v.dxf.location)[:2] for v in ve.vertices]
            c = np.array([e.dxf.insert.x, e.dxf.insert.y], float)
            ang = float(e.dxf.rotation)
            if pts:
                a = np.array(pts, float)
                c = a.mean(axis=0)
                _, _, vt = np.linalg.svd(a - c, full_matrices=False)
                ang = math.degrees(math.atan2(vt[0, 1], vt[0, 0]))
            out["citerne"] = {"centre": c, "angle": ang}
        elif (e.dxf.name in ("UNI_Batterie", "UNI_Zone-remise", "UNI_Portail 5m",
                             "UNI_Zone de contention")
              or e.dxf.layer.lower().startswith("uni_portail")):
            # Blocs releves tels quels : centre, orientation et emprise. Le plan
            # de Sarnois porte un BESS, sa zone de remise et deux portails, qui
            # n'etaient jusqu'ici pas lus du tout.
            pts = []
            for ve in e.virtual_entities():
                if ve.dxftype() == "LWPOLYLINE":
                    pts += [tuple(x) for x in ve.get_points("xy")]
                elif ve.dxftype() == "POLYLINE":
                    pts += [tuple(v.dxf.location)[:2] for v in ve.vertices]
                elif ve.dxftype() == "LINE":
                    pts += [(ve.dxf.start.x, ve.dxf.start.y), (ve.dxf.end.x, ve.dxf.end.y)]
            if not pts:
                continue
            a = np.array(pts, float)
            c = a.mean(axis=0)
            _, _, vt = np.linalg.svd(a - c, full_matrices=False)
            pr = (a - c) @ vt.T
            cle = {"UNI_Batterie": "bess", "UNI_Zone-remise": "remise",
                   "UNI_Portail 5m": "portail",
                   "UNI_Zone de contention": "contention"}.get(e.dxf.name, "portail")
            d = {"centre": c, "angle": math.degrees(math.atan2(vt[0, 1], vt[0, 0])),
                 "L": float(np.ptp(pr[:, 0])), "l": float(np.ptp(pr[:, 1]))}
            if cle == "portail":
                out.setdefault("portails", []).append(d)
            else:
                out[cle] = d
    return out


def fond(cam, E0, N0, z0, mnt, rng, ciel_haut=(96, 134, 190), ciel_bas=(168, 186, 204)):
    """Ciel degrade jusqu'a l'horizon calcule, puis prairie procedurale."""
    v0 = cam.horizon_v()
    img = np.zeros((H, W, 3), float)
    for j in range(H):
        t = min(1.0, max(0.0, j / max(v0, 1.0)))
        img[j] = np.array(ciel_haut) * (1 - t) + np.array(ciel_bas) * t
    E, N, dist, ok = M.carte_sol(cam, E0, N0, z0, mnt, W, H, v0)
    herbe = np.array([101, 116, 71], float)
    n1 = gaussian_filter(rng.standard_normal((H, W)), 0.8)
    n2 = gaussian_filter(rng.standard_normal((H, W)), 3.0)
    n1 /= n1.std(); n2 /= n2.std()
    amp = 16.0 * np.exp(-dist / 90.0)
    tex = (n1 * 0.6 + n2 * 0.4) * amp
    lum = 1.0 - 0.16 * np.exp(-dist / 55.0)          # le sol proche est plus sombre
    sol = herbe[None, None, :] * lum[..., None] + tex[..., None] * np.array([0.8, 1.0, 0.6])
    brume = (1 - np.exp(-dist / 900.0))[..., None]
    sol = sol * (1 - brume) + np.array(ciel_bas)[None, None, :] * brume
    img[ok] = sol[ok]
    # au-dela de la portee du lancer, prolonger par la derniere teinte
    loin = (~ok) & (np.mgrid[0:H, 0:W][0] > v0)
    img[loin] = np.array(ciel_bas) * 0.72 + herbe * 0.28
    return np.clip(img, 0, 255).astype(np.uint8), v0


def vue(nom, titre, cible, distance, azimut, legende, tables=True, cloture=True):
    scn = lecture_dxf.lire(M.DXF)
    geo = geometrie_equipements(M.DXF)
    q = np.array([t.q for t in scn.tables])
    z0 = float(np.median(q[:, :, 2])) - 1.5
    mnt = SolPlat(z0)
    c = np.asarray(cible, float)
    a = math.radians(azimut)
    E0, N0 = c[0] - distance * math.sin(a), c[1] - distance * math.cos(a)
    f1 = (W / 2) / math.tan(math.radians(CHAMP / 2))     # champ impose, pas la focale eq. 35
    cam = Camera(W * M.SUR, H * M.SUR, azimut, TANGAGE, 0.0, 26.0, 1.60)
    cam.f_px = f1 * M.SUR
    cam1 = Camera(W, H, azimut, TANGAGE, 0.0, 26.0, 1.60)
    cam1.f_px = f1
    rng = np.random.default_rng(3)
    img, v0 = fond(cam1, E0, N0, z0, mnt, rng)
    ciel = np.array([168, 186, 204], float)
    sc = M.Scene(cam, E0, N0, z0, mnt, ciel)
    calque = Image.new("RGBA", (W * M.SUR, H * M.SUR), (0, 0, 0, 0))
    d = ImageDraw.Draw(calque, "RGBA")

    objets = []
    if tables:
        for t in scn.tables:
            m = np.array(t.q).mean(axis=0)
            dd = math.hypot(m[0] - E0, m[1] - N0)
            if dd < 320:
                objets.append((dd, "table", t.q))
    if cloture:
        for e in scn.lignes.get("cloture", []):
            pts = [(x, y) for x, y in e["pts"]]
            s0 = 0.0
            for i in range(len(pts) - 1):
                m = ((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2)
                objets.append((math.hypot(m[0] - E0, m[1] - N0), "cloture",
                               ([pts[i], pts[i + 1]], s0)))
                s0 += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    for cle, genre in (("poste", "poste"), ("citerne", "citerne")):
        if cle in geo:
            g = geo[cle]
            objets.append((math.hypot(g["centre"][0] - E0, g["centre"][1] - N0), genre, g))
    objets.sort(key=lambda z: -z[0])

    calque_sol = Image.new("RGBA", (W * M.SUR, H * M.SUR), (0, 0, 0, 0))
    d_sol = ImageDraw.Draw(calque_sol)
    for _, genre, obj in objets:
        if genre == "table":
            M.contact_sol(sc, d_sol, obj)
    calque.alpha_composite(calque_sol)

    for dist, genre, obj in objets:
        if genre == "table":
            M.dessiner_table(sc, d, obj, dist)
        elif genre == "cloture":
            M.dessiner_cloture(sc, d, obj[0], obj[1])
        elif genre == "poste":
            M.dessiner_poste(sc, d, obj["centre"], obj["angle"], dist,
                             L=obj.get("L", 10.0), l=obj.get("l", 3.0))
        elif genre == "citerne":
            M.dessiner_citerne(sc, d, obj["centre"], obj["angle"], dist)

    calque = calque.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.35))
    im = Image.fromarray(img)
    im.paste(calque, (0, 0), calque)
    d2 = ImageDraw.Draw(im, "RGBA")
    d2.rectangle([0, 0, W, 30], fill=(22, 22, 22))
    d2.text((10, 9), titre, fill=(255, 228, 120))
    d2.rectangle([0, H - 46, W, H], fill=(22, 22, 22, 225))
    for k, ligne in enumerate(legende):
        d2.text((10, H - 38 + k * 15), ligne, fill=(198, 198, 198))
    # echelle : silhouette d'une personne de 1,75 m a 15 m devant
    ap = math.radians(azimut)
    dp = max(10.0, distance * 0.42)                    # devant le sujet, pas a cote
    lat = -min(8.0, 0.16 * distance)
    px = E0 + dp * math.sin(ap) + lat * math.cos(ap)
    py = N0 + dp * math.cos(ap) - lat * math.sin(ap)
    P, Q = sc.p(px, py, z0), sc.p(px, py, z0 + 1.75)
    if P and Q:
        P = (P[0] / M.SUR, P[1] / M.SUR)
        Q = (Q[0] / M.SUR, Q[1] / M.SUR)
        ht = P[1] - Q[1]                       # hauteur apparente de 1,75 m
        ep = ht / 1.75                          # pixels par metre a cette distance
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
    SORTIE.mkdir(exist_ok=True)
    im.save(SORTIE / nom, quality=93)
    print(f"  {nom}  ({distance:.0f} m, azimut {azimut:.0f} deg)")
    return im


if __name__ == "__main__":
    geo = geometrie_equipements(M.DXF)
    print("geometrie lue dans le plan :")
    for k, g in geo.items():
        print(f"  {k:8s} centre {g['centre'][0]:.1f}, {g['centre'][1]:.1f}  angle {g['angle']:.1f} deg")
    vue("poste_transformation.jpg",
        "Poste de transformation - prefabrique beton 10,00 x 3,00 m, hauteur 2,60 m",
        geo["poste"]["centre"], 26.0, 200.0,
        ["Dimensions du bloc UNI_PTR du plan PVcase. Emprise amenagee 13,5 x 7,0 m.",
         "Vue de synthese sur fond neutre : ni photo, ni vegetation existante."])
    vue("citerne_incendie.jpg",
        "Citerne souple 120 m3 - bache PVC 12,0 x 10,0 m, 1,35 m au centre",
        geo["citerne"]["centre"], 30.0, 215.0,
        ["Bache souple dans un bac de retention de 16,0 x 11,3 m, merlon de 0,70 m.",
         "Forme de coussin : bombee au centre, affaissee jusqu'au sol sur le pourtour."])
    vue("entree_sud.jpg",
        "Entree sud - poste, citerne et premieres rangees",
        (geo["poste"]["centre"] + geo["citerne"]["centre"]) / 2, 85.0, 12.0,
        ["Les deux equipements sont distants de 47 m, groupes a l'entree sud du site.",
         "La cloture de 2,00 m a poteaux d'acacia ceinture l'ensemble."])
