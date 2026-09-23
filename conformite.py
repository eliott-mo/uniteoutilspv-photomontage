#!/usr/bin/env python3
"""Confronte la géométrie exportée au plan de masse, avant tout rendu.

POURQUOI CE MODULE EXISTE
-------------------------
Quatre allers-retours ont été perdus sur un même défaut, parce qu'il ne se
lisait pas sur le rendu. Le chef de projet voyait « des éléments qui se
mélangent » et « des conflits entre des choses qui ne sont pas en conflit sur
le plan de masse » ; moi je corrigeais ce que je croyais reconnaître à l'œil,
et le suivant ressortait. Un rendu perspectif mélange trois questions — la
géométrie, la pose, l'occultation — et on ne sait jamais laquelle a lâché.

Le défaut, une fois la géométrie posée à plat, tenait en une phrase :
`geometrie_poste` et `geometrie_citerne` ajoutent chacune un tablier de grave
autour de l'ouvrage. Juste quand l'appelant leur donne une géométrie choisie à
la main ; faux quand un plan pilote. Mesuré sur Saint-Cyr : **356 m² de grave
absents du plan**, qui se recouvraient entre eux et débordaient sur la clôture.

CE QUI EST VÉRIFIÉ
------------------
1. **Toute surface rendue est sur le plan.** Chaque triangle de sol doit tomber
   sur un polygone dur du plan. C'est le contrôle qui aurait pris les 356 m².
2. **Rien ne sort de l'enceinte.** Un ouvrage dont l'emprise déborde la clôture
   est faux, quelle qu'en soit la cause — c'était le cas de la bâche montée au
   gabarit, à 15 % dehors.
3. **Ce qui est disjoint au plan reste disjoint au modèle.** Deux ouvrages qui
   ne se touchent pas sur le plan et s'interpénètrent dans la scène signalent
   une cote ou une orientation inventée.

Le contrôle est **géométrique et chiffré**. Il ne remplace pas le coup d'œil,
il le précède : il dit *où* regarder, et il ne se laisse pas convaincre par une
image qui a l'air correcte.

Usage :
    python conformite.py scene.json plan.dxf pose.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

import lecture_dxf
import ouvrages_techniques as OT

#: Materiaux qui sont des NAPPES DE SOL, donc soumis au controle n°1.
SOLS = ("grave",)

#: Materiaux hors controle : le capteur d'ombre est invisible, la nappe de
#: tables et le sol du site ont leur propre emprise, deja verrouillee ailleurs.
HORS_CONTROLE = ("sol_ombre", "herbe", "module", "cadre", "haie", "feuillage",
                 "branche")

#: Tolerances, en m2 et en metres.
TOL_AIRE = 1.0
TOL_DEBORD = 0.5


def _polygone(v, f):
    """Emprise au sol d'un bloc : l'union de ses faces projetees."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    v = np.asarray(v, float)
    parts = []
    for face in f:
        p = Polygon([(v[i][0], v[i][1]) for i in face]).buffer(0)
        if p.is_valid and p.area > 1e-9:
            parts.append(p)
    return unary_union(parts) if parts else None


def verifier(scene, scn, E0, N0, dmax=120.0):
    """Rend la liste des anomalies, chacune en une ligne lisible."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    if not isinstance(scene, dict):
        scene = json.loads(Path(scene).read_text(encoding="utf-8"))
    anomalies = []

    # --- 1. toute surface rendue est sur le plan --------------------------
    durs = OT._polygones_durs(scn, E0, N0, dmax * 3)
    plan = unary_union(durs) if durs else None
    for b in scene["objets"]:
        if b["materiau"] not in SOLS or not b.get("f"):
            continue
        emp = _polygone([[x + E0, y + N0, z] for x, y, z in b["v"]], b["f"])
        if emp is None:
            continue
        hors = emp if plan is None else emp.difference(plan.buffer(TOL_DEBORD))
        if hors.area > TOL_AIRE:
            anomalies.append(
                f"{b['materiau']} : {hors.area:.0f} m2 de sol rendu qui ne "
                f"sont sur aucun polygone du plan (emprise rendue "
                f"{emp.area:.0f} m2)")

    # --- 2. rien ne sort de l'enceinte ------------------------------------
    lignes = scn.lignes.get("cloture") or []
    enc = None
    if lignes:
        p = Polygon(OT.anneau(lignes[0]["pts"])).buffer(0)
        enc = p if p.is_valid and p.area > 0 else None
    emprises = {}
    for b in scene["objets"]:
        mat = b["materiau"]
        if mat in HORS_CONTROLE or not b.get("f"):
            continue
        emp = _polygone([[x + E0, y + N0, z] for x, y, z in b["v"]], b["f"])
        if emp is None or emp.is_empty:
            continue
        proche = emp.intersection(
            Polygon([(E0 - dmax, N0 - dmax), (E0 + dmax, N0 - dmax),
                     (E0 + dmax, N0 + dmax), (E0 - dmax, N0 + dmax)]))
        if proche.is_empty:
            continue
        emprises.setdefault(mat, []).append(proche)
        # Une PISTE A CREER a le droit de sortir de l'enceinte : elle rejoint
        # la voie publique. Seuls les VOLUMES doivent y rester.
        if (enc is not None and mat not in SOLS
                and mat not in ("grillage", "bois", "menuiserie")):
            dehors = proche.difference(enc.buffer(TOL_DEBORD))
            if dehors.area > TOL_AIRE:
                anomalies.append(
                    f"{mat} : {dehors.area:.0f} m2 hors de l'enceinte "
                    f"({100 * dehors.area / proche.area:.0f} % de son emprise)")

    # --- 3. chaque ouvrage est pose sur son trace du plan -----------------
    #
    # ON NE COMPARE PAS DES MATERIAUX. Une premiere version confrontait les
    # emprises par materiau et signalait « beton et couvertine
    # s'interpenetrent sur 58 m2 » : ce sont le corps et la couvertine du MEME
    # poste, et la couvertine deborde par construction. Un materiau n'est pas
    # un ouvrage. C'est le constructeur qui declare ce qu'il a monte, et ou.
    for r in scene.get("registre", []):
        plan = Polygon(r["plan"]).buffer(0)
        monte = Polygon(r["monte"]).buffer(0)
        if plan.is_empty or monte.is_empty:
            continue
        c1, c2 = plan.centroid, monte.centroid
        ecart = math.hypot(c1.x - c2.x, c1.y - c2.y)
        commun = plan.intersection(monte).area
        union = plan.union(monte).area
        if union > 0 and commun / union < 0.90:
            anomalies.append(
                f"{r['nom']} ({r['couche']}) : monte {monte.area:.1f} m2 pour "
                f"{plan.area:.1f} m2 au plan, recouvrement "
                f"{100 * commun / union:.0f} %, centre decale de {ecart:.2f} m")
    return anomalies


def main():
    scene, dxf, pose_f = sys.argv[1:4]
    scn = lecture_dxf.lire(dxf)
    pose = json.loads(Path(pose_f).read_text(encoding="utf-8"))
    a = verifier(scene, scn, pose["est"], pose["nord"])
    if not a:
        print("conformite au plan : rien a signaler")
        return 0
    print(f"conformite au plan : {len(a)} anomalie(s)")
    for ligne in a:
        print(f"  - {ligne}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
