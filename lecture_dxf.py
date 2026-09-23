#!/usr/bin/env python3
"""Lecture generique d'un plan BE PVcase : tables, cloture, pistes, zones.

Gere les deux structures rencontrees :
  - Sarnois   : les tables sont des INSERT de blocs PVCase. Les coordonnees
                brutes `e.dxf.insert` sont en OCS et absurdes ; il faut passer
                par virtual_entities() qui resout en WCS.
  - Saint-Cyr : les tables sont des POLYLINE 3D directement dans le modelspace.

Dans les deux cas une table est une POLYLINE 3D a 4 sommets, dans l'ordre
haut, haut, bas, bas.
"""
import math
import re
from dataclasses import dataclass, field

import ezdxf
import numpy as np

MOTIF_TABLES = "PV Modules"          # sous-chaine commune aux couches PVcase
MOTIF_OPTIMISED = "optimised"
LAYER_TOPO = "-TopoNiveau"
MOTIFS_LIGNES = {
    "cloture": ("cloture", "clôture"),
    "piste": ("piste",),
    "plateforme": ("plateforme",),
    "voirie": ("voirie",),
    "haie": ("haie",),
    "pdl": ("pdl",),
    "local": ("local", "stockage"),
    "sdis": ("sdis",),
    "portail": ("portail",),
}


def _sans_accents(s):
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o"), ("û", "u"), ("î", "i"), ("ç", "c")):
        s = s.replace(a, b).replace(a.upper(), b.upper())
    return s


@dataclass
class Table:
    q: list                    # 4 sommets (x, y, z) : haut, haut, bas, bas
    rows: int = 2
    cols: int = 26

    @property
    def largeur_pente(self):
        a, b = np.array(self.q[0]), np.array(self.q[3])
        return float(np.linalg.norm(a - b))

    @property
    def denivele(self):
        return float(self.q[0][2] - self.q[3][2])

    @property
    def inclinaison(self):
        return math.degrees(math.asin(max(-1.0, min(1.0, self.denivele / self.largeur_pente))))


@dataclass
class Scene:
    tables: list = field(default_factory=list)
    lignes: dict = field(default_factory=dict)      # categorie -> liste de polylignes 2D/3D
    topo: np.ndarray = None                          # (n, 3) ou None
    source: str = ""

    def bbox(self):
        pts = np.array([p for t in self.tables for p in t.q])
        return (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())

    def centre(self):
        pts = np.array([p for t in self.tables for p in t.q])
        return pts.mean(axis=0)

    def azimut_modules(self):
        q = np.array([t.q for t in self.tables])
        n = np.cross(q[:, 3] - q[:, 0], q[:, 1] - q[:, 0])
        n[n[:, 2] < 0] *= -1
        az = (np.degrees(np.arctan2(n[:, 0], n[:, 1])) + 360) % 360
        return float(az.mean()), float(az.std())

    def resume(self):
        q = np.array([t.q for t in self.tables])
        largeurs = np.array([t.largeur_pente for t in self.tables])
        incl = np.array([t.inclinaison for t in self.tables])
        az, azs = self.azimut_modules()
        lignes = ", ".join(f"{k}:{len(v)}" for k, v in sorted(self.lignes.items()) if v)
        return (f"{len(self.tables)} tables | largeur {largeurs.mean():.3f} m | "
                f"inclinaison {incl.mean():.1f} deg | azimut modules {az:.1f} deg (ecart {azs:.1f})\n"
                f"  X [{q[:, :, 0].min():.0f}, {q[:, :, 0].max():.0f}]  "
                f"Y [{q[:, :, 1].min():.0f}, {q[:, :, 1].max():.0f}]  "
                f"Z [{q[:, :, 2].min():.2f}, {q[:, :, 2].max():.2f}]\n"
                f"  lignes : {lignes or 'aucune'} | topo DXF : "
                f"{len(self.topo) if self.topo is not None else 0} points")


def _quad_depuis_polyline(e):
    if e.dxftype() != "POLYLINE" or not e.is_3d_polyline:
        return None
    pts = [tuple(v.dxf.location) for v in e.vertices]
    return pts if len(pts) == 4 else None


def _rows_cols(nom):
    m = re.match(r"(\d+)P(\d+)", nom or "")
    return (int(m.group(1)), int(m.group(2))) if m else (2, 26)


def lire(chemin):
    """Lit un DXF et renvoie une Scene. Detecte automatiquement la structure."""
    doc = ezdxf.readfile(chemin)
    msp = doc.modelspace()
    tables = []

    # structure 1 : blocs INSERT (Sarnois)
    for ins in msp.query("INSERT"):
        if MOTIF_TABLES not in ins.dxf.layer:
            continue
        for ve in ins.virtual_entities():
            q = _quad_depuis_polyline(ve)
            if q:
                r, c = _rows_cols(ins.dxf.name)
                tables.append(Table(q=q, rows=r, cols=c))
                break

    # structure 2 : POLYLINE 3D directes dans le modelspace (Saint-Cyr)
    if not tables:
        for e in msp.query("POLYLINE"):
            if MOTIF_TABLES not in e.dxf.layer:
                continue
            q = _quad_depuis_polyline(e)
            if q:
                tables.append(Table(q=q))
    if not tables:
        raise RuntimeError(f"aucune table trouvee (couches contenant {MOTIF_TABLES!r})")

    # ordre des sommets : les deux premiers doivent etre les plus hauts
    for t in tables:
        z = [p[2] for p in t.q]
        if not (min(z[:2]) > max(z[2:]) - 1e-6):
            raise RuntimeError("ordre des sommets inattendu : haut, haut, bas, bas attendu")

    topo = np.array([tuple(e.dxf.insert) for e in msp.query("INSERT")
                     if e.dxf.layer == LAYER_TOPO], dtype=float)
    topo = topo if len(topo) else None

    lignes = {k: [] for k in MOTIFS_LIGNES}
    for e in msp.query("LWPOLYLINE"):
        lay = _sans_accents(e.dxf.layer).lower()
        for cat, motifs in MOTIFS_LIGNES.items():
            if any(_sans_accents(m).lower() in lay for m in motifs):
                pts = [(float(x), float(y)) for x, y in e.get_points("xy")]
                lignes[cat].append({"pts": pts, "fermee": bool(e.closed), "couche": e.dxf.layer})
                break

    return Scene(tables=tables, lignes={k: v for k, v in lignes.items() if v},
                 topo=topo, source=str(chemin))


if __name__ == "__main__":
    import sys
    from pathlib import Path
    HERE = Path(__file__).resolve().parent
    cibles = sys.argv[1:] or [
        HERE / "exemples" / "sarnois-A" / "2026_08_025-IMP-DEV-Fixe-IND10a_V2.dxf",
        HERE / "exemples" / "saint-cyr" / "20260903_SCV_IND06.dxf",
    ]
    for c in cibles:
        print(f"\n=== {Path(c).name} ===")
        print(" ", lire(c).resume().replace("\n", "\n "))
