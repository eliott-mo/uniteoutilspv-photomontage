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

Usage :
    python preparer_calage.py plan.dxf photo.jpg sortie.html
    python preparer_calage.py plan.dxf photo.jpg sortie.html --azimut 245
"""
import argparse
import base64
import io as _io
import json
from pathlib import Path

import numpy as np
from PIL import Image

import lecture_dxf
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


def preparer(plan, photo, sortie, azimut=None, tangage=0.0, roulis=0.0,
             hauteur_oeil=1.60, rogner_bas=0, titre=None, verbose=True):
    """Ecrit la page de calage. Rend le dictionnaire de depart."""
    scn = lecture_dxf.lire(plan)
    ex = preparer_vue.exif_photo(photo)
    if ex["lon"] is None:
        raise ValueError(f"{Path(photo).name} n'a pas de geolocalisation EXIF")
    if ex["f_px"] is None:
        raise ValueError(f"{Path(photo).name} n'a pas de focale EXIF")
    est, nord = (float(v) for v in terrain.l93(ex["lon"], ex["lat"]))

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
            soleil = preparer_vue.position_soleil(ex["horodatage"], ex["lat"],
                                                  ex["lon"])
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
        f"<br>GPS {ex['lat']:.6f}, {ex['lon']:.6f} &middot; sol "
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


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("plan")
    p.add_argument("photo")
    p.add_argument("sortie")
    p.add_argument("--azimut", type=float,
                   help="azimut de depart ; a defaut, la meilleure visee")
    p.add_argument("--tangage", type=float, default=0.0)
    p.add_argument("--roulis", type=float, default=0.0)
    p.add_argument("--oeil", type=float, default=1.60)
    p.add_argument("--titre")
    p.add_argument("--rogner-bas", type=int, default=0,
                   help="pixels a retirer en bas (bandeau GPS Map Camera)")
    a = p.parse_args()
    preparer(a.plan, a.photo, a.sortie, azimut=a.azimut, tangage=a.tangage,
             roulis=a.roulis, hauteur_oeil=a.oeil,
             rogner_bas=a.rogner_bas, titre=a.titre)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
