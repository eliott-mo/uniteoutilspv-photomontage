#!/usr/bin/env python3
"""Genere un outil de calage autonome (un HTML par point de vue).

Assemble le plan BE, le modele de terrain IGN, l'orthophoto IGN et la photo,
puis produit un fichier HTML ou le chef de projet clique des points d'appui
(le meme endroit sur la photo et sur la carte) et lance le calcul de pose.

Usage :
    python preparer_vue.py                       # tous les points de vue de Saint-Cyr
    python preparer_vue.py 7                     # seulement le point de vue 7
    python preparer_vue.py 7 D:\\calage          # dans un autre dossier

Attention OneDrive : ces fichiers font 2 a 3 Mo chacun. Les regenerer plusieurs
fois de suite dans un dossier synchronise provoque des conflits de
synchronisation et, parfois, des fichiers corrompus. En cas de mise au point
repetee, generer dans un dossier local hors OneDrive.
"""
import base64
import datetime
import io
import json
import math
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image

import camera
from PIL.ExifTags import TAGS

import lecture_dxf
import terrain

HERE = Path(__file__).resolve().parent
GABARIT = HERE / "gabarit_vue.html"
SORTIE = HERE / "calage"

CONFIG = {
    "nom": "Saint-Cyr-en-Val",
    "dxf": HERE / "exemples" / "saint-cyr" / "20260903_SCV_IND06.dxf",
    "photos": HERE / "exemples" / "saint-cyr" / "photos",
    "shapefile": HERE / "exemples" / "saint-cyr" / "localisation" / "Propostions photomontages.shp",
    "cloture_h": 2.0,
    "photo_largeur": 2720,      # largeur de la photo embarquee (px)
    "photo_qualite": 82,
    "ortho_max_px": 3000,
    "ortho_resolution": 0.20,   # resolution native de l'ortho IGN
    "ortho_marge_m": 90.0,      # marge autour du couple camera / projet
    "mnt_pas": 5.0,
    "marge_m": 120.0,
}

# Projet sans couche SIG des points de vue : on decrit la vue a la main.
CONFIG_SARNOIS = {
    "nom": "Sarnois-10A",
    "dxf": HERE / "exemples" / "sarnois-A" / "2026_08_025-IMP-DEV-Fixe-IND10a_V2.dxf",
    "cloture_h": 2.0,
    "photo_largeur": 2268,
    "photo_qualite": 84,
    "ortho_max_px": 3000,
    "ortho_resolution": 0.20,
    "ortho_marge_m": 120.0,
    "mnt_pas": 5.0,
    "marge_m": 150.0,
    "vues": [{
        "num": 1,
        "photo": HERE / "exemples" / "sarnois-A" / "IMG_6941.jpeg",
        "lon": 1.91953, "lat": 49.68153,
        "cardinal": "nord-ouest",
        # calage valide le 16/09/2026 (VALIDATION_V1_V3.md), f_px pour 2268 px de large
        "pose": {"hauteur": 1.60, "azimut": 336.5, "tangage": -8.5, "roulis": 0.0, "f_px": 3166.0},
    }],
}

CARDINAUX = {"nord": 0, "nord-est": 45, "est": 90, "sud-est": 135,
             "sud": 180, "sud-ouest": 225, "ouest": 270, "nord-ouest": 315}


def _sans_accents(s):
    for a, b in (("é","e"),("è","e"),("ê","e"),("à","a"),("ô","o"),("û","u"),("î","i"),("ç","c")):
        s = s.replace(a, b).replace(a.upper(), b.upper())
    return s


def lire_points_de_vue(chemin_shp):
    import geopandas as gpd
    g = gpd.read_file(chemin_shp).to_crs("EPSG:4326")
    vues = []
    for i, r in g.iterrows():
        card = _sans_accents(str(r.get("Orientatio") or "")).strip().lower()
        vues.append({
            "num": int(r.get("Nom") or i + 1),
            "nom_fichier": str(r.get("Name") or ""),
            "lon": float(r.geometry.x), "lat": float(r.geometry.y),
            "z_gps": float(r.geometry.z) if r.geometry.has_z else None,
            "cardinal": card,
            "azimut_cardinal": CARDINAUX.get(card),
            "horodatage": str(r.get("DateTime") or ""),
        })
    return sorted(vues, key=lambda v: v["num"])


def exif_photo(chemin):
    im = Image.open(chemin)
    larg, haut = im.size
    ex = im.getexif()
    ifd = ex.get_ifd(0x8769) if ex else {}
    d = {TAGS.get(k, k): v for k, v in ifd.items()}
    base = {TAGS.get(k, k): v for k, v in ex.items()} if ex else {}
    f35 = d.get("FocalLengthIn35mmFilm")
    gps = ex.get_ifd(0x8825) if ex else {}
    lon = lat = None
    if gps and 2 in gps and 4 in gps:
        def dd(v, ref):
            x = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -x if ref in ("S", "W") else x
        lat, lon = dd(gps[2], gps.get(1, "N")), dd(gps[4], gps.get(3, "E"))
    ratio = min(larg, haut) / max(larg, haut)
    rognee = abs(ratio - 3 / 4) > 0.02
    f_px = None
    if f35:
        cote = max(larg, haut) if rognee else larg
        # UNE SEULE CONVENTION POUR TOUT LE DEPOT : la diagonale, via
        # `camera.focale_px_depuis_exif`. Ce module avait la sienne — le grand
        # cote pour 36 mm — qui sous-estime de 4 % sur un capteur 4:3. Le
        # calage de Saint-Cyr a ete lance avec 2607 px au lieu de 2711.
        f_px = camera.focale_px_depuis_exif(larg, haut, float(f35))[0]
    return {"largeur": larg, "hauteur": haut, "ratio": round(larg / haut, 4), "rognee": rognee,
            "f35": float(f35) if f35 else None, "f_px": f_px, "lon": lon, "lat": lat,
            "appareil": f"{base.get('Make','')} {base.get('Model','')}".strip(),
            "horodatage": str(base.get("DateTime", "")), "zoom": d.get("DigitalZoomRatio")}


def geometrie_l93(scene, mnt):
    """Geometrie du projet en Lambert 93 absolu, altitudes NGF."""
    tables = [[[round(c, 2) for c in p] for p in t.q] for t in scene.tables]

    def au_sol(poly):
        pts = np.array(poly, dtype=float)
        z = mnt.altitude(pts[:, 0], pts[:, 1])
        z = np.atleast_1d(z)
        return [[round(float(x), 2), round(float(y), 2), round(float(zz), 2)]
                for (x, y), zz in zip(pts, z)]

    cloture = [au_sol(l["pts"]) for l in scene.lignes.get("cloture", [])]
    pistes = [au_sol(l["pts"]) for l in scene.lignes.get("piste", [])]
    zones = []
    for cat in ("plateforme", "pdl", "local", "voirie", "sdis"):
        for l in scene.lignes.get(cat, []):
            if l["fermee"]:
                zones.append(au_sol(l["pts"]))
    return {"tables": tables, "cloture": cloture, "pistes": pistes, "zones": zones}


def position_soleil(horodatage, lat, lon):
    """Azimut et hauteur du soleil a l'instant de la photo (pvlib).

    L'EXIF donne l'heure locale sans fuseau. On suppose l'heure legale
    francaise : UTC+1 en hiver, UTC+2 en ete.
    """
    if not horodatage or not lat or not lon:
        return None
    try:
        dt = datetime.datetime.strptime(horodatage, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    fuseau = ZoneInfo("Europe/Paris")
    dt = dt.replace(tzinfo=fuseau)
    try:
        import pandas as pd
        import pvlib
        pos = pvlib.solarposition.get_solarposition(
            pd.DatetimeIndex([dt]), lat, lon)
        az = float(pos["azimuth"].iloc[0])
        el = float(pos["apparent_elevation"].iloc[0])
    except Exception:
        return None
    return {"azimut": round(az, 1), "elevation": round(el, 1),
            "instant": dt.strftime("%d/%m/%Y %H:%M %Z")}


def nettoyer_sharepoint(html):
    """Retire les metadonnees que SharePoint/OneDrive injecte dans les fichiers HTML.

    Un dossier synchronise fait apparaitre un bloc <!--[if gte mso 9]><xml>...
    et des attributs xmlns sur <html>. Sans effet sur le rendu, mais cela pollue
    le gabarit et se recopie dans chaque fichier produit.
    """
    motif = r"\n?<!--\[if gte mso 9\]>.*?<!\[endif\]-->\n?"
    html = re.sub(motif, "\n", html, flags=re.S)
    return html.replace(
        '<html lang="fr" xmlns:mso="urn:schemas-microsoft-com:office:office" '
        'xmlns:msdt="uuid:C2F41010-65B3-11d1-A29F-00AA00C14882">', '<html lang="fr">')


def azimut_vers(x0, y0, x1, y1):
    return (math.degrees(math.atan2(x1 - x0, y1 - y0)) + 360) % 360


def preparer(cfg, num=None, sortie=None):
    sortie = Path(sortie) if sortie else SORTIE
    print(f"=== {cfg['nom']} ===")
    scene = lecture_dxf.lire(cfg["dxf"])
    print(" ", scene.resume().splitlines()[0])
    vues = (lire_points_de_vue(cfg["shapefile"]) if cfg.get("shapefile")
            else [dict(v, azimut_cardinal=CARDINAUX.get(v.get("cardinal", "")),
                       nom_fichier=str(v.get("photo", "")), horodatage="") for v in cfg["vues"]])
    if num:
        vues = [v for v in vues if v["num"] == num]
        if not vues:
            raise SystemExit(f"point de vue {num} introuvable")

    xs_proj = [p[0] for t in scene.tables for p in t.q]
    ys_proj = [p[1] for t in scene.tables for p in t.q]
    pts_vues = [terrain.l93(v["lon"], v["lat"]) for v in vues]
    xs = xs_proj + [p[0] for p in pts_vues]
    ys = ys_proj + [p[1] for p in pts_vues]
    m = cfg["marge_m"]
    bbox = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)
    print(f"  emprise L93 {bbox[2]-bbox[0]:.0f} x {bbox[3]-bbox[1]:.0f} m")

    mnt = terrain.charger_mnt(bbox, pas=cfg["mnt_pas"], marge=0.0)
    geom = geometrie_l93(scene, mnt)
    centre = scene.centre()
    gabarit = nettoyer_sharepoint(GABARIT.read_text(encoding="utf-8"))
    sortie.mkdir(parents=True, exist_ok=True)
    produits = []

    for v in vues:
        f_photo = Path(v["photo"]) if v.get("photo") else cfg["photos"] / f"PM ({v['num']}).jpg"
        if not f_photo.exists():
            print(f"  point de vue {v['num']} : photo absente, ignore")
            continue
        ex = exif_photo(f_photo)
        x_cam, y_cam = terrain.l93(ex["lon"] or v["lon"], ex["lat"] or v["lat"])
        z_sol = float(mnt.altitude(x_cam, y_cam))
        az_projet = azimut_vers(x_cam, y_cam, centre[0], centre[1])
        az_card = v["azimut_cardinal"]
        if az_card is None:
            az0 = az_projet
        else:
            ecart = abs((az_projet - az_card + 180) % 360 - 180)
            az0 = az_projet if ecart <= 90 else az_card

        # orthophoto cadree sur le couple camera / projet, a la resolution native
        mo = cfg["ortho_marge_m"]
        o_bbox = (min(min(xs_proj), x_cam) - mo, min(min(ys_proj), y_cam) - mo,
                  max(max(xs_proj), x_cam) + mo, max(max(ys_proj), y_cam) + mo)
        ortho_bytes, ortho_bbox, o_larg, o_haut = terrain.charger_ortho(
            o_bbox, resolution=cfg["ortho_resolution"], max_px=cfg["ortho_max_px"], verbose=False)
        ortho_b64 = base64.b64encode(ortho_bytes).decode("ascii")

        im = Image.open(f_photo).convert("RGB")
        larg = min(cfg["photo_largeur"], im.width)
        haut = round(im.height * larg / im.width)
        buf = io.BytesIO()
        im.resize((larg, haut), Image.LANCZOS).save(buf, "JPEG", quality=cfg["photo_qualite"], optimize=True)
        photo_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        f_px = ex["f_px"] * larg / ex["largeur"] if ex["f_px"] else larg / 36.0 * 26.0

        dist = math.hypot(centre[0] - x_cam, centre[1] - y_cam)
        soleil = position_soleil(ex["horodatage"], ex["lat"], ex["lon"])
        donnees = {
            "nom_court": f"{cfg['nom'].replace(' ','')}_PV{v['num']}",
            "photo": {"largeur": larg, "hauteur": haut},
            "ortho": {"xmin": ortho_bbox[0], "ymin": ortho_bbox[1], "xmax": ortho_bbox[2],
                      "ymax": ortho_bbox[3], "largeur": o_larg, "hauteur": o_haut},
            "mnt": mnt.vers_json(),
            "geom": geom,
            "cloture_h": cfg["cloture_h"],
            "soleil": soleil,
            "depart": dict({"est": round(x_cam, 2), "nord": round(y_cam, 2), "hauteur": 1.60,
                            "azimut": round(az0, 1), "tangage": 0.0, "roulis": 0.0,
                            "f_px": round(f_px, 1)}, **(v.get("pose") or {})),
        }
        # une photo issue d'un rapport de BE n'a plus d'EXIF : ni focale, ni GPS, ni date
        bouts = [f"{ex['appareil'] or 'appareil inconnu'} &middot; {ex['largeur']}&times;{ex['hauteur']} "
                 f"({'rogn&eacute;e' if ex['rognee'] else 'format natif'})"]
        bouts.append(f"{ex['f35']:.0f} mm &eacute;q. 35" if ex["f35"]
                     else "focale inconnue, &agrave; r&eacute;soudre")
        if ex["horodatage"]:
            bouts.append(str(ex["horodatage"]))
        bouts.append(f"GPS {ex['lat']:.6f}, {ex['lon']:.6f}" if ex["lat"] is not None
                     else f"position estim&eacute;e {v['lat']:.5f}, {v['lon']:.5f}")
        bouts.append(f"sol {z_sol:.1f} m NGF")
        bouts.append(f"projet &agrave; {dist:.0f} m, azimut {az_projet:.0f}&deg;")
        bouts.append(f"BE : {v['cardinal'] or 'non renseign&eacute;'}")
        if soleil:
            bouts.append(f"soleil {soleil['azimut']:.0f}&deg;/{soleil['elevation']:.0f}&deg;")
        sous = " &middot; ".join(bouts[:3]) + "<br>" + " &middot; ".join(bouts[3:])
        html = (gabarit
                .replace("__TITRE__", f"Calage {cfg['nom']} &mdash; point de vue {v['num']}")
                .replace("__NOM_PHOTO__", f"PM ({v['num']}).jpg")
                .replace("__SOUS_TITRE__", sous)
                .replace("__DONNEES__", json.dumps(donnees, separators=(",", ":")))
                .replace("__PHOTO_B64__", photo_b64)
                .replace("__ORTHO_B64__", ortho_b64))
        f_out = sortie / f"calage_PV{v['num']}.html"
        octets = html.encode("utf-8")
        f_out.write_bytes(octets)            # pas de write_text : evite la conversion CRLF
        relu = f_out.read_bytes()            # relecture : detecte un fichier tronque ou corrompu
        if relu != octets:
            raise RuntimeError(f"ecriture incomplete ou corrompue : {f_out} "
                               f"({len(relu)} octets relus pour {len(octets)} ecrits). "
                               f"Si le dossier est synchronise par OneDrive, generer ailleurs.")
        produits.append(f_out)
        res_o = (ortho_bbox[2] - ortho_bbox[0]) / o_larg
        print(f"  PV {v['num']} : {f_out.name} ({f_out.stat().st_size/1e6:.1f} Mo) | "
              f"projet a {dist:.0f} m, azimut de depart {az0:.0f} deg "
              f"(BE : {v['cardinal'] or '?'}), f = {f_px:.0f} px | "
              f"ortho {o_larg}x{o_haut} a {res_o:.2f} m/px | "
              + (f"soleil {soleil['azimut']:.0f} deg / {soleil['elevation']:.0f} deg"
                 if soleil else "soleil inconnu"))
    return produits


# Variante B du meme site : la photo IMG_6941 a ete prise a l'angle sud-est de
# CETTE implantation (cloture a 4 m, premieres tables a 19 m), pas de la 10A.
CONFIG_SARNOIS_B = dict(CONFIG_SARNOIS, nom="Sarnois-10B",
    dxf=HERE / "exemples" / "sarnois-B" / "2026_08_27-IMP-DEV-Fixe-IND10b_V2.dxf")

# Reportage paysager du bureau d'etudes (Antea Group, etude d'impact A135824),
# photos 9 et 10 de la figure 45. Extraites du Word : ni EXIF, ni GPS, ni date, et
# 0,35 a 0,42 Mpx apres compression Word. Les positions viennent de la carte de
# localisation, calee sur la pointe sud du parc ; pour la photo 10 le chemin OSM
# le plus proche tombe a 11 m de cette estimation, ce qui la confirme. La focale
# n'est pas connue : elle est laissee au solveur, ce qui impose deux points hauts.
CONFIG_SARNOIS_BE = dict(CONFIG_SARNOIS_B, nom="Sarnois-10B-reportage-BE",
    photo_largeur=1600, photo_qualite=92, ortho_marge_m=160.0, marge_m=200.0,
    vues=[
        {"num": 9, "photo": HERE / "exemples" / "sarnois-B" / "reportage-BE" / "BE_09_acces-sud.jpg",
         "lon": 1.91814, "lat": 49.68031, "cardinal": "nord"},
        {"num": 10, "photo": HERE / "exemples" / "sarnois-B" / "reportage-BE" / "BE_10_chemin-ouest.jpg",
         "lon": 1.91684, "lat": 49.68164, "cardinal": "est"},
    ])

PROJETS = {"saint-cyr": CONFIG, "sarnois": CONFIG_SARNOIS, "sarnois-b": CONFIG_SARNOIS_B,
           "sarnois-be": CONFIG_SARNOIS_BE}

if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    cfg = CONFIG
    if args and args[0] in PROJETS:
        cfg = PROJETS[args.pop(0)]
    num = int(args[0]) if args and args[0].isdigit() else None
    dossier = args[1] if len(args) > 1 else (args[0] if args and not args[0].isdigit() else None)
    preparer(cfg, num, dossier)
