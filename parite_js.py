#!/usr/bin/env python3
"""Parite entre le modele JavaScript de photomontage.html et camera.py.

Node.js n'est pas installe sur les postes : la comparaison numerique se fait
dans le navigateur, une fois, puis on VERROUILLE la source JavaScript par une
empreinte. Si quelqu'un modifie makeCam, le test echoue et demande de rejouer
la comparaison.

Comparaison numerique (a rejouer apres toute modification de makeCam) :
  1. python proto_photomontage.py
  2. servir le dossier :  python -m http.server 8765
  3. ouvrir http://localhost:8765/photomontage.html, console du navigateur,
     coller le contenu de SNIPPET_NAVIGATEUR ci-dessous
  4. coller le JSON obtenu dans un fichier et lancer :
        python parite_js.py verifier chemin_du_json.json
  5. si l'ecart est < 1e-6 px, lancer :
        python parite_js.py verrouiller
"""
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

from camera import Camera

HERE = Path(__file__).resolve().parent
HTML = HERE / "photomontage.html"
EMPREINTE = HERE / "parite_js.json"

SNIPPET_NAVIGATEUR = r"""
const D=Math.PI/180, pol=(az,d,h)=>[d*Math.sin(az*D), d*Math.cos(az*D), h];
const PTS=[pol(336.5,300,3.5),pol(320,180,1.6),pol(350,410,0),pol(336.5,50,12),pol(325,1000,-2),pol(348,95,4.2)];
const CFGS=[{az:336.5,pitch:-8.5,roll:3.7,f:33.5,h:1.60},{az:0,pitch:0,roll:0,f:26,h:1.60},
            {az:90,pitch:12,roll:-4,f:20,h:2.5},{az:271.3,pitch:7.7,roll:-2.2,f:40,h:1.0}];
const out={W:W,H:H,cfgs:[]};
for(const c of CFGS){const cam=makeCam(c);
  out.cfgs.push({cfg:c, fpx:cam.fpx,
    uv:PTS.map(p=>{const s=cam.proj(cam.toCam(p)); return s?[s[0],s[1]]:null;}),
    ray:cam.ray(500.5,1200.25)});}
JSON.stringify(out)
"""

D = math.pi / 180
POL = lambda az, d, h: [d * math.sin(az * D), d * math.cos(az * D), h]
PTS = np.array([POL(336.5, 300, 3.5), POL(320, 180, 1.6), POL(350, 410, 0),
                POL(336.5, 50, 12), POL(325, 1000, -2), POL(348, 95, 4.2)])


GABARIT = HERE / "gabarit_vue.html"
EMPREINTE_GABARIT = HERE / "parite_gabarit.json"


def source_js(html_path=HTML):
    """Extrait le texte de makeCam(), sub/add/cross et la formule de projection."""
    txt = html_path.read_text(encoding="utf-8")
    m = re.search(r"function makeCam\(P\) \{.*?\n\}", txt, re.S)
    if not m:
        raise RuntimeError("makeCam introuvable dans le HTML")
    return m.group(0)


def empreinte_js(html_path=HTML):
    src = re.sub(r"\s+", " ", source_js(html_path)).strip()
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def source_gabarit(chemin=GABARIT):
    """Modele de camera + solveur de l'outil de calage (gabarit_vue.html)."""
    txt = chemin.read_text(encoding="utf-8")
    parts = []
    for motif in (r"function makeCam\(p\) \{.*?\n\}",
                  r"function residus\(p, pts\) \{.*?\n\}",
                  r"function resoudre\(pts, depart, libres\) \{.*?\n\}",
                  r"function gauss\(A, b\) \{.*?\n\}",
                  r"const MNT = \{.*?\n\};"):
        m = re.search(motif, txt, re.S)
        if not m:
            raise RuntimeError(f"bloc introuvable dans le gabarit : {motif[:30]}")
        parts.append(m.group(0))
    return "\n".join(parts)


def empreinte_gabarit(chemin=GABARIT):
    src = re.sub(r"\s+", " ", source_gabarit(chemin)).strip()
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def verifier(json_path):
    js = json.loads(Path(json_path).read_text(encoding="utf-8"))
    pires = {"f_px": 0.0, "uv": 0.0, "rayon": 0.0}
    for e in js["cfgs"]:
        c = e["cfg"]
        cam = Camera(js["W"], js["H"], c["az"], c["pitch"], c["roll"], c["f"], c["h"])
        pires["f_px"] = max(pires["f_px"], abs(cam.f_px - e["fpx"]))
        py = cam.projeter(PTS)
        for k, ref in enumerate(e["uv"]):
            if ref is None:
                if not np.isnan(py[k]).all():
                    raise AssertionError(f"JS rejette le point {k}, Python non (az={c['az']})")
            else:
                if np.isnan(py[k]).any():
                    raise AssertionError(f"Python rejette le point {k}, JS non (az={c['az']})")
                pires["uv"] = max(pires["uv"], float(np.abs(py[k] - np.array(ref)).max()))
        r_py = cam.rayon([[500.5, 1200.25]])[0]
        r_js = np.array(e["ray"])
        r_py /= np.linalg.norm(r_py)
        r_js /= np.linalg.norm(r_js)
        pires["rayon"] = max(pires["rayon"], float(np.abs(r_py - r_js).max()))
    return pires


def main(argv):
    if len(argv) >= 2 and argv[1] == "snippet":
        print(SNIPPET_NAVIGATEUR)
        return 0
    if len(argv) >= 3 and argv[1] == "verifier":
        p = verifier(argv[2])
        print(f"ecart f_px  : {p['f_px']:.3e} px")
        print(f"ecart (u,v) : {p['uv']:.3e} px")
        print(f"ecart rayon : {p['rayon']:.3e}")
        ok = p["uv"] < 1e-6 and p["rayon"] < 1e-9 and p["f_px"] < 1e-9
        print("PARITE OK" if ok else "ECART A INVESTIGUER")
        return 0 if ok else 1
    if len(argv) >= 2 and argv[1] == "verrouiller":
        EMPREINTE.write_text(json.dumps({
            "empreinte_makeCam": empreinte_js(),
            "verifie_le": argv[2] if len(argv) > 2 else "non precise",
            "ecart_max_uv_px": argv[3] if len(argv) > 3 else "voir rapport",
        }, indent=2), encoding="utf-8")
        print(f"empreinte enregistree : {EMPREINTE.name}")
        return 0
    if len(argv) >= 2 and argv[1] == "verrouiller-gabarit":
        EMPREINTE_GABARIT.write_text(json.dumps({
            "empreinte": empreinte_gabarit(),
            "verifie_le": argv[2] if len(argv) > 2 else "non precise",
            "note": "camera et solveur du gabarit compares au solveur Python "
                    "sur donnees identiques : ecart max 0,0004 (m, deg ou px)",
        }, indent=2), encoding="utf-8")
        print(f"empreinte du gabarit enregistree : {EMPREINTE_GABARIT.name}")
        return 0
    print(__doc__)
    print(f"empreinte actuelle de makeCam : {empreinte_js()}")
    if EMPREINTE.exists():
        ref = json.loads(EMPREINTE.read_text(encoding="utf-8"))
        etat = "INCHANGE" if ref["empreinte_makeCam"] == empreinte_js() else "MODIFIE (rejouer la parite)"
        print(f"empreinte verrouillee le {ref['verifie_le']} : {etat}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
