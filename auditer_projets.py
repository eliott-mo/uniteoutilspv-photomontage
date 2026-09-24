#!/usr/bin/env python3
"""Passe en revue un dossier de projets, avant d'en monter un seul.

CE QUE CET AUDIT SERT A EVITER
-------------------------------
Le pilote de Saint-Cyr a coûté quatre allers-retours et n'a rien livré, pour
une raison qu'un contrôle d'une seconde aurait donnée : les photos étaient
prises trop près. Et chaque plan apporte ses conventions — `VAL-PDL` doublant
`UNI_PDL`, une aire VRD lue comme un conteneur, des tables tantôt en blocs,
tantôt en polylignes 3D, tantôt en quatre segments. Chacune coûte un
aller-retour la première fois qu'on la rencontre, et rien la fois suivante.

Cet audit les fait toutes remonter **d'un coup**, sur tous les projets, avant
qu'on ait passé du temps sur aucun. Il ne rend rien, ne cale rien, n'écrit
rien : il lit et il dit.

CE QU'IL REGARDE
----------------
  - le PLAN : se lit-il, combien de tables, quelles couches ne sont mappées
    par rien, et le repère est-il bien du Lambert 93 ;
  - les POINTS DE VUE du rapport photo, passés au garde-fou de prise de vue ;
  - ce qui MANQUE : plan, rapport, tableau bilan.

⚠️ LA FOCALE EST SUPPOSEE quand les photos elles-mêmes ne sont pas au dossier.
Le rapport ne porte que des vignettes. Un 26 mm équivalent sur un capteur 4:3
est le cas courant, et le critère décisif — la distance au premier ouvrage
visible — n'en dépend pas. Les pourcentages, eux, en dépendent : à vérifier
sur les photos d'origine avant de conclure sur une vue limite.

Usage :
    python auditer_projets.py projets
"""
import argparse
import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

import camera
import garde_prise_de_vue as G
import lecture_dxf
import terrain

#: Taille et focale supposees quand la photo n'est pas au dossier.
LARGEUR_SUPPOSEE, HAUTEUR_SUPPOSEE, EQ35_SUPPOSEE = 4032, 3024, 26.0

#: Ce qui marque un export HelioScope brut : il n'est ni georeference, ni
#: nomme comme un plan PVcase. Il doit passer par `generateur-dp` (lot 2), qui
#: reconstitue le georeferencement par la resolution de l'entite IMAGE.
COUCHES_HELIOSCOPE = {"Modules", "Field_Segments"}

#: Commentaire du rapport photo qui designe une vue de PHOTOMONTAGE. Les
#: autres servent aux pieces DP 7 et DP 8, ou une vue rapprochee est normale :
#: les recaler serait un faux signal.
USAGE_PHOTOMONTAGE = "photomontage"

#: Bornes du Lambert 93 metropolitain, pour reconnaitre un plan deja
#: georeference d'un export HelioScope en repere local.
L93_E = (99000.0, 1310000.0)
L93_N = (6000000.0, 7200000.0)


def _plans(dossier):
    """Chemins de DXF du projet, en extrayant ceux qui sont dans un zip."""
    out = [p for p in dossier.glob("*.dxf")]
    for z in dossier.glob("*.zip"):
        try:
            with zipfile.ZipFile(z) as arc:
                noms = [n for n in arc.namelist() if n.lower().endswith(".dxf")]
                if not noms:
                    continue
                tmp = Path(tempfile.mkdtemp(prefix="audit_"))
                for n in noms:
                    arc.extract(n, tmp)
                    out.append(tmp / n)
        except zipfile.BadZipFile:
            continue
    return out


def _vues(dossier):
    """Points de vue VISIBLES du rapport photo, dans l'ordre de la carte."""
    for h in list(dossier.glob("*.html")) + list(dossier.glob("*.HTML")):
        s = io.open(h, encoding="utf-8", errors="replace").read()
        m = re.search(r'<script id="donnees-carte"[^>]*>(.*?)</script>', s, re.S)
        if not m:
            continue
        pts = json.loads(m.group(1)).get("points", [])
        vis = sorted((p for p in pts if not p.get("masque")),
                     key=lambda p: p.get("ordre", 0))
        return h.name, len(pts), vis
    return None, 0, []


def _repere(scn):
    """Dit si les tables sont en Lambert 93 metropolitain."""
    q = np.array([t.q for t in scn.tables])
    e, n = q[:, :, 0].mean(), q[:, :, 1].mean()
    return (L93_E[0] < e < L93_E[1]) and (L93_N[0] < n < L93_N[1]), e, n


def auditer(dossier, verbose=True):
    """Audite un projet. Rend un dictionnaire de constats."""
    dossier = Path(dossier)
    c = {"projet": dossier.name, "anomalies": []}

    plans = _plans(dossier)
    scn = None
    for p in plans:
        try:
            scn = lecture_dxf.lire(p)
            c["plan"] = p.name
            break
        except Exception as e:                                # noqa: BLE001
            couches = {x.dxf.layer for x in lecture_dxf.ezdxf.readfile(p).modelspace()}
            if COUCHES_HELIOSCOPE <= couches:
                c["helioscope"] = p.name
                c["anomalies"].append(
                    f"{p.name} : export HelioScope brut (couches "
                    f"{', '.join(sorted(COUCHES_HELIOSCOPE))}). Il n'est pas "
                    f"georeference : il doit passer par le lot 2 de "
                    f"generateur-dp, qui ecrit le contrat, puis par "
                    f"lecture_contrat.")
            else:
                c["anomalies"].append(
                    f"{p.name} : {type(e).__name__} {str(e)[:70]}")
    if scn is None:
        return c

    c["tables"] = len(scn.tables)
    c["lignes"] = {k: len(v) for k, v in sorted(scn.lignes.items()) if v}
    l93, e, n = _repere(scn)
    c["lambert93"] = l93
    if not l93:
        c["anomalies"].append(
            f"plan hors Lambert 93 (centre {e:.0f}, {n:.0f}) : c'est un export "
            f"HelioScope en repere local, il faut passer par le contrat de "
            f"generateur-dp pour le georeferencer")

    d = lecture_dxf.ezdxf.readfile(plans[0]) if plans else None
    if d is not None:
        couches = {x.dxf.layer for x in d.modelspace()}
        c["non_mappees"] = sorted(
            l for l in couches
            if not lecture_dxf._categorie(l)
            and lecture_dxf.MOTIF_TABLES not in l
            and not l.startswith("-Topo") and l != "0")

    nom_html, total, vues = _vues(dossier)
    c["rapport"] = nom_html
    c["vues_total"], c["vues"] = total, []
    if vues and l93:
        f_px = camera.focale_px_depuis_exif(LARGEUR_SUPPOSEE,
                                            HAUTEUR_SUPPOSEE, EQ35_SUPPOSEE)[0]
        for i, v in enumerate(vues, 1):
            est, nord = (float(x) for x in terrain.l93(v["lon"], v["lat"]))
            cap = v.get("cap")
            try:
                r = G.evaluer(scn, est, nord, LARGEUR_SUPPOSEE, HAUTEUR_SUPPOSEE,
                              f_px, azimut=float(cap) if cap is not None else None,
                              sigma=G.SIGMA_RELEVE)
            except Exception as ex:                           # noqa: BLE001
                c["vues"].append({"n": i, "nom": v["nom"],
                                  "erreur": str(ex)[:60]})
                continue
            m = r.mesures
            com = (v.get("commentaire") or "").strip()
            c["vues"].append({
                "n": i, "nom": v["nom"], "commentaire": com,
                "phom": USAGE_PHOTOMONTAGE in com.lower(),
                "cap": cap, "cap_connu": r.cap_connu, "ok": r.exploitable,
                "d": m.get("distance_premier_ouvrage_visible_m"),
                "cloture_pct": m.get("part_ouvrage_proche_pct"),
                "cadre_pct": m.get("part_projet_dans_le_cadre_pct"),
                "motifs": r.motifs,
            })
    return c


def imprimer(c):
    print(f"\n=== {c['projet']}")
    if "plan" in c:
        print(f"  plan : {c['plan']} | {c.get('tables', 0)} tables | "
              + ", ".join(f"{k}:{v}" for k, v in (c.get("lignes") or {}).items()))
    if c.get("non_mappees"):
        print(f"  couches non mappees : {', '.join(c['non_mappees'])}")
    if c.get("rapport"):
        print(f"  rapport : {c['rapport']} | {len(c['vues'])} vues visibles "
              f"sur {c['vues_total']}")
    for a in c["anomalies"]:
        print(f"  ! {a}")
    if c.get("vues"):
        print(f"    {'':2s} {'fichier':26s} {'usage':13s} {'cap':>5s} "
              f"{'d_vis':>7s} {'clot':>6s} {'cadre':>6s}  verdict")
    for v in c.get("vues", []):
        if "erreur" in v:
            print(f"    {v['n']:2d} {v['nom'][:26]:26s} {v['erreur']}")
            continue
        cap = f"{v['cap']:5.0f}" if v["cap"] is not None else "    -"
        marque = ">>" if v["phom"] else "  "
        print(f" {marque} {v['n']:2d} {v['nom'][:26]:26s} {v['commentaire'][:13]:13s} "
              f"{cap} {v['d']:7.1f} {v['cloture_pct']:5.1f}% {v['cadre_pct']:5.0f}%  "
              f"{'OK' if v['ok'] else 'A REPRENDRE'}")
    phom = [v for v in c.get("vues", []) if v.get("phom")]
    if phom:
        bons = sum(1 for v in phom if v["ok"])
        print(f"    -> {len(phom)} vue(s) de photomontage, {bons} exploitable(s)")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("dossier", nargs="?", default="projets")
    a = p.parse_args()
    racine = Path(a.dossier)
    if not racine.is_dir():
        print(f"{racine} n'est pas un dossier")
        return 1
    for d in sorted(x for x in racine.iterdir() if x.is_dir()):
        imprimer(auditer(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
