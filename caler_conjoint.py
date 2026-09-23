#!/usr/bin/env python3
"""Ajuste PLUSIEURS vues d'un meme parc avec une hauteur de moyeu commune.

Pourquoi : vue par vue, l'horizon et la hauteur de moyeu sont mal separes. Les
eoliennes d'appui d'une meme photo sont a des distances voisines (1,3 a 1,9 km
a Sarnois), donc le bras de levier qui distingue « horizon 5 px plus bas » de
« moyeu 8 m plus haut » est faible : chaque vue s'accommode d'un couple
different, et deux photos du meme parc finissaient a 73,8 m et 82,7 m.

Or les machines sont les memes. En imposant UNE hauteur de moyeu pour toutes
les vues, la geometrie de chacune contraint l'horizon de l'autre, et l'ensemble
se referme. Inconnues : (E, N, azimut, horizon) par vue, plus H commun.

Usage :
    python caler_conjoint.py mesures_PV9.json mesures_PV10.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

import caler_focale_fixe as cf

HERE = Path(__file__).resolve().parent


def charger(chemin):
    m = json.loads(Path(chemin).read_text(encoding="utf-8"))
    pose = json.loads(Path(HERE / m["sortie"]).read_text(encoding="utf-8"))
    return m, pose


def ajuster(fichiers, verbose=True):
    eol = {e["id"]: e for e in json.loads(
        (HERE / "exemples/sarnois-B/eoliennes_osm.json").read_text(encoding="utf-8"))}
    import terrain
    vues = []
    for f in fichiers:
        m, pose = charger(f)
        F = cf.focale_px(m["eq35_mm"], m["largeur"], m["hauteur"])
        ap = [eol[i] for i in pose["eoliennes_appui"]]
        vues.append(dict(m=m, pose=pose, F=F, cx=m["largeur"] / 2.0,
                         U=np.array([p[0] for p in m["mats"]], float),
                         Y=np.array([p[1] for p in m["mats"]], float),
                         E=np.array([e["E"] for e in ap], float),
                         N=np.array([e["N"] for e in ap], float)))
    tE = np.concatenate([v["E"] for v in vues] + [[v["pose"]["est"] for v in vues]])
    tN = np.concatenate([v["N"] for v in vues] + [[v["pose"]["nord"] for v in vues]])
    mnt = terrain.charger_mnt((tE.min() - 200, tN.min() - 200, tE.max() + 200, tN.max() + 200),
                              pas=20.0, marge=0.0)
    for v in vues:
        v["ZB"] = np.array([float(mnt.altitude(e, n)) for e, n in zip(v["E"], v["N"])])
        v["z0"] = float(mnt.altitude(v["pose"]["est"], v["pose"]["nord"]))

    # parametres : [H] puis (azimut, E, N, horizon) par vue
    p0 = [float(np.mean([v["pose"].get("h_moyeu_commun", 78.0) for v in vues]))]
    bas, haut = [55.0], [100.0]
    for v in vues:
        p = v["pose"]
        p0 += [p["azimut"], p["est"], p["nord"], p["horizon"]]
        bas += [p["azimut"] - 4, p["est"] - 40, p["nord"] - 40, p["horizon"] - 25]
        haut += [p["azimut"] + 4, p["est"] + 40, p["nord"] + 40, p["horizon"] + 25]

    def residus(p):
        out = []
        for k, v in enumerate(vues):
            az0, E0, N0, hv = p[1 + 4 * k: 5 + 4 * k]
            az = (np.degrees(np.arctan2(v["E"] - E0, v["N"] - N0)) + 360) % 360
            d = np.hypot(v["E"] - E0, v["N"] - N0)
            out.append(v["cx"] + v["F"] * np.tan(np.radians(cf._wrap(az - az0))) - v["U"])
            # hauteur de moyeu vue par chaque mat, relief corrige, contre H commun
            z_oeil = float(mnt.altitude(E0, N0)) + v["m"].get("hauteur_oeil", 1.6)
            hm = (hv - v["Y"]) * d / v["F"] + (z_oeil - v["ZB"])
            out.append(0.20 * (hm - p[0]))
        return np.concatenate(out)

    s = least_squares(residus, p0, bounds=(bas, haut))
    H = float(s.x[0])
    if verbose:
        print(f"hauteur de moyeu commune : {H:.1f} m "
              f"(bout de pale 114,9 m -> rayon de rotor {114.9 - H:.1f} m)\n")
    sorties = []
    for k, v in enumerate(vues):
        az0, E0, N0, hv = s.x[1 + 4 * k: 5 + 4 * k]
        az = (np.degrees(np.arctan2(v["E"] - E0, v["N"] - N0)) + 360) % 360
        d = np.hypot(v["E"] - E0, v["N"] - N0)
        r = v["cx"] + v["F"] * np.tan(np.radians(cf._wrap(az - az0))) - v["U"]
        z_oeil = float(mnt.altitude(E0, N0)) + v["m"].get("hauteur_oeil", 1.6)
        hm = (hv - v["Y"]) * d / v["F"] + (z_oeil - v["ZB"])
        rms = float(np.sqrt(np.mean(r ** 2)))
        nom = Path(v["m"]["photo"]).stem
        if verbose:
            print(f"{nom:12s} E={E0:.0f} N={N0:.0f} az={az0 % 360:7.2f} horizon={hv:6.1f} "
                  f"| mats {rms:.2f} px | moyeu {hm.mean():.1f} +/- {hm.std():.1f} m")
        sorties.append((v, float(az0 % 360), float(E0), float(N0), float(hv), rms,
                        float(hm.std()), H))
    return sorties


if __name__ == "__main__":
    for v, az, E0, N0, hv, rms, disp, H in ajuster(sys.argv[1:]):
        m, F = v["m"], v["F"]
        W, Ht = m["largeur"], m["hauteur"]
        pose = dict(v["pose"])
        pose.update({
            "est": round(E0, 1), "nord": round(N0, 1), "azimut": round(az, 2),
            "horizon": round(hv, 1),
            "tangage": round(math.degrees(math.atan((hv - Ht / 2) / F)), 2),
            "appui": (f"{len(m['mats'])} moyeux a focale FIXEE par l'EXIF "
                      f"({m['eq35_mm']} mm eq.), ajustement conjoint des deux vues a "
                      f"hauteur de moyeu commune {H:.1f} m ; ecart {rms:.2f} px ; "
                      f"dispersion du moyeu {disp:.1f} m"),
            "h_moyeu_commun": round(H, 1),
        })
        out = HERE / m["sortie"]
        out.write_text(json.dumps(pose, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"ecrit : {out}")
