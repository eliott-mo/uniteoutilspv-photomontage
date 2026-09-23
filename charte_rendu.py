#!/usr/bin/env python3
"""Extrait une charte de rendu chiffree a partir de photomontages de reference.

Une paire avant / apres est un cadeau : elle isole au pixel pres ce que le
prestataire a peint. On n'apprend pas une image, mais on peut en MESURER les
regles, et ces mesures pilotent ensuite `montage.py` a la place de constantes
choisies a l'oeil.

Ce qui est mesure :
  - la LUMINANCE DES PANNEAUX rapportee a celle du ciel de la meme image. C'est
    un rapport, donc transposable d'une photo a l'autre, contrairement a une
    couleur absolue.
  - la TEINTE des panneaux, en ecart au gris.
  - la DENSITE D'OMBRE au sol : rapport apres / avant la ou le sol s'est assombri
    sans devenir un panneau.
  - l'AERATION : part du sol qui reste visible entre les rangees dans la bande
    occupee par la centrale. Une nappe opaque est le defaut le plus visible d'un
    rendu vectoriel.
  - la BRUME : derive de la luminance des panneaux avec l'eloignement.
  - la NETTETE DE BORD : largeur du degrade au bord de ce qui a ete ajoute.

Usage :
    python charte_rendu.py                 # mesure les references, ecrit charte_rendu.json
"""
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion, binary_dilation, gaussian_filter
from scipy.ndimage import label as _label

HERE = Path(__file__).resolve().parent
REFS = HERE / "exemples" / "references-HOCH"
SORTIE = HERE / "charte_rendu.json"

SEUIL_DIFF = 16          # ecart RGB a partir duquel on considere le pixel retouche
SEUIL_OMBRE = 10         # assombrissement minimal pour parler d'ombre


def _sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def paires(dossier=REFS):
    """Associe chaque 'avant' a son 'apres sans mesure' (les mesures ajoutent des haies)."""
    fichiers = list(dossier.glob("*.jpg")) + list(dossier.glob("*.png"))
    avant = {}
    apres = {}
    for f in fichiers:
        n = _sans_accents(f.name)
        m = re.match(r"vue\s+([abc])\s*-", n)
        if not m:
            continue
        vue = m.group(1).upper()
        if "avant" in n:
            avant[vue] = f
        elif "sans mesure" in n:
            apres[vue] = f
    return [(v, avant[v], apres[v]) for v in sorted(avant) if v in apres]


def _ciel(img, lum):
    """Luminance et couleur du ciel : la moitie haute, pixels clairs et bleutes."""
    h = img.shape[0]
    bande = img[: int(h * 0.45)]
    lb = lum[: int(h * 0.45)]
    m = (lb > np.percentile(lb, 55)) & (bande[..., 2] >= bande[..., 0] - 6)
    if m.sum() < 500:
        m = lb > np.percentile(lb, 70)
    return float(lb[m].mean()), bande[m].mean(axis=0)


def mesurer(f_avant, f_apres):
    a = np.array(Image.open(f_avant).convert("RGB")).astype(float)
    b = np.array(Image.open(f_apres).convert("RGB")).astype(float)
    if a.shape != b.shape:
        h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
        a, b = a[:h, :w], b[:h, :w]
    La, Lb = a.mean(axis=2), b.mean(axis=2)
    diff = np.abs(b - a).max(axis=2)
    touche = diff > SEUIL_DIFF
    l_ciel, c_ciel = _ciel(a, La)

    assombri = touche & ((La - Lb) > SEUIL_OMBRE)
    panneaux = assombri & (Lb < 0.58 * l_ciel)
    panneaux = binary_erosion(panneaux, np.ones((3, 3)))          # ecarte les bords mous
    ombres = assombri & ~binary_dilation(panneaux, np.ones((7, 7)))

    res = {"pixels_touches": int(touche.sum()), "part_touchee": float(touche.mean())}
    if panneaux.sum() > 2000:
        coul = b[panneaux].mean(axis=0)
        res["panneau_luminance_sur_ciel"] = round(float(Lb[panneaux].mean() / l_ciel), 4)
        res["panneau_rgb_median"] = [round(float(v), 1) for v in np.median(b[panneaux], axis=0)]
        res["panneau_ecart_type"] = round(float(Lb[panneaux].std()), 2)
        # teinte : ecart relatif de chaque canal a la moyenne
        res["panneau_teinte"] = [round(float(v / coul.mean()), 4) for v in coul]
        res["panneau_rgb_sur_ciel"] = [round(float(coul[k] / max(c_ciel[k], 1)), 4) for k in range(3)]
        # brume : luminance des panneaux selon la ligne d'image (proxy de distance)
        ys = np.nonzero(panneaux)[0]
        q = np.percentile(ys, [15, 85])
        haut = panneaux & (np.arange(panneaux.shape[0])[:, None] < q[0])
        bas = panneaux & (np.arange(panneaux.shape[0])[:, None] > q[1])
        if haut.sum() > 300 and bas.sum() > 300:
            res["brume_haut_sur_bas"] = round(float(Lb[haut].mean() / Lb[bas].mean()), 4)
        # aeration : dans la boite des panneaux, part de sol restee visible
        y0, y1 = int(ys.min()), int(ys.max())
        xs = np.nonzero(panneaux)[1]
        x0, x1 = int(xs.min()), int(xs.max())
        boite = panneaux[y0:y1 + 1, x0:x1 + 1]
        res["aeration_dans_la_bande"] = round(float(1.0 - boite.mean()), 4)
    # --- objets CLAIRS ajoutes : locaux techniques, citernes, cabanes.
    # Tout le reste de la mesure part de `assombri`, donc ne voit que ce qui est
    # plus sombre que le fond. Un prefabrique beton est plus clair que l'herbe :
    # sans cette passe, il echappe entierement a la charte.
    eclairci = touche & ((Lb - La) > SEUIL_OMBRE) & (Lb > 0.40 * l_ciel)
    eclairci = binary_erosion(eclairci, np.ones((3, 3)))
    lab, n = _label(eclairci)
    garde = np.zeros_like(eclairci)
    surfaces = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if len(ys) < 600:
            continue
        # On garde les taches COMPACTES, en esperant des volumes. Le controle
        # visuel des 18 dossiers montre que la recolte est en fait faite de
        # poteaux vus de face, de dessous de modules et de grillage : ne pas
        # lire le resultat comme une mesure de bati.
        c = np.stack([xs - xs.mean(), ys - ys.mean()])
        _, sv, _ = np.linalg.svd(c @ c.T / len(ys))
        if sv[1] <= 0 or (sv[0] / sv[1]) ** 0.5 > 4.0:
            continue
        if len(ys) / max((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1), 1) < 0.35:
            continue                                   # trop creux pour un volume plein
        garde |= (lab == k)
        surfaces.append(int(len(ys)))
    if garde.sum() > 1200:
        coul = b[garde].mean(axis=0)
        res["volume_clair_luminance_sur_ciel"] = round(float(Lb[garde].mean() / l_ciel), 4)
        res["volume_clair_teinte"] = [round(float(v / coul.mean()), 4) for v in coul]
        res["volume_clair_ecart_type"] = round(float(Lb[garde].std()), 2)
        res["volume_clair_nb_volumes"] = len(surfaces)
        res["volume_clair_pixels"] = int(garde.sum())
    if ombres.sum() > 1500:
        res["ombre_rapport"] = round(float((Lb[ombres] / np.maximum(La[ombres], 1)).mean()), 4)
        res["ombre_part_du_touche"] = round(float(ombres.sum() / max(touche.sum(), 1)), 4)
    # nettete de bord : largeur du degrade autour de ce qui a ete ajoute
    if panneaux.sum() > 2000:
        bord = binary_dilation(panneaux, np.ones((5, 5))) & ~binary_erosion(panneaux, np.ones((5, 5)))
        g = np.abs(gaussian_filter(Lb, 1.0) - Lb)
        res["bord_douceur"] = round(float(g[bord].mean()), 3)
    res["ciel_luminance"] = round(float(l_ciel), 1)
    res["ciel_rgb"] = [round(float(v), 1) for v in c_ciel]
    return res, panneaux, ombres, touche


def resumer(mesures):
    """Charte unique : MEDIANE des vues.

    Avec 37 paires, la mediane resiste aux cas limites (vue quasi vide, planche
    ou le masque attrape autre chose que les panneaux) la ou une moyenne se
    laisse tirer. Sur trois vues la question ne se posait pas ; a 37 elle compte.
    """
    cles = ("panneau_luminance_sur_ciel", "panneau_ecart_type", "brume_haut_sur_bas",
            "aeration_dans_la_bande", "ombre_rapport", "bord_douceur",
            "volume_clair_luminance_sur_ciel", "volume_clair_ecart_type")
    out = {}
    for k in cles:
        v = [m[k] for m in mesures.values() if k in m]
        if v:
            out[k] = round(float(np.median(v)), 4)
    tb = [m["volume_clair_teinte"] for m in mesures.values() if "volume_clair_teinte" in m]
    if tb:
        out["volume_clair_teinte"] = [round(float(x), 4) for x in np.median(tb, axis=0)]
    t = [m["panneau_teinte"] for m in mesures.values() if "panneau_teinte" in m]
    if t:
        out["panneau_teinte"] = [round(float(x), 4) for x in np.median(t, axis=0)]
    r = [m["panneau_rgb_sur_ciel"] for m in mesures.values() if "panneau_rgb_sur_ciel" in m]
    if r:
        out["panneau_rgb_sur_ciel"] = [round(float(x), 4) for x in np.median(r, axis=0)]
    return out


if __name__ == "__main__":
    mesures = {}
    for vue, fa, fb in paires():
        m, pan, omb, touche = mesurer(fa, fb)
        mesures[vue] = m
        print(f"\n=== vue {vue} : {fa.name}  ->  {fb.name}")
        for k, v in m.items():
            print(f"    {k:28s} {v}")
    charte = {"source": "exemples/references-HOCH (3 paires avant/apres, prestataire HOCH)",
              "vues": mesures, "charte": resumer(mesures)}
    SORTIE.write_text(json.dumps(charte, indent=1), encoding="utf-8")
    print("\n=== charte retenue ===")
    for k, v in charte["charte"].items():
        print(f"  {k:28s} {v}")
