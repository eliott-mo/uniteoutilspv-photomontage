#!/usr/bin/env python3
"""Propose des points de vue de photomontage a partir du plan seul.

On ne dispose pas toujours d'une photo au bon endroit. Ce script part du plan BE,
du reseau de chemins d'OpenStreetMap et du modele de terrain, puis :

  - repere les elements techniques du plan (portail, poste de transformation,
    batteries, citerne incendie, base vie, pistes) avec leur emprise reelle ;
  - echantillonne les positions accessibles le long des routes et chemins ;
  - note chaque position pour chaque element : distance, taille apparente,
    degagement, orientation du soleil ;
  - produit une carte, un tableau et un apercu simule de ce qu'on verrait.

L'apercu n'est pas un photomontage : il n'y a pas de photo. Il sert a choisir
ou aller et dans quelle direction viser avant de se deplacer.

Usage : python proposer_vues.py
"""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import lecture_dxf
import terrain
from camera import Camera

HERE = Path(__file__).resolve().parent
DXF = HERE / "exemples" / "sarnois-B" / "2026_08_27-IMP-DEV-Fixe-IND10b_V2.dxf"
VOIES = HERE / "exemples" / "sarnois-B" / "voies_osm.json"
SORTIE = HERE / "propositions_sarnois-B"

HAUTEUR_OEIL = 1.60
LARGEUR_APERCU, HAUTEUR_APERCU = 1600, 900
FOCALE_APERCU = 26.0        # equivalent 35 mm, champ ~70 deg comme un telephone en paysage

# Elements techniques : nom affiche, couche DXF, hauteur retenue (m)
ELEMENTS = [
    ("Portail et zone de contention", ("UNI_portail", "UNI_Zone de contention"), 2.0),
    ("Poste de transformation",        ("UNI_PDT",),                             2.6),
    ("Batteries BESS",                 ("UNI_BESS_Batterie", "UNI_BESS_Zone_remise"), 2.9),
    ("Citerne incendie 120 m3",        ("UNI_SDIS_Bache_incendie",),             2.5),
    ("Base vie",                       ("UNI_VRD_Base_vie",),                    3.0),
    ("Bac d'equarissage",              ("UNI_Bac d'equarissage",),               1.5),
    ("Local de stockage",              ("UNI_Local_Stockage",),                  3.0),
]


def _sa(s):
    for a, b in (("é","e"),("è","e"),("ê","e"),("à","a"),("ô","o"),("û","u"),("î","i"),("ç","c")):
        s = s.replace(a, b).replace(a.upper(), b.upper())
    return s


def lire_elements(chemin):
    """Emprise au sol de chaque element technique, en Lambert 93.

    Une couche peut porter plusieurs objets distincts et eloignes : UNI_SDIS_Bache_incendie
    contient a la fois le bloc CIT_RIGID_120m3 de la citerne, a 621917/6954084, et un
    contour d'aire 70 m plus au sud-ouest. Un simple filtre de points aberrants choisissait
    l'un des deux au hasard et visait a cote. On separe donc les points en amas, et on
    privilegie les blocs INSERT, qui sont l'equipement lui-meme, sur les polylignes nues,
    qui ne sont que des contours de zone.
    """
    import ezdxf
    msp = ezdxf.readfile(chemin).modelspace()
    brut = {}
    for e in msp:
        lay = _sa(e.dxf.layer)
        pts = []
        bloc = e.dxftype() == "INSERT"
        if bloc:
            try:
                for ve in e.virtual_entities():
                    if ve.dxftype() == "LWPOLYLINE":
                        pts += [tuple(p) for p in ve.get_points("xy")]
                    elif ve.dxftype() == "LINE":
                        pts += [(ve.dxf.start.x, ve.dxf.start.y), (ve.dxf.end.x, ve.dxf.end.y)]
                    elif ve.dxftype() == "POLYLINE":
                        pts += [tuple(v.dxf.location)[:2] for v in ve.vertices]
            except Exception:
                pass
            if not pts:
                pts = [(e.dxf.insert.x, e.dxf.insert.y)]
        elif e.dxftype() == "LWPOLYLINE":
            pts = [tuple(p) for p in e.get_points("xy")]
        if pts:
            g = brut.setdefault(lay, {"bloc": [], "trait": []})
            g["bloc" if bloc else "trait"].extend(pts)

    out = []
    for nom, couches, h in ELEMENTS:
        bl, tr = [], []
        for c in couches:
            g = brut.get(_sa(c))
            if g:
                bl += g["bloc"]
                tr += g["trait"]
        pts = bl or tr                      # le bloc prime sur le contour de zone
        if not pts:
            continue
        amas = _amas(np.array(pts, dtype=float))
        for k, a in enumerate(amas, 1):
            out.append({"nom": nom if len(amas) == 1 else f"{nom} ({k})",
                        "hauteur": h, "pts": a, "centre": a.mean(axis=0),
                        "taille": float(max(np.ptp(a[:, 0]), np.ptp(a[:, 1])))})
    return out


def _amas(a, seuil=25.0):
    """Separe un nuage en objets distincts : lien simple, coupure a `seuil` metres."""
    if len(a) < 2:
        return [a]
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist
    etiq = fcluster(linkage(pdist(a), "single"), seuil, criterion="distance")
    return [a[etiq == k] for k in sorted(set(etiq))]


def positions_accessibles(chemin_voies, bbox, pas=12.0):
    """Points tous les `pas` metres le long des voies, limites a la zone utile."""
    voies = json.loads(Path(chemin_voies).read_text())
    pos = []
    for v in voies:
        p = np.array(v["pts"], dtype=float)
        for i in range(len(p) - 1):
            a, b = p[i], p[i + 1]
            L = math.hypot(*(b - a))
            if L < 1e-6:
                continue
            for s in np.arange(0, L, pas):
                q = a + (b - a) * (s / L)
                if bbox[0] <= q[0] <= bbox[2] and bbox[1] <= q[1] <= bbox[3]:
                    pos.append((q[0], q[1], v.get("type", ""), v.get("nom", "")))
    return pos


def coupe_emprise(p0, p1, poly, marge=6.0):
    """Le segment p0-p1 traverse-t-il le polygone (la centrale) ?"""
    from shapely.geometry import LineString, Polygon
    try:
        return LineString([p0, p1]).intersects(Polygon(poly).buffer(-marge))
    except Exception:
        return False


ANGLE_CIBLE = 12.0          # taille apparente visee : l'element occupe environ 1/6 du cadre
DIST_MIN, DIST_MAX = 45.0, 280.0


def evaluer(elem, pos, tables_poly, tables_cen, mnt, soleil_az=None):
    """Note un point de vue : on vise une taille apparente lisible, pas maximale.

    Trop pres, l'element remplit le cadre et on perd le contexte ; trop loin,
    il devient illisible. On demande aussi que des tables soient visibles,
    sans quoi ce n'est pas un photomontage de centrale.
    """
    x, y, typ, nom_voie = pos
    c = elem["centre"]
    d = math.hypot(c[0] - x, c[1] - y)
    if d < DIST_MIN or d > DIST_MAX:
        return None
    ang = math.degrees(2 * math.atan(elem["taille"] / (2 * d)))
    if coupe_emprise((x, y), tuple(c), tables_poly):
        return None
    az = (math.degrees(math.atan2(c[0] - x, c[1] - y)) + 360) % 360
    # contexte : combien de tables dans un champ de 70 degres autour de cet axe
    az_t = (np.degrees(np.arctan2(tables_cen[:, 0] - x, tables_cen[:, 1] - y)) + 360) % 360
    ecart_t = np.abs((az_t - az + 180) % 360 - 180)
    n_tables = int((ecart_t < 35).sum())
    if n_tables < 5:
        return None
    # note : proximite de la taille visee, en echelle logarithmique
    note = math.exp(-abs(math.log(max(ang, 0.5) / ANGLE_CIBLE)) ** 2 / 0.35)
    note *= min(1.0, 0.45 + n_tables / 60)          # bonus de contexte, plafonne
    if soleil_az is not None:                       # eviter le contre-jour
        ecart = abs((az - soleil_az + 180) % 360 - 180)
        if ecart < 45:
            note *= 0.45
        elif ecart > 135:
            note *= 1.2
    if typ in ("track", "path"):
        note *= 1.1                                 # un chemin est plus discret qu'une route
    return {"x": x, "y": y, "azimut": az, "distance": d, "angle": ang, "tables": n_tables,
            "note": note, "voie": typ, "nom_voie": nom_voie}


def dessiner_apercu(vue, scene, elems, mnt, chemin_png, titre):
    """Rendu simule depuis le point de vue : pas de photo, seulement le plan en 3D."""
    W, H = LARGEUR_APERCU, HAUTEUR_APERCU
    cam = Camera(W, H, vue["azimut"], vue.get("tangage", -1.5), 0.0, FOCALE_APERCU, HAUTEUR_OEIL)
    cam.f_px = W / 36.0 * FOCALE_APERCU
    zsol = float(mnt.altitude(vue["x"], vue["y"]))
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im, "RGBA")
    # Le fond doit basculer du ciel au sol sur la vraie ligne d'horizon de la camera,
    # pas au milieu de l'image. Avec un tangage de -1,5 deg elle remonte de 30 px, et
    # tout element au-dela de 60 m posait alors le pied sur du ciel : il levitait.
    v_hz = cam.horizon_v()          # jamais recalculer a la main : le signe du tangage s'inverse
    for j in range(H):                                     # ciel puis sol
        if j < v_hz:
            k = min(1.0, max(0.0, j / max(v_hz, 1.0)))
            d.line([(0, j), (W, j)], fill=(int(120+70*k), int(155+55*k), int(205+30*k)))
        else:
            k = min(1.0, max(0.0, (j - v_hz) / max(H - v_hz, 1.0)))
            d.line([(0, j), (W, j)], fill=(int(150-40*k), int(160-40*k), int(115-35*k)))

    def proj(X, Y, Z):
        uv = cam.projeter([[X - vue["x"], Y - vue["y"], Z - zsol]])[0]
        return None if not np.isfinite(uv).all() else (float(uv[0]), float(uv[1]))

    def poly(pts, remplissage, contour=None, ep=1):
        s = [proj(p[0], p[1], p[2] if len(p) > 2 else float(mnt.altitude(p[0], p[1]))) for p in pts]
        if any(v is None for v in s):
            return False
        if remplissage:
            d.polygon(s, fill=remplissage)
        if contour:
            d.line(s + [s[0]], fill=contour, width=ep)
        return True

    for p in scene.lignes.get("piste", []):
        poly([(a, b) for a, b in p["pts"]], (176, 160, 130, 235), (120, 105, 78, 255))
    for cat in ("plateforme", "sdis", "voirie"):
        for p in scene.lignes.get(cat, []):
            poly([(a, b) for a, b in p["pts"]], (162, 162, 156, 235), (90, 90, 88, 255))

    items = []
    for t in scene.tables:
        q = np.array(t.q)
        cen = q.mean(axis=0)
        items.append((math.hypot(cen[0]-vue["x"], cen[1]-vue["y"]), "table", t))
    for e in elems:
        items.append((math.hypot(e["centre"][0]-vue["x"], e["centre"][1]-vue["y"]), "elem", e))
    for it in sorted(items, key=lambda z: -z[0]):
        dist, genre, obj = it
        brume = 1 - math.exp(-dist / 2600)
        if genre == "table":
            q = obj.q
            n = np.cross(np.array(q[3])-np.array(q[0]), np.array(q[1])-np.array(q[0]))
            if n[2] < 0: n = -n
            n = n / np.linalg.norm(n)
            vers = np.array([vue["x"]-q[0][0], vue["y"]-q[0][1], zsol+HAUTEUR_OEIL-q[0][2]])
            vers /= np.linalg.norm(vers)
            cosv = abs(float(np.dot(n, vers)))
            R = 0.04 + 0.96 * (1 - cosv) ** 5
            base = np.array([34, 42, 62]) * (1 - R) + np.array([175, 192, 205]) * R
            coul = tuple(int(v*(1-brume) + 172*brume) for v in base)
            poly(q, coul + (255,), (14, 18, 30, 210))
        else:
            e = obj
            hull = e["pts"]
            if len(hull) > 2:
                from scipy.spatial import ConvexHull
                try:
                    hull = e["pts"][ConvexHull(e["pts"]).vertices]
                except Exception:
                    hull = e["pts"]
            # le pied suit le terrain point par point (0,70 m de denivele sous la
            # base vie), le toit reste plat comme celui d'un vrai batiment
            zb = [float(mnt.altitude(p[0], p[1])) for p in hull]
            zs = max(zb)
            bas = [(p[0], p[1], z) for p, z in zip(hull, zb)]
            haut = [(p[0], p[1], zs + e["hauteur"]) for p in hull]
            for i in range(len(bas)):                     # faces laterales
                j = (i + 1) % len(bas)
                poly([bas[i], bas[j], haut[j], haut[i]], (196, 192, 182, 255), (95, 92, 86, 255))
            poly(haut, (222, 218, 208, 255), (95, 92, 86, 255))
            if e["nom"] == vue.get("cible"):
                for i in range(len(bas)):
                    j = (i + 1) % len(bas)
                    poly([bas[i], bas[j], haut[j], haut[i]], (255, 214, 120, 235), (170, 110, 20, 255))
                poly(haut, (255, 232, 170, 245), (170, 110, 20, 255))
                s = proj(e["centre"][0], e["centre"][1], zs + e["hauteur"] + 2.5)
                if s and 0 < s[0] < W and 0 < s[1] < H:
                    d.text((s[0] - 40, s[1] - 14), e["nom"], fill=(150, 90, 0))

    for c in scene.lignes.get("cloture", []):
        pts = [(a, b) for a, b in c["pts"]]
        for i in range(len(pts) - 1):
            zs = float(mnt.altitude(pts[i][0], pts[i][1]))
            a = proj(pts[i][0], pts[i][1], zs + 2.0)
            b = proj(pts[i+1][0], pts[i+1][1], zs + 2.0)
            a2 = proj(pts[i][0], pts[i][1], zs)
            if a and b: d.line([a, b], fill=(110, 112, 104, 210), width=1)
            if a and a2: d.line([a, a2], fill=(90, 92, 86, 200), width=1)

    d.line([(0, v_hz), (W, v_hz)], fill=(255, 255, 255, 80), width=1)
    d.rectangle([0, 0, W, 30], fill=(20, 20, 20))
    d.text((10, 9), titre, fill=(255, 230, 120))
    d.rectangle([0, H-26, W, H], fill=(20, 20, 20))
    d.text((10, H-19), f"Apercu simule depuis le plan — champ {2*math.degrees(math.atan(W/2/cam.f_px)):.0f}°, "
                       f"oeil a {HAUTEUR_OEIL} m — ce n'est pas un photomontage", fill=(170, 170, 170))
    im.save(chemin_png, quality=92)


def main():
    SORTIE.mkdir(exist_ok=True)
    scene = lecture_dxf.lire(DXF)
    elems = lire_elements(DXF)
    print(f"{len(scene.tables)} tables, {len(elems)} elements techniques reperes")
    q = np.array([t.q for t in scene.tables])
    bbox_p = (q[:, :, 0].min(), q[:, :, 1].min(), q[:, :, 0].max(), q[:, :, 1].max())
    mnt = terrain.charger_mnt(bbox_p, pas=5.0, marge=350.0)
    from scipy.spatial import ConvexHull
    tp = q.reshape(-1, 3)[:, :2]
    tables_poly = tp[ConvexHull(tp).vertices]
    bbox_util = (bbox_p[0]-320, bbox_p[1]-320, bbox_p[2]+320, bbox_p[3]+320)
    pos = positions_accessibles(VOIES, bbox_util, pas=12.0)
    print(f"{len(pos)} positions accessibles echantillonnees sur les voies\n")

    soleil_az = 200.0        # milieu de journee en France : eviter de viser vers le sud
    tables_cen = q.mean(axis=1)[:, :2]
    retenues = []
    for e in elems:
        cands = [c for c in (evaluer(e, p, tables_poly, tables_cen, mnt, soleil_az) for p in pos) if c]
        if not cands:
            print(f"  {e['nom']:32s} : aucun point de vue accessible satisfaisant")
            continue
        cands.sort(key=lambda c: -c["note"])
        # on ecarte les positions trop proches d'une vue deja retenue
        best = None
        for c in cands:
            if all(math.hypot(c["x"]-r["x"], c["y"]-r["y"]) > 45 for r in retenues):
                best = c
                break
        if best is None:
            print(f"  {e['nom']:32s} : deja couvert par une vue voisine")
            continue
        best["cible"] = e["nom"]
        retenues.append(best)
        print(f"  {e['nom']:32s} : {len(cands):3d} positions possibles, retenue a "
              f"{best['distance']:3.0f} m, azimut {best['azimut']:3.0f} deg, "
              f"{best['angle']:4.1f} deg apparent, {best['tables']:2d} tables dans le champ ({best['voie']})")
    return scene, elems, mnt, retenues, tables_poly


def dessiner_carte(scene, elems, retenues, chemin_png):
    """Carte des points de vue proposes sur l'orthophoto IGN."""
    q = np.array([t.q for t in scene.tables])
    xs = list(q[:, :, 0].ravel()) + [v["x"] for v in retenues]
    ys = list(q[:, :, 1].ravel()) + [v["y"] for v in retenues]
    m = 70
    bbox = (min(xs)-m, min(ys)-m, max(xs)+m, max(ys)+m)
    octets, bb, lw, lh = terrain.charger_ortho(bbox, resolution=0.30, max_px=2400, verbose=False)
    import io as _io
    im = Image.open(_io.BytesIO(octets)).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    L = lambda X, Y: ((X-bb[0])/(bb[2]-bb[0])*lw, (bb[3]-Y)/(bb[3]-bb[1])*lh)
    voies = json.loads(Path(VOIES).read_text())
    for v in voies:
        p = [L(*pt) for pt in v["pts"]]
        d.line(p, fill=(255, 255, 255, 150), width=2)
    for t_ in scene.tables:
        d.polygon([L(p[0], p[1]) for p in t_.q], fill=(60, 90, 180, 120), outline=(40, 60, 140, 200))
    for c in scene.lignes.get("cloture", []):
        d.line([L(a, b) for a, b in c["pts"]], fill=(0, 0, 0, 220), width=3)
    for e in elems:
        c = L(e["centre"][0], e["centre"][1])
        d.ellipse([c[0]-7, c[1]-7, c[0]+7, c[1]+7], fill=(255, 200, 60, 230), outline=(140, 90, 0))
    for i, v in enumerate(retenues, 1):
        c = L(v["x"], v["y"])
        hf = math.radians(35)
        portee = min(v["distance"] * 1.25, 230)
        coin = [c]
        for s in np.linspace(-hf, hf, 9):
            a = math.radians(v["azimut"]) + s
            coin.append(L(v["x"] + portee*math.sin(a), v["y"] + portee*math.cos(a)))
        d.polygon(coin, fill=(230, 30, 30, 55))
        for s in (-hf, hf):
            a = math.radians(v["azimut"]) + s
            d.line([c, L(v["x"] + portee*math.sin(a), v["y"] + portee*math.cos(a))],
                   fill=(230, 30, 30, 190), width=2)
        a = math.radians(v["azimut"])
        d.line([c, L(v["x"] + portee*math.sin(a), v["y"] + portee*math.cos(a))],
               fill=(255, 60, 60, 230), width=3)
        d.ellipse([c[0]-9, c[1]-9, c[0]+9, c[1]+9], fill=(230, 30, 30), outline=(255, 255, 255))
        d.text((c[0]-3, c[1]-6), str(i), fill=(255, 255, 255))
    d.rectangle([0, 0, lw, 30], fill=(20, 20, 20))
    d.text((10, 9), "Points de vue proposes — Sarnois IND10B — rouge : camera et cone de vue, "
                    "jaune : elements techniques, blanc : voies accessibles", fill=(255, 230, 120))
    im.save(chemin_png, quality=92)
    return bb


def planche(fichiers, chemin_png, colonnes=2, largeur=900):
    """Assemble les apercus en une planche unique."""
    vign = [Image.open(f) for f in fichiers]
    h = int(largeur * vign[0].height / vign[0].width)
    lignes = (len(vign) + colonnes - 1) // colonnes
    im = Image.new("RGB", (colonnes * largeur, lignes * h), (24, 24, 24))
    for k, v in enumerate(vign):
        im.paste(v.resize((largeur, h), Image.LANCZOS),
                 ((k % colonnes) * largeur, (k // colonnes) * h))
    im.save(chemin_png, quality=88)


if __name__ == "__main__":
    scene, elems, mnt, retenues, tables_poly = main()
    apercus = []
    for i, v in enumerate(retenues, 1):
        f = SORTIE / f"vue_{i}_{v['cible'].split()[0].lower()}.jpg"
        dessiner_apercu(v, scene, elems, mnt, f,
                        f"Vue {i} : {v['cible']} — {v['distance']:.0f} m, azimut {v['azimut']:.0f}°")
        apercus.append(f)
        print(f"  apercu : {f.name}")
    planche(apercus, SORTIE / "planche_apercus.jpg")
    print("  planche : planche_apercus.jpg")
    dessiner_carte(scene, elems, retenues, SORTIE / "carte_points_de_vue.jpg")
    print("  carte : carte_points_de_vue.jpg")
    (SORTIE / "vues.json").write_text(json.dumps(retenues, indent=1, default=float), encoding="utf-8")
