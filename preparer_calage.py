#!/usr/bin/env python3
"""Fabrique la page de calage d'une vue : photo, orthophoto, plan, solveur.

CE QUE LA PAGE SERT A FAIRE
----------------------------
Retrouver la POSE — azimut, tangage, roulis, et au besoin la position — en
cliquant des couples de points : un repère dans la photo, le même sur
l'orthophoto. C'est la seule étape de la chaîne qui demande un œil humain et
qu'aucune mesure ne remplace, et c'est aussi celle qui coûte le moins : la
page est un fichier autonome, elle s'ouvre dans un navigateur, et rien ne se
rend tant qu'elle n'est pas close.

POURQUOI ELLE N'EST PAS FACULTATIVE
------------------------------------
Le cap EXIF d'un téléphone ne vaut rien pour cet usage. Mesuré sur les 25
clichés de Sarnois, le compas se trompe de **28 à 47 degrés**, et parfois bien
plus : la vue 6 annonce 27,8 degrés là où quatre mâts d'éoliennes, recalés sur
leurs positions OpenStreetMap, donnent **340,7 degrés à 0,4 près**. Un montage
monté sur le cap EXIF ne se pose sur rien.

La POSITION, elle, est utilisable telle quelle quand le premier ouvrage visible
est à plus d'une vingtaine de mètres — voir `garde_prise_de_vue`, qui le dit en
chiffres avant qu'on ouvre cette page.

CE QUE LA PAGE RECOIT
----------------------
Un bloc JSON et deux images, dans un gabarit HTML figé (`gabarits/calage.html`,
extrait de l'outil validé sur Saint-Cyr) :

  - la PHOTO, réduite pour que le fichier reste manipulable ;
  - l'ORTHOPHOTO IGN de l'emprise, qui sert de plan cliquable ;
  - le MODELE DE TERRAIN, pour que chaque point du plan porte son altitude ;
  - la GEOMETRIE du projet en Lambert 93, altitudes NGF ;
  - le SOLEIL à l'instant du cliché, pour juger des ombres ;
  - une POSE DE DEPART, qui n'a pas besoin d'être bonne — seulement plausible.

LE PLAN EST UN DXF OU UN CONTRAT, indifferemment : un dossier
`geometries.gpkg` + `projet.json` ecrit par `generateur-dp`, ou un DXF du
bureau d'etudes. Le but etant de se passer du BE, c'est le contrat qui devient
l'entree normale.

⚠️ LA PHOTO DOIT ETRE CELLE SORTIE DU TELEPHONE. Une carte `photos-geoloc`
reencode ses photos en 1280 px SANS metadonnees : plus de focale, donc plus de
calage possible sans la resoudre. Le rapport, lui, sert a autre chose — il
porte la position REPLACEE a la main et le cap CALIBRE, qui valent mieux que
l'EXIF brut. On donne donc les deux : la photo d'origine pour l'optique, le
rapport pour la pose de depart.

Usage :
    python preparer_calage.py --projet Gannay IMG_0001.jpg
    python preparer_calage.py contrat/ photo.jpg sortie.html
    python preparer_calage.py plan.dxf photo.jpg sortie.html --azimut 245
    python preparer_calage.py contrat/ photo.jpg sortie.html         --rapport "Photos geolocalisees.html" --rogner-bas 260
"""
import argparse
import base64
import io as _io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

import dossiers
import lecture_contrat
import preparer_vue
import terrain

HERE = Path(__file__).resolve().parent
GABARIT = HERE / "gabarits" / "calage.html"

#: Largeur a laquelle la photo est reduite dans la page. Au-dela, le fichier
#: depasse la dizaine de megaoctets et le navigateur rame au zoom.
LARGEUR_PHOTO = 2720

#: Resolution de l'orthophoto, en metres par pixel, et marge autour de
#: l'emprise utile.
RESOLUTION_ORTHO = 0.25
MARGE_ORTHO = 60.0

#: Marge du modele de terrain autour de l'emprise, en metres.
MARGE_MNT = 150.0


def _b64_jpeg(im, qualite=86):
    tampon = _io.BytesIO()
    im.convert("RGB").save(tampon, "JPEG", quality=qualite, optimize=True)
    return base64.b64encode(tampon.getvalue()).decode("ascii")


def _emprise(scn, est, nord, marge):
    """Boite englobant le projet ET le point de vue.

    Le point de vue en fait partie : une orthophoto qui ne le contiendrait pas
    ne permettrait pas de cliquer les reperes proches de l'operateur, qui sont
    justement les plus precis.
    """
    pts = [(float(p[0]), float(p[1])) for t in scn.tables for p in t.q]
    for objs in scn.lignes.values():
        for o in objs:
            pts += [(float(x), float(y)) for x, y in o["pts"]]
    pts.append((est, nord))
    a = np.asarray(pts, float)
    return (a[:, 0].min() - marge, a[:, 1].min() - marge,
            a[:, 0].max() + marge, a[:, 1].max() + marge)


def point_du_rapport(rapport, nom_photo, exiger=False):
    """Position et cap d'une photo, lus dans une carte `photos-geoloc`.

    ⚠️ LE POINT DU RAPPORT VAUT MIEUX QUE L'EXIF, et c'est tout l'interet de
    le lire. Le chef de projet y REPLACE le point sur le fond satellite et y
    calibre le cone de visee ; l'EXIF, lui, porte la position brute du
    telephone — 5 a 10 m — et un cap compas mesure faux de 28 a 47 degres sur
    les vingt-cinq cliches de Sarnois.

    La carte range la position saisie dans `lat`/`lon` (valeur DEDUITE de
    `lat_brut` et `lat_manuel`) et le cap dans `cap`. Rend None si la photo
    n'y figure pas — auquel cas l'EXIF reprend la main.

    ⚠️ `nom_photo` DESIGNE L'ENTREE DE LA CARTE, PAS FORCEMENT LE FICHIER. Le
    dossier d'un chef de projet range rarement les photos sous le nom que la
    carte leur donne : a Gannay, la vue de cap 314 y figure sous
    `20260821_110154AMByGPSMapCamera.jpg` et se trouve au dossier sous
    `Photo 2 - PHOM.jpeg` et `image00012.jpeg` — deux noms pour un seul
    fichier, empreintes identiques. `exiger` sert alors a nommer l'entree a la
    main, et a REFUSER plutot que de retomber en silence sur un EXIF qui,
    justement, n'a pas de position.
    """
    s = Path(rapport).read_text(encoding="utf-8", errors="replace")
    m = re.search(r'<script id="donnees-carte"[^>]*>(.*?)</script>', s, re.S)
    if not m:
        if exiger:
            raise ValueError(f"{Path(rapport).name} n'est pas une carte "
                             f"photos-geoloc : pas de bloc donnees-carte.")
        return None
    points = json.loads(m.group(1)).get("points", [])
    cible = Path(nom_photo).stem.lower()
    for p in points:
        if Path(str(p.get("nom", ""))).stem.lower() != cible:
            continue
        if p.get("lat") is None or p.get("lon") is None:
            if exiger:
                raise ValueError(f"le point {p.get('nom')!r} de la carte n'a "
                                 f"pas de position.")
            return None
        return {"lat": float(p["lat"]), "lon": float(p["lon"]),
                "cap": None if p.get("cap") is None else float(p["cap"]),
                "source": str(p.get("source_position") or "?")}
    if exiger:
        raise ValueError(
            f"aucun point nomme {nom_photo!r} dans {Path(rapport).name}. "
            f"Points de la carte : "
            + ", ".join(str(p.get("nom")) for p in points if not p.get("masque")))
    return None


def preparer(plan, photo, sortie, azimut=None, tangage=0.0, roulis=0.0,
             hauteur_oeil=1.60, rogner_bas=0, titre=None, rapport=None,
             vue=None, verbose=True):
    """Ecrit la page de calage. Rend le dictionnaire de depart.

    `plan` est un DXF ou un dossier de contrat, indifferemment.
    `rapport` est une carte `photos-geoloc` : si la photo y figure, sa
    position replacee et son cap calibre priment sur l'EXIF.
    """
    scn = lecture_contrat.lire_plan(plan, verbose=verbose)
    ex = preparer_vue.exif_photo(photo)
    if ex["f_px"] is None:
        raise ValueError(
            f"{Path(photo).name} n'a pas de focale EXIF. Une carte "
            f"photos-geoloc ne la porte pas non plus : elle reencode les "
            f"photos sans metadonnees. Il faut le fichier SORTI DU TELEPHONE.")

    pt = (point_du_rapport(rapport, vue or photo, exiger=bool(vue))
          if rapport else None)
    if pt is not None:
        lon, lat = pt["lon"], pt["lat"]
        if azimut is None and pt["cap"] is not None:
            azimut = pt["cap"]
        if verbose:
            print(f"  position du rapport ({pt['source']}) : "
                  f"{lat:.6f}, {lon:.6f}"
                  + (f" | cap {pt['cap']:.0f} deg" if pt["cap"] is not None
                     else " | sans cap"))
    elif ex["lon"] is not None:
        lon, lat = ex["lon"], ex["lat"]
        if verbose:
            print(f"  position EXIF (brute, 5 a 10 m) : {lat:.6f}, {lon:.6f}")
    else:
        raise ValueError(
            f"{Path(photo).name} n'a ni geolocalisation EXIF ni point dans le "
            f"rapport fourni. Sans position de depart, la page ne s'ouvre sur "
            f"rien.")
    est, nord = (float(v) for v in terrain.l93(lon, lat))

    im = Image.open(photo)
    if rogner_bas:
        # LE BANDEAU DE GPS MAP CAMERA N'EST PAS DE LA PHOTO. Le laisser
        # decale le centre optique vers le haut et fausse le tangage.
        im = im.crop((0, 0, im.width, im.height - rogner_bas))
    f_px = ex["f_px"] * LARGEUR_PHOTO / ex["largeur"]
    if im.width > LARGEUR_PHOTO:
        im = im.resize((LARGEUR_PHOTO, round(im.height * LARGEUR_PHOTO / im.width)),
                       Image.LANCZOS)
    else:
        f_px = ex["f_px"]

    bbox = _emprise(scn, est, nord, MARGE_ORTHO)
    mnt = terrain.charger_mnt(bbox, pas=5.0, marge=MARGE_MNT, verbose=verbose)
    octets_ortho, ob, ol, oh = terrain.charger_ortho(
        bbox, resolution=RESOLUTION_ORTHO, verbose=verbose)
    geom = preparer_vue.geometrie_l93(scn, mnt)

    soleil = None
    if ex["horodatage"]:
        try:
            soleil = preparer_vue.position_soleil(ex["horodatage"], lat, lon)
        except Exception:                                     # noqa: BLE001
            soleil = None

    if azimut is None:
        # A DEFAUT DE CAP, LA MEILLEURE VISEE — pas zero. Le compas EXIF est
        # faux de plusieurs dizaines de degres ; partir de la visee qui montre
        # le plus de projet met l'operateur a quelques degres de la solution
        # au lieu de plusieurs centaines.
        import garde_prise_de_vue as G
        pts = G.points_projet(scn, hautes_seulement=True)
        az = np.degrees(np.arctan2(pts[:, 0] - est, pts[:, 1] - nord)) % 360
        champ = 2 * np.degrees(np.arctan(im.width / (2 * f_px)))
        azimut = G._meilleure_visee(az, float(champ))
        if verbose:
            print(f"  azimut de depart : {azimut:.0f} deg (meilleure visee)")

    depart = {"est": round(est, 2), "nord": round(nord, 2),
              "hauteur": hauteur_oeil,
              "azimut": float(azimut),
              "tangage": float(tangage), "roulis": float(roulis),
              "f_px": round(f_px, 1)}
    donnees = {
        "nom_court": Path(photo).stem,
        "photo": {"largeur": im.width, "hauteur": im.height},
        "ortho": {"xmin": ob[0], "ymin": ob[1], "xmax": ob[2], "ymax": ob[3],
                  "largeur": ol, "hauteur": oh},
        "mnt": mnt.vers_json(),
        "geom": geom,
        "cloture_h": 2.0,
        "soleil": soleil,
        "depart": depart,
    }

    sous_titre = (
        f"{ex['appareil']} &middot; {ex['largeur']}&times;{ex['hauteur']}"
        f"{' (recadr&eacute;e)' if ex['rognee'] else ' (format natif)'}"
        f" &middot; {ex['f35']:.0f} mm &eacute;q. 35 &middot; {ex['horodatage']}"
        f"<br>GPS {lat:.6f}, {lon:.6f} &middot; sol "
        f"{mnt.altitude(est, nord):.1f} m NGF &middot; azimut de d&eacute;part "
        f"{depart['azimut']:.0f}&deg;"
        + (f" &middot; soleil {soleil['azimut']:.0f}&deg;/"
           f"{soleil['elevation']:.0f}&deg;" if soleil else ""))
    page = GABARIT.read_text(encoding="utf-8")
    page = (page.replace("__TITRE__", titre or f"Calage &mdash; {Path(photo).stem}")
                .replace("__SOUS_TITRE__", sous_titre)
                .replace("__FICHIER__", Path(photo).name)
                .replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False))
                .replace("__PHOTO__", _b64_jpeg(im))
                .replace("__ORTHO__",
                         base64.b64encode(octets_ortho).decode("ascii")))
    Path(sortie).write_text(page, encoding="utf-8")
    if verbose:
        print(f"  {Path(sortie).name} : photo {im.width}x{im.height}, "
              f"f_px {f_px:.0f}, ortho {ol}x{oh}, {len(page) / 1e6:.1f} Mo")
    return depart


def depuis_projet(nom, photo, sortie=None, rapport=None):
    """Resout plan, photo, sortie et rapport dans un dossier de projet.

    C'est la forme qu'on tape quinze fois : `--projet Gannay photo.jpg`. Le
    contrat, la carte et l'atelier s'y trouvent seuls, et la page ne PEUT PAS
    atterrir dans le mauvais projet — `dossiers.projet` refuse un fragment
    ambigu. Sans cela « Loire » designerait a la fois Gannay-sur-Loire et
    Saint-Aubin-sur-Loire, et un montage depose au mauvais endroit ressemble
    a un montage.
    """
    base = dossiers.projet(nom)
    ph = Path(photo)
    if not ph.exists():
        candidats = [f for f in base.rglob(ph.name) if f.is_file()]
        if len(candidats) != 1:
            raise ValueError(
                f"{ph.name} : {len(candidats)} fichier(s) de ce nom sous "
                f"{base.name}")
        ph = candidats[0]
    if rapport is None:
        cartes = [h for h in base.glob("*.htm*") if h.is_file()]
        rapport = cartes[0] if len(cartes) == 1 else None
    if sortie is None:
        sortie = dossiers.montages(nom) / f"calage_{ph.stem}.html"
    return dossiers.contrat(nom), ph, Path(sortie), rapport


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--projet", help="nom (ou fragment) d'un dossier de "
                                    "projets/ : contrat, carte et dossier de "
                                    "sortie s'y trouvent seuls")
    p.add_argument("args", nargs="*", metavar="...",
                   help="avec --projet : la PHOTO seule (et au besoin la "
                        "sortie). Sans : PLAN PHOTO SORTIE.")
    p.add_argument("--azimut", type=float,
                   help="azimut de depart ; a defaut, la meilleure visee")
    p.add_argument("--tangage", type=float, default=0.0)
    p.add_argument("--roulis", type=float, default=0.0)
    p.add_argument("--oeil", type=float, default=1.60)
    p.add_argument("--titre")
    p.add_argument("--rogner-bas", type=int, default=0,
                   help="pixels a retirer en bas (bandeau GPS Map Camera)")
    p.add_argument("--rapport",
                   help="carte photos-geoloc : sa position replacee et son "
                        "cap calibre priment sur l'EXIF")
    p.add_argument("--vue",
                   help="nom de l'entree DANS LA CARTE, quand le fichier "
                        "porte un autre nom. Refuse au lieu de retomber sur "
                        "l'EXIF.")
    a = p.parse_args()
    if a.projet:
        if not 1 <= len(a.args) <= 2:
            p.error("avec --projet, donner la PHOTO (et au besoin la sortie)")
        plan, photo, sortie, rapport = depuis_projet(
            a.projet, a.args[0], a.args[1] if len(a.args) > 1 else None,
            a.rapport)
    elif len(a.args) == 3:
        plan, photo, sortie, rapport = (*a.args, a.rapport)
    else:
        p.error("donner PLAN PHOTO SORTIE, ou --projet NOM PHOTO")
    preparer(plan, photo, sortie, azimut=a.azimut, tangage=a.tangage,
             roulis=a.roulis, hauteur_oeil=a.oeil, rapport=rapport,
             vue=a.vue, rogner_bas=a.rogner_bas, titre=a.titre)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
