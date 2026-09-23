#!/usr/bin/env python3
"""Recense les vues ou un masque VEGETAL s'interpose entre l'oeil et le projet.

Un photomontage compose le rendu PAR-DESSUS la photo : tout ce qui est calcule
passe devant tout ce qui est photographie. Un panneau a 300 m s'affiche donc
par-dessus une haie qui est a 40 m. Avant de batir la mecanique de detourage,
il faut savoir sur combien de vues le cas se presente.

CE QUI EST MESURE, ET CE QUI NE L'EST PAS. Pour chaque prise de vue, on tire
des lignes de visee vers l'emprise des tables et on cherche ou elles traversent
un boisement de l'orthophoto IGN. Puis, plutot que de PRESUMER une hauteur
d'arbre — c'est le biais de 15 a 30 px connu sur `arbitre_silhouette` — on
calcule la HAUTEUR QU'IL FAUDRAIT a cette vegetation pour cacher le haut des
panneaux. Le verdict se lit alors sans reglage :

    h requise < 2 m    une simple haie suffit
    2 a 6 m            haie champetre ordinaire
    6 a 15 m           il faut des arbres ; a verifier sur la photo
    > 15 m             rien de plausible ne cachera le projet

Le VERDICT, lui, porte sur la PART des visees barrees par une haie de
`h_plausible` — pas sur la mediane des seules visees qui rencontrent de la
vegetation. La nuance n'est pas academique : une vue dont deux visees sur
vingt-cinq sont barrees sortait « masque certain » alors que l'ouvrage est
visible a quatre-vingt-douze pour cent.

Ce qui n'est PAS traite : les masques batis, les talus, et tout ce qui est a
moins de 25 m de l'oeil et ne figure pas dans l'orthophoto comme boisement.
Ceux-la ne se reglent qu'au masque dessine.

Usage :
    python audit_masques.py [carte.png] [--json audit.json]
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

PAS = 3.0          # m, pas de marche le long de la visee
D_MIN = 25.0       # m ; en deca l'orthophoto ne distingue plus rien d'utile
MARGE = 15.0       # m, on s'arrete avant la cible pour ne pas compter le site
RESOLUTION = 1.5   # m, grille du masque de vegetation
H_PLAUSIBLE = 3.0  # m, hauteur d'une haie de limite parcellaire ordinaire


def _raster_boisements(bbox, resolution=RESOLUTION, verbose=True):
    """Masque booleen des boisements sur une grille reguliere."""
    import calage_paysage as cp
    # 2000 px : au-dela le WMS de la Geoplateforme repond 400, et 0,6 m de
    # resolution suffit a distinguer une haie de 2 m de large.
    TE, TN = cp.masque_boisements(bbox, resolution=0.60, max_px=2000)
    W = int((bbox[2] - bbox[0]) / resolution) + 1
    H = int((bbox[3] - bbox[1]) / resolution) + 1
    m = np.zeros((H, W), bool)
    j = ((TE - bbox[0]) / resolution).astype(int)
    i = ((bbox[3] - TN) / resolution).astype(int)
    ok = (i >= 0) & (i < H) & (j >= 0) & (j < W)
    m[i[ok], j[ok]] = True
    if verbose:
        print(f"  boisements : {len(TE)} points -> grille {W}x{H} a {resolution} m, "
              f"{m.mean()*100:.1f} % couverte")
    return m


def _lire(m, bbox, resolution, E, N):
    j = ((E - bbox[0]) / resolution).astype(int)
    i = ((bbox[3] - N) / resolution).astype(int)
    ok = (i >= 0) & (i < m.shape[0]) & (j >= 0) & (j < m.shape[1])
    out = np.zeros(len(E), bool)
    out[ok] = m[i[ok], j[ok]]
    return out


def auditer(vues, cible, mnt, veg, bbox, resolution=RESOLUTION,
            h_oeil=1.60, n_visees=25, h_plausible=H_PLAUSIBLE,
            verbose=True):
    """Pour chaque vue, la hauteur de vegetation qui masquerait le projet.

    `cible` : semis de points (E, N, Z_haut) sur l'ouvrage a masquer.
    """
    out = []
    for k, v in enumerate(vues):
        E0, N0 = v["E"], v["N"]
        z_oeil = float(mnt.altitude(E0, N0)) + h_oeil
        d_cible = np.hypot(cible[:, 0] - E0, cible[:, 1] - N0)
        # on vise un echantillon reparti sur toute la largeur de l'ouvrage
        idx = np.argsort(np.arctan2(cible[:, 0] - E0, cible[:, 1] - N0))
        idx = idx[np.linspace(0, len(idx) - 1, n_visees).astype(int)]

        besoins, portees, n_tot = [], [], 0
        for c in idx:
            D = float(d_cible[c])
            if D < D_MIN + MARGE:
                continue
            # angle d'elevation du HAUT de l'ouvrage, vu d'ici
            a_cible = (cible[c, 2] - z_oeil) / D
            s = np.arange(D_MIN, D - MARGE, PAS)
            if not len(s):
                continue
            n_tot += 1                       # visee RETENUE, barree ou non
            u = np.array([(cible[c, 0] - E0) / D, (cible[c, 1] - N0) / D])
            E, N = E0 + u[0] * s, N0 + u[1] * s
            occ = _lire(veg, bbox, resolution, E, N)
            if not occ.any():
                continue
            s_o = s[occ]
            z_o = np.array([float(mnt.altitude(e, n))
                            for e, n in zip(E[occ], N[occ])])
            # hauteur qu'il faudrait a CHAQUE point boise pour cacher la cible ;
            # le minimum est le seuil le plus facile a franchir, donc celui qui
            # decide si la visee est barree.
            h = z_oeil + a_cible * s_o - z_o
            besoins.append(float(np.min(h)))
            portees.append(float(s_o[int(np.argmin(h))]))
        if not n_tot:
            out.append(dict(**v, visees=0, part=0.0, h_requise=None,
                            d_obstacle=None, verdict="hors de portee"))
            continue
        besoins = np.array(besoins) if besoins else np.array([np.inf])
        # PART DE L'OUVRAGE masquee par une haie ordinaire
        part = float((besoins <= h_plausible).sum()) / n_tot
        verdict = ("masque total" if part >= 0.85 else
                   "masque partiel" if part >= 0.35 else
                   "masque marginal" if part >= 0.05 else "degage")
        bar = besoins[besoins <= h_plausible]
        out.append(dict(**v, visees=n_tot, part=round(part, 2),
                        h_requise=(round(float(np.median(bar)), 1)
                                   if len(bar) else None),
                        d_obstacle=(round(float(np.median(
                            [p for p, b in zip(portees, besoins)
                             if b <= h_plausible]))) if len(bar) else None),
                        verdict=verdict))
    return out


# Numeros imprimes sur la carte de Sarnois, du NORD au SUD — releves a l'oeil.
# `--apercu` reprojette le resultat sur la carte : si une pastille ne tombe pas
# sur sa fleche, la correspondance est fausse et cela se voit aussitot.
NUMEROS_SARNOIS = (13, 7, 20, 8, 12, 1, 2, 4, 11, 3,
                   18, 6, 19, 5, 10, 9, 14, 17, 15, 16)


def principal(carte=None, sortie=None, apercu=None,
              numeros=NUMEROS_SARNOIS):
    import carte_reperage as CR
    import lecture_dxf
    import montage as M
    import terrain

    scn = lecture_dxf.lire(M.DXF)
    q = np.array([t.q for t in scn.tables])
    centre = (float(q[:, :, 0].mean()), float(q[:, :, 1].mean()))
    carte = carte or (HERE / "exemples/sarnois-B/reportage-BE/carte_localisation_BE.png")
    print("carte de reperage")
    vues, _ = CR.points_de_vue(str(carte), 500.0, centre, numeros=numeros)
    if apercu:
        print(f"  apercu : {CR.apercu(str(carte), vues, apercu)}")

    # cible : le HAUT des tables, c'est lui qui doit etre cache
    cible = np.column_stack([q[:, :, 0].ravel(), q[:, :, 1].ravel(),
                             q[:, :, 2].ravel()])
    E = np.concatenate([cible[:, 0], [v["E"] for v in vues]])
    N = np.concatenate([cible[:, 1], [v["N"] for v in vues]])
    bbox = (E.min() - 120, N.min() - 120, E.max() + 120, N.max() + 120)
    print("\nterrain et vegetation")
    mnt = terrain.charger_mnt(bbox, pas=10.0, marge=0.0)
    veg = _raster_boisements(bbox)

    res = sorted(auditer(vues, cible, mnt, veg, bbox), key=lambda r: r["num"])
    if sortie:
        Path(sortie).write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res, vues


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    res, _ = principal(args[0] if args else None,
                       "audit_masques.json" if "--json" in sys.argv else None,
                       "audit_masques.png" if "--apercu" in sys.argv else None)
    print()
    print(f"{'vue':>4} {'E':>8} {'N':>9} {'visees':>7} {'masquee':>8} "
          f"{'h requise':>10} {'obstacle':>9}  verdict")
    for r in res:
        h = "-" if r["h_requise"] is None else f"{r['h_requise']:.1f} m"
        d = "-" if r.get("d_obstacle") is None else f"{r['d_obstacle']} m"
        print(f"{r['num']:4d} {r['E']:8.0f} {r['N']:9.0f} {r['visees']:7d} "
              f"{r['part'] * 100:7.0f} % {h:>10} {d:>9}  {r['verdict']}")
    for etat in ("masque total", "masque partiel", "masque marginal", "degage"):
        n = [r["num"] for r in res if r["verdict"] == etat]
        if n:
            print(f"\n{etat:16s} {len(n):2d} vues : " + ", ".join(map(str, n)))
