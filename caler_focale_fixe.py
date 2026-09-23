#!/usr/bin/env python3
"""Cale une photo dont la FOCALE EST CONNUE par l'EXIF.

Pourquoi un second solveur plutot qu'une option de `calage_paysage.caler` :
le probleme change de nature. Quand la focale est inconnue, on ajuste (azimut,
focale) sur un triplet de mats, et il faut ensuite lever l'ambiguite d'echelle
a coups de controles de taille apparente. Quand la focale est donnee, il ne
reste qu'UNE inconnue angulaire par position candidate — alors on peut balayer
l'azimut de front, laisser l'appariement mat/eolienne se faire tout seul, et
utiliser TOUS les mats visibles au lieu de trois. La taille apparente cesse
d'etre une bequille et devient une verification independante : la hauteur de
moyeu deduite doit etre la meme pour tous les mats, et valoir ce que valent les
machines du parc.

La focale se deduit du 35 mm equivalent par la DIAGONALE, qui est la definition
usuelle et ne demande pas de connaitre la taille du capteur :

    f_px = eq35_mm * diagonale_px / 43,267

Usage :
    python caler_focale_fixe.py mesures_PV9.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

import calage_paysage as cp

HERE = Path(__file__).resolve().parent
DIAG35 = 43.267                      # mm, diagonale du 24 x 36


def focale_px(eq35_mm, W, H):
    return eq35_mm * math.hypot(W, H) / DIAG35


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def _cout(U, pred, tol=40.0):
    """Appariement 1-1 glouton entre mats mesures et eoliennes predites.

    Glouton et non hongrois : les mats sont peu nombreux et bien separes, et
    l'appariement optimal se lit sans ambiguite des que l'azimut est proche.
    """
    pred = np.asarray(pred, float)
    libre = np.ones(len(pred), bool)
    total, paires = 0.0, []
    for i in np.argsort([min(abs(u - pred)) for u in U]):
        d = np.where(libre, np.abs(pred - U[i]), np.inf)
        j = int(np.argmin(d))
        if not np.isfinite(d[j]) or d[j] > tol:
            return np.inf, []
        libre[j] = False
        total += d[j] ** 2
        paires.append((i, j))
    return math.sqrt(total / len(U)), paires


def resoudre(m, verbose=True):
    W, H = m["largeur"], m["hauteur"]
    F = focale_px(m["eq35_mm"], W, H)
    cx, hv = W / 2.0, m["horizon_v"]
    U = np.array([p[0] for p in m["mats"]], float)
    PX = np.array([hv - p[1] for p in m["mats"]], float)      # moyeu au-dessus de l'horizon
    eol = json.loads((HERE / m["eoliennes"]).read_text(encoding="utf-8"))
    EE = np.array([e["E"] for e in eol]); NN = np.array([e["N"] for e in eol])

    c0 = np.array(m["autour"], float)
    bbox = (c0[0] - m["rayon"], c0[1] - m["rayon"], c0[0] + m["rayon"], c0[1] + m["rayon"])
    cand = cp.positions_le_long_des_voies(HERE / m["voies"], bbox, pas=m.get("pas", 4.0))

    # ALTITUDE DES PIEDS. La hauteur de moyeu lue dans l'image est comptee
    # au-dessus de l'HORIZON, donc au-dessus de l'oeil, pas au-dessus du pied du
    # mat. A Sarnois les pieds s'etagent sur 5 m, ce qui fait 4 px a 1,4 km,
    # c'est-a-dire l'essentiel de la dispersion residuelle. Sans cette
    # correction, le controle d'echelle accuse le modele de ce que fait le relief.
    ZB = np.zeros(len(eol))
    z_oeil = 0.0
    if m.get("mnt", True):
        import terrain
        # bbox limitee au parc utile : le fichier OSM porte des machines a 8 km,
        # dont le MNT complet ferait des millions de points pour rien.
        pr = np.hypot(EE - c0[0], NN - c0[1]) < m.get("dmax_eol", 4000.0)
        mnt = terrain.charger_mnt((min(EE[pr].min(), c0[0]) - 200, min(NN[pr].min(), c0[1]) - 200,
                                   max(EE[pr].max(), c0[0]) + 200, max(NN[pr].max(), c0[1]) + 200),
                                  pas=20.0, marge=0.0)
        z_oeil = float(mnt.altitude(c0[0], c0[1])) + m.get("hauteur_oeil", 1.6)
        ZB = np.where(pr, [float(mnt.altitude(e, n)) if p else z_oeil
                           for e, n, p in zip(EE, NN, pr)], z_oeil)
    if verbose:
        print(f"focale EXIF : {m['eq35_mm']} mm eq. -> f = {F:.1f} px sur {W}x{H}")
        print(f"{len(U)} mats mesures, {len(eol)} eoliennes, {len(cand)} positions candidates")

    # Le CONTROLE D'ECHELLE est applique DANS la boucle, pas apres.
    #
    # Avec la focale fixee, trois mats donnent trois equations pour trois
    # inconnues (E, N, azimut) : le systeme est exactement determine, et des
    # dizaines d'assignations differentes l'ajustent au dixieme de pixel tout en
    # placant les eoliennes a des distances absurdes. Ce qui tranche, c'est que
    # les machines d'un meme parc ont TOUTES la meme hauteur de moyeu : chaque
    # mat en donne une estimation PX * d / f, et elles doivent coincider. En
    # post-filtre, ce controle arrivait trop tard et ne laissait rien passer.
    hmin, hmax = m.get("h_moyeu", (55.0, 100.0))
    disp_max = m.get("disp_max", 0.06)
    grille = np.arange(m["az0"] - m["daz"], m["az0"] + m["daz"], 0.08)
    best = []
    for c in cand:
        az_t = (np.degrees(np.arctan2(EE - c[0], NN - c[1])) + 360) % 360
        d_t = np.hypot(EE - c[0], NN - c[1])
        for az0 in grille:
            rel = np.radians(_wrap(az_t - az0))
            vu = np.abs(rel) < 1.0
            if vu.sum() < len(U):
                continue
            idx = np.nonzero(vu)[0]
            pred = cx + F * np.tan(rel[vu])
            rms, paires = _cout(U, pred)
            if not np.isfinite(rms):
                continue
            tri = [int(idx[j]) for _, j in sorted(paires)]
            H = PX * d_t[tri] / F + (z_oeil - ZB[tri])
            hm = float(H.mean())
            if not (hmin <= hm <= hmax) or float(H.std()) / hm > disp_max:
                continue
            best.append((rms + 6.0 * float(H.std()) / hm, float(az0), c, idx, paires))
    if not best:
        raise SystemExit("aucune solution : elargir la fenetre, ou revoir "
                         "l'horizon dont depend entierement le controle d'echelle")
    best.sort(key=lambda r: r[0])

    # affinage : sur le meilleur appariement, l'azimut seul est ajuste, et
    # TOUS les mats servent. Avec f fixee le systeme est surdetermine.
    sorties = []
    vus = []
    for rms0, az0, c, idx, paires in best[:4000]:
        if any(math.hypot(c[0] - e, c[1] - n) < 12 for e, n in vus):
            continue
        tri = [int(idx[j]) for _, j in sorted(paires)]
        az_t = np.array([(math.degrees(math.atan2(EE[k] - c[0], NN[k] - c[1])) + 360) % 360
                         for k in tri])
        d_t = np.array([math.hypot(EE[k] - c[0], NN[k] - c[1]) for k in tri])

        # Affinage CONTINU. Les candidats sont echantillonnes tous les 4 m le
        # long des chemins : cette quantification laissait a elle seule 4 a 5 px
        # d'ecart. On libere donc (E, N, azimut) et la hauteur de moyeu H, avec
        # deux familles de residus — les abscisses en pixels, et l'egalite des
        # hauteurs de moyeu vues par chaque mat. Six equations, quatre inconnues.
        E_t, N_t = EE[tri], NN[tri]
        DZ = z_oeil - ZB[tri]
        H0 = float((PX * d_t / F + DZ).mean())
        # Ponderation par l'incertitude REELLE de chaque famille : les abscisses
        # sont mesurees a 0,5 px pres, la hauteur de moyeu a 4 % pres (elle
        # depend de la lecture du moyeu et de l'horizon). Un poids de 3 faisait
        # dominer l'echelle et sacrifiait les angles, qui sont pourtant la
        # mesure precise. L'echelle doit rester un garde-fou, pas le pilote.
        ech = m.get("poids_echelle", 0.5 / (0.04 * max(H0, 1.0)))
        # L'HORIZON est lui aussi une inconnue. Il a ete lu sur un unique pied de
        # tour a demi cache par une haie, et il commande a la fois le tangage et
        # tout le controle d'echelle. Or les machines ont la meme hauteur de
        # moyeu : (hv - y_i) * d_i doit etre constant, ce qui determine hv et H
        # ensemble des que les mats sont a des distances differentes. Un a priori
        # large le retient pres de la lecture initiale sans l'y clouer.
        YM = np.array([p[1] for p in m["mats"]], float)
        s_hv = m.get("incertitude_horizon", 6.0)

        def res(p):
            az_i = (np.degrees(np.arctan2(E_t - p[1], N_t - p[2])) + 360) % 360
            d_i = np.hypot(E_t - p[1], N_t - p[2])
            r_ang = cx + F * np.tan(np.radians(_wrap(az_i - p[0]))) - U
            r_ech = ech * ((p[4] - YM) * d_i / F + DZ - p[3])
            return np.concatenate([r_ang, r_ech, [(p[4] - hv) / s_hv]])

        s = least_squares(res, [az0, c[0], c[1], H0, hv],
                          bounds=([az0 - 8, c[0] - 45, c[1] - 45, hmin, hv - 3 * s_hv],
                                  [az0 + 8, c[0] + 45, c[1] + 45, hmax, hv + 3 * s_hv]))
        c = np.array([s.x[1], s.x[2]])
        az_t = (np.degrees(np.arctan2(E_t - c[0], N_t - c[1])) + 360) % 360
        d_t = np.hypot(E_t - c[0], N_t - c[1])
        rms = float(np.sqrt(np.mean(s.fun[:len(U)] ** 2)))
        moyeux = (s.x[4] - YM) * d_t / F + DZ      # hauteur de moyeu, relief corrige
        sorties.append({"rms": rms, "azimut": float(s.x[0] % 360),
                        "est": float(c[0]), "nord": float(c[1]), "H": float(s.x[3]),
                        "horizon_v": float(s.x[4]),
                        "h_moyeu": float(moyeux.mean()),
                        "h_moyeu_disp": float(moyeux.std()),
                        "ids": [eol[k]["id"] for k in tri],
                        "d": [round(float(x), 1) for x in d_t]})
        vus.append((c[0], c[1]))
        if len(vus) >= m.get("n_positions", 40):
            break

    # filtre physique : la hauteur de moyeu doit etre la meme pour tous les mats
    # et rester dans les bornes des machines du parc
    hmin, hmax = m.get("h_moyeu", (55.0, 100.0))
    gardes = [r for r in sorties
              if hmin <= r["h_moyeu"] <= hmax
              and r["h_moyeu_disp"] / r["h_moyeu"] < m.get("disp_max", 0.10)]
    if verbose:
        print(f"\n{len(sorties)} positions distinctes, {len(gardes)} passent le controle "
              f"de hauteur de moyeu ({hmin:.0f}-{hmax:.0f} m, dispersion < "
              f"{100*m.get('disp_max', 0.10):.0f} %)")
    if not gardes:
        gardes = sorties

    # depart : la silhouette des boisements tranche entre positions restantes
    prof = cp.silhouette(HERE / m["photo"])
    TE, TN = cp.masque_boisements((c0[0] - 700, c0[1] - 700, c0[0] + 700, c0[1] + 700))
    for r in gardes:
        r["accord"] = cp._accord_silhouette(r["est"], r["nord"], r["azimut"], F, W,
                                            prof, TE, TN, horizon_v=hv)
        r["score"] = r["accord"] - r["rms"] / 40.0
    gardes.sort(key=lambda r: -r["score"])
    if verbose:
        print()
        for r in gardes[:8]:
            print(f"  score {r['score']:.3f} | silhouette {100*r['accord']:5.1f}% | "
                  f"mats {r['rms']:5.2f} px | az {r['azimut']:7.2f} | "
                  f"E={r['est']:.0f} N={r['nord']:.0f} | "
                  f"moyeu {r['h_moyeu']:5.1f} +/- {r['h_moyeu_disp']:.1f} m | "
                  f"horizon {r['horizon_v']:6.1f}")
    return gardes, F


def ecrire_pose(m, r, F, sortie):
    W, H = m["largeur"], m["hauteur"]
    # tangage : v_horizon = cy + f*tan(tangage), cf. camera.Camera.horizon_v
    hv = r.get("horizon_v", m["horizon_v"])
    tangage = math.degrees(math.atan((hv - H / 2) / F))
    pose = {
        "photo": Path(m["photo"]).name,
        "largeur": W, "hauteur": H,
        "est": r["est"], "nord": r["nord"],
        "azimut": round(r["azimut"], 2),
        "f_px": round(F, 1),
        "horizon": round(hv, 1),
        "appui": (f"{len(m['mats'])} mats a focale FIXEE par l'EXIF "
                  f"({m['eq35_mm']} mm eq.), ecart {r['rms']:.2f} px ; "
                  f"moyeu deduit {r['h_moyeu']:.1f} +/- {r['h_moyeu_disp']:.1f} m ; "
                  f"silhouette des boisements {100*r['accord']:.1f}%"),
        "tangage": round(tangage, 2),
        "roulis": 0.0,
        "hauteur_oeil": m.get("hauteur_oeil", 1.6),
        "champ_deg": round(2 * math.degrees(math.atan(W / (2 * F))), 1),
        "eq35_mm": m["eq35_mm"],
        "soleil": m.get("soleil"),
        "eoliennes_appui": r["ids"],
        "distances_m": r["d"],
    }
    Path(sortie).write_text(json.dumps(pose, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\necrit : {sortie}")
    return pose


if __name__ == "__main__":
    m = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    gardes, F = resoudre(m)
    ecrire_pose(m, gardes[0], F, sys.argv[2] if len(sys.argv) > 2 else m["sortie"])
