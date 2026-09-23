#!/usr/bin/env python3
"""Prototype photomontage PV - Sarnois 10A, photo IMG_6941.

Produit `photomontage.html` (fichier autonome) a partir du plan BE (DXF, L93)
et de la photo terrain. Prototype jetable : un seul cas, geometrie seulement
(pas de masquage vegetation, pas d'ombres, pas de textures).

Elements projetes : tables PV (face modules + structure indicative), cloture
avec poteaux, haie projetee, pistes et zones VRD au sol, ligne d'horizon,
reperes eoliennes (controle du calage).

Dependances : ezdxf, numpy, pillow.
"""
import base64
import io
import json
import math
import re
from pathlib import Path

import ezdxf
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "exemples" / "sarnois-A"
DXF_PATH = SRC / "2026_08_025-IMP-DEV-Fixe-IND10a_V2.dxf"
PHOTO_PATH = SRC / "IMG_6941.jpeg"
OUT_JSON = HERE / "geom.json"
OUT_HTML = HERE / "photomontage.html"

# ---------------------------------------------------------------------------
# Constantes verifiees (brief) - ne pas recalculer
# ---------------------------------------------------------------------------
CAM_X, CAM_Y = 621980.0, 6954139.0   # position camera L93 (EXIF GPS)
CAM_Z_SOL = 191.3                    # altitude sol au point de prise de vue
CAM_H = 1.60                         # hauteur de prise de vue initiale (m)
AZIMUT = 321.6                       # yaw initial (deg, 0 = Nord, horaire)
FOCALE = 26.0                        # focale eq. 35 mm
Z_POINT_BAS = 1.50                   # point bas table (m au-dessus du sol, tableau bilan BE)
# NB : le brief demandait d'ajouter +1,50 m aux Z DXF. Verification du 14/09/2026 : dans ce DXF V2,
# PVcase exporte deja les coins bas a 1,500 m (+/- 0,006) au-dessus du TIN topo. Le script mesure
# donc l'ecart coins bas / sol et n'ajoute que le complement necessaire (0 m ici).
CLOTURE_H = 2.00                     # hauteur cloture (m)
HAIE_H = 2.00                        # hauteur haie projetee dessinee (m, indicatif)
SOLEIL = {"azimut": 244.9, "elevation": 47.6}   # info seulement, pas d'ombre

# Reperes de calage : les deux eoliennes visibles a l'horizon (OpenStreetMap,
# converties en L93). Controle uniquement, dessines comme des tirets verticaux.
REPERES = [
    {"nom": "Eolienne OSM 7595939636 (1,5 km)", "xy": (621646.0, 6955615.0)},
    {"nom": "Eolienne OSM 7595939637 (1,9 km)", "xy": (621732.0, 6956035.0)},
]
AZ_PLAGE = 20.0             # curseur azimut : AZIMUT +/- AZ_PLAGE (brief : 15, elargi pour le calage)
F_MIN, F_MAX = 20.0, 40.0   # curseur focale (brief : 20-32, elargi : photo rognee en 9:16)
# Calage obtenu sur les deux eoliennes (validation du 07/09/2026)
CALAGE = {"az": 336.5, "pitch": -8.5, "roll": 0.0, "f": 33.5, "h": 1.60, "op": 85}

LAYER_PV = "PVcase PV Modules (full frames)"
LAYER_CLOTURE = "UNI_Cloture"
LAYER_TOPO = "-TopoNiveau"
LAYER_HAIE = "UNI_Haies"
PREFIX_PISTES = "UNI_VRD_Pistes"
LAYERS_ZONES = ["UNI_VRD_Plateforme", "UNI_VRD_Voirie", "UNI_Local_Stockage", "UNI_PDL",
                "UNI_VRD_Base_vie", "UNI_VRD_Stockage_Logistique"]

HTML_W = 2268       # largeur photo embarquee (px) : pleine resolution, la centrale ne fait que ~90 px de haut
JPEG_Q = 80
HTML_MAX_MB = 4.0


# ---------------------------------------------------------------------------
# Etape 1 - extraction geometrie DXF
# ---------------------------------------------------------------------------
def extraire_tables(msp):
    """85 quadrilateres 3D en WCS (L93 + altitude), Z rehausse de Z_BAS_TABLE.

    Piege OCS : chaque INSERT porte son propre vecteur d'extrusion. On passe
    imperativement par virtual_entities() qui resout les entites en WCS.
    Sommets : haut, haut, bas, bas (les deux premiers ont Z +2,02 m).
    """
    tables = []
    for ins in msp.query("INSERT"):
        if ins.dxf.layer != LAYER_PV:
            continue
        quad = None
        for ve in ins.virtual_entities():
            if ve.dxftype() == "POLYLINE" and ve.is_3d_polyline:
                pts = [tuple(v.dxf.location) for v in ve.vertices]
                if len(pts) == 4:
                    quad = pts
                    break
        if quad is None:
            raise RuntimeError(f"Bloc {ins.dxf.name!r} sans POLYLINE 3D a 4 sommets")
        m = re.match(r"(\d+)P(\d+)", ins.dxf.name)   # ex. "2P26_25DEG ..." : 2 modules portrait x 26
        rows, cols = (int(m.group(1)), int(m.group(2))) if m else (2, 26)
        tables.append({"q": [tuple(p) for p in quad], "rows": rows, "cols": cols})
    return tables


def rehausser_point_bas(tables, topo):
    """Amene le bord bas des tables a Z_POINT_BAS au-dessus du sol.

    Mesure l'ecart entre les coins bas du DXF et le sol topo (IDW sur les 3 points
    les plus proches), puis ajoute le complement a tous les Z. Ainsi un DXF ou les
    coins bas sont au sol recoit +1,50 m, un DXF deja rehausse (cas PVcase ici) recoit 0.
    """
    low = np.array([t["q"][2:] for t in tables], dtype=float).reshape(-1, 3)
    d2 = ((low[:, None, :2] - topo[None, :, :2]) ** 2).sum(axis=-1)
    idx = np.argsort(d2, axis=1)[:, :3]
    w = 1.0 / np.sqrt(np.take_along_axis(d2, idx, 1) + 1e-6)
    z_sol = (topo[idx, 2] * w).sum(axis=1) / w.sum(axis=1)
    res = low[:, 2] - z_sol
    dz = Z_POINT_BAS - res.mean()
    print(f"Point bas : coins bas DXF - sol topo = {res.mean():.3f} m (+/- {res.std():.3f}) "
          f"-> rehausse appliquee {dz:+.2f} m pour un point bas a {Z_POINT_BAS:.2f} m")
    if res.std() > 0.15:
        print("  ATTENTION : dispersion forte des coins bas par rapport au sol, verifier le DXF")
    for t in tables:
        t["q"] = [(x, y, z + dz) for x, y, z in t["q"]]
    return dz


def extraire_topo(msp):
    pts = [tuple(e.dxf.insert) for e in msp.query("INSERT") if e.dxf.layer == LAYER_TOPO]
    return np.array(pts, dtype=float)


def z_topo(xy, topo):
    """Altitude du point topo le plus proche pour chaque (x, y)."""
    xy = np.asarray(xy, dtype=float)
    d2 = ((xy[:, None, :] - topo[None, :, :2]) ** 2).sum(axis=-1)
    return topo[d2.argmin(axis=1), 2]


def poly3d(e, topo):
    xy = np.array(list(e.get_points("xy")), dtype=float)
    return [(float(x), float(y), float(z)) for (x, y), z in zip(xy, z_topo(xy, topo))]


def extraire_lignes(msp, topo):
    """Cloture, haie projetee, pistes (lourdes/legeres), zones techniques -> 3D via topo."""
    cloture, haie, pistes, zones = None, None, [], []
    for e in msp.query("LWPOLYLINE"):
        lay = e.dxf.layer
        if lay == LAYER_CLOTURE:
            cloture = poly3d(e, topo)
        elif lay == LAYER_HAIE:
            haie = poly3d(e, topo)
        elif lay.startswith(PREFIX_PISTES) and e.closed:
            pistes.append({"type": "lourde" if "lourd" in lay else "legere", "pts": poly3d(e, topo)})
        elif lay in LAYERS_ZONES and e.closed:
            zones.append({"nom": lay.replace("UNI_VRD_", "").replace("UNI_", ""), "pts": poly3d(e, topo)})
    if cloture is None:
        raise RuntimeError(f"Pas de LWPOLYLINE sur {LAYER_CLOTURE!r}")
    return cloture, haie, pistes, zones


def relatif(pts, nd=2):
    """Coordonnees relatives au sol sous la camera (X-Xcam, Y-Ycam, Z-Zsol).

    La hauteur de prise de vue est un curseur cote JS ; on garde donc le sol
    comme reference et JS soustrait la hauteur camera.
    """
    return [[round(x - CAM_X, nd), round(y - CAM_Y, nd), round(z - CAM_Z_SOL, nd)] for x, y, z in pts]


def controle(tables, cloture, haie, pistes, zones, topo):
    arr = np.array([t["q"] for t in tables])  # (85, 4, 3)
    print(f"Tables : {len(tables)} quadrilateres, blocs {sorted({(t['rows'], t['cols']) for t in tables})}")
    print(f"  X  [{arr[:, :, 0].min():.1f}, {arr[:, :, 0].max():.1f}]")
    print(f"  Y  [{arr[:, :, 1].min():.1f}, {arr[:, :, 1].max():.1f}]")
    print(f"  Z  [{arr[:, :, 2].min():.2f}, {arr[:, :, 2].max():.2f}]  (point bas a {Z_POINT_BAS} m du sol)")
    dz = arr[:, :2, 2].mean(axis=1) - arr[:, 2:, 2].mean(axis=1)
    print(f"  dZ haut-bas : moy {dz.mean():.3f} m, min {dz.min():.3f}, max {dz.max():.3f}")
    v0, v1, v3 = arr[:, 0], arr[:, 1], arr[:, 3]
    n = np.cross(v3 - v0, v1 - v0)
    n[n[:, 2] < 0] *= -1
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    az = (np.degrees(np.arctan2(n[:, 0], n[:, 1])) + 360) % 360
    tilt = np.degrees(np.arccos(n[:, 2]))
    print(f"  normale modules : azimut moy {az.mean():.1f} deg, tilt moy {tilt.mean():.1f} deg")
    cen = arr.reshape(-1, 3).mean(axis=0)
    az_cen = (math.degrees(math.atan2(cen[0] - CAM_X, cen[1] - CAM_Y)) + 360) % 360
    dist = math.hypot(cen[0] - CAM_X, cen[1] - CAM_Y)
    print(f"  centre projet : ({cen[0]:.0f}, {cen[1]:.0f}), azimut {az_cen:.1f} deg "
          f"({az_cen - AZIMUT:+.1f} deg de l'axe), distance {dist:.0f} m")
    dc = [math.hypot(x - CAM_X, y - CAM_Y) for x, y, _ in cloture]
    print(f"Cloture : {len(cloture)} sommets, Z [{min(p[2] for p in cloture):.2f}, "
          f"{max(p[2] for p in cloture):.2f}], distance [{min(dc):.0f}, {max(dc):.0f}] m")
    print(f"Haie projetee : {len(haie) if haie else 0} sommets")
    print(f"Pistes : {len(pistes)} polygones ({sum(p['type'] == 'lourde' for p in pistes)} lourdes)")
    print(f"Zones : {len(zones)} polygones {sorted({z['nom'] for z in zones})}")
    print(f"Topo : {len(topo)} points")
    d = np.hypot(topo[:, 0] - CAM_X, topo[:, 1] - CAM_Y)
    i = d.argmin()
    print(f"  point topo le plus proche de la camera : {d[i]:.1f} m, Z = {topo[i, 2]:.2f} m "
          f"(brief : {CAM_Z_SOL} m, conserve)")


# ---------------------------------------------------------------------------
# Etape 2 - photo + HTML autonome
# ---------------------------------------------------------------------------
def photo_base64(path, width, quality):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    nh = round(h * width / w)
    if width != w:
        im = im.resize((width, nh), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    data = buf.getvalue()
    print(f"Photo : {w}x{h} -> {width}x{nh}, JPEG q{quality} {len(data) / 1e6:.2f} Mo")
    return base64.b64encode(data).decode("ascii"), width, nh


HTML = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Photomontage proto - Sarnois 10A - IMG_6941</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #141414; color: #ddd; font: 13px/1.4 system-ui, sans-serif;
         display: flex; height: 100vh; overflow: hidden; }
  #view { flex: 1; overflow: auto; position: relative; }
  #stagewrap { min-width: 100%; min-height: 100%; display: flex; align-items: flex-start; justify-content: center; }
  #stage { position: relative; height: 98vh; aspect-ratio: {{W}} / {{H}}; margin: 1vh 0; flex: none; }
  #stage img, #stage canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  #stage canvas { cursor: crosshair; }
  #loupe { position: fixed; left: 12px; bottom: 12px; width: 720px; height: 360px; border: 2px solid #ffe600;
           background: #000; box-shadow: 0 0 12px #000; z-index: 5; pointer-events: none; }
  #loupe.hidden { display: none; }
  #panel { width: 400px; flex: none; padding: 12px 16px; background: #1e1e1e; overflow: auto;
           border-left: 1px solid #333; }
  h1 { font-size: 14px; margin: 0 0 4px; }
  .sub { color: #999; margin: 0 0 10px; font-size: 12px; }
  .ctl { margin: 6px 0; }
  .ctl label { display: flex; justify-content: space-between; }
  .ctl output { font-variant-numeric: tabular-nums; color: #ffe600; }
  .ctl input[type=range] { width: 100%; }
  .row { display: flex; flex-wrap: wrap; gap: 4px 12px; margin: 6px 0; }
  .row label { white-space: nowrap; }
  button, select { margin: 4px 6px 0 0; padding: 5px 9px; background: #333; color: #eee; border: 1px solid #555;
           border-radius: 4px; cursor: pointer; font: inherit; }
  button:hover { background: #444; }
  .stats { margin-top: 10px; padding-top: 8px; border-top: 1px solid #333; color: #bbb;
           font-variant-numeric: tabular-nums; white-space: pre-line; }
  .stats b { color: #eee; }
  .warn { color: #ff7a7a; }
  .ok { color: #7aff9a; }
  #vals { margin-top: 6px; font-family: ui-monospace, monospace; font-size: 12px; color: #ffe600; user-select: all; }
  .leg { display: inline-block; width: 14px; height: 10px; vertical-align: middle; margin-right: 4px; border: 1px solid #666; }
  h2 { font-size: 12px; color: #aaa; margin: 10px 0 4px; text-transform: uppercase; letter-spacing: .04em; }
  #plan { width: 368px; height: 300px; display: block; background: #f2f1ec; border: 1px solid #555; }
</style>
</head>
<body>
<div id="view"><div id="stagewrap">
  <div id="stage">
    <img id="photo" src="data:image/jpeg;base64,{{B64}}" alt="IMG_6941">
    <canvas id="ov"></canvas>
  </div>
</div></div>
<canvas id="loupe" class="hidden"></canvas>
<div id="panel">
  <h1>Photomontage proto &mdash; Sarnois 10A</h1>
  <p class="sub">IMG_6941 &middot; iPhone 16 &middot; cam&eacute;ra L93 ({{CAMX}}, {{CAMY}}) &middot; sol {{CAMZ}} m &middot; image {{W}}&times;{{H}} px</p>

  <h2>Cam&eacute;ra</h2>
  <div class="ctl"><label>Azimut (&deg;) <output id="o_az"></output></label>
    <input type="range" id="az" min="{{AZMIN}}" max="{{AZMAX}}" step="0.1" value="{{AZ}}"></div>
  <div class="ctl"><label>Tangage (&deg;) <output id="o_pitch"></output></label>
    <input type="range" id="pitch" min="-15" max="15" step="0.1" value="0"></div>
  <div class="ctl"><label>Roulis (&deg;) <output id="o_roll"></output></label>
    <input type="range" id="roll" min="-5" max="5" step="0.1" value="0"></div>
  <div class="ctl"><label>Focale &eacute;q. 35 mm (mm) <output id="o_f"></output></label>
    <input type="range" id="f" min="{{FMIN}}" max="{{FMAX}}" step="0.1" value="{{F}}"></div>
  <div class="ctl"><label>Hauteur cam&eacute;ra (m) <output id="o_h"></output></label>
    <input type="range" id="h" min="1.0" max="2.5" step="0.05" value="{{H_CAM}}"></div>
  <div class="ctl"><label>Opacit&eacute; (%) <output id="o_op"></output></label>
    <input type="range" id="op" min="0" max="100" step="1" value="{{OP}}"></div>
  <div>
    <button id="reset">R&eacute;initialiser (brief)</button>
    <button id="calage" title="Calage manuel sur les deux eoliennes OSM (validation du 07/09/2026)">Calage &eacute;oliennes</button>
  </div>

  <h2>Couches</h2>
  <div class="row">
    <label><input type="checkbox" class="lay" id="l_tables" checked> <span class="leg" style="background:#1e2a44"></span>Tables</label>
    <label><input type="checkbox" class="lay" id="l_structure" checked> <span class="leg" style="background:#3a3a3a"></span>Structure</label>
    <label><input type="checkbox" class="lay" id="l_cloture" checked> <span class="leg" style="background:#555"></span>Cl&ocirc;ture</label>
    <label><input type="checkbox" class="lay" id="l_haie"> <span class="leg" style="background:#4a8a3c"></span>Haie projet&eacute;e (2 m, masque la cl&ocirc;ture)</label>
    <label><input type="checkbox" class="lay" id="l_pistes" checked> <span class="leg" style="background:#c8b088"></span>Pistes</label>
    <label><input type="checkbox" class="lay" id="l_zones" checked> <span class="leg" style="background:#a8a8a8"></span>Zones techniques</label>
    <label><input type="checkbox" class="lay" id="l_horizon" checked> <span class="leg" style="background:#ffe600"></span>Horizon</label>
    <label><input type="checkbox" class="lay" id="l_reperes" checked> <span class="leg" style="background:#00e5ff"></span>Rep&egrave;res &eacute;oliennes</label>
  </div>

  <h2>Plan (L93) &mdash; c&ocirc;ne de vue courant</h2>
  <canvas id="plan"></canvas>

  <h2>Affichage</h2>
  <div class="row">
    <label>Zoom <select id="zoom">
      <option value="fit">ajust&eacute;</option><option value="1">100 %</option><option value="2">200 %</option>
      <option value="3">300 %</option><option value="4">400 %</option></select></label>
    <button id="center">Centrer sur l'horizon</button>
  </div>
  <div class="row">
    <label><input type="checkbox" id="loupeon"> Loupe</label>
    <label>&times; <select id="loupek"><option>3</option><option selected>4</option><option>6</option><option>8</option></select></label>
    <span style="color:#888">(suit la souris ; clic sur la photo = verrouiller / d&eacute;verrouiller)</span>
  </div>
  <div><button id="export">Exporter PNG</button></div>

  <div class="stats" id="stats"></div>
  <div id="vals"></div>
  <div class="stats" id="mouse"></div>
</div>

<script id="geom" type="application/json">{{GEOM}}</script>
<script>
'use strict';
const G = JSON.parse(document.getElementById('geom').textContent);
const W = {{W}}, H = {{H}};
const INIT = { az: {{AZ}}, pitch: 0, roll: 0, f: {{F}}, h: {{H_CAM}}, op: {{OP}} };
const CALAGE = {{CALAGE}};
const P = Object.assign({}, INIT);
const D2R = Math.PI / 180;
const CLOT_H = {{CLOT_H}}, HAIE_H = {{HAIE_H}}, Z_BAS = {{Z_BAS}};

const img = document.getElementById('photo');
const cv = document.getElementById('ov');
cv.width = W; cv.height = H;
const ctx = cv.getContext('2d');
const stage = document.getElementById('stage');
const view = document.getElementById('view');
const loupe = document.getElementById('loupe');
loupe.width = 1440; loupe.height = 720;   // 2x la taille CSS pour des traits nets
const lctx = loupe.getContext('2d');

const lay = id => document.getElementById('l_' + id).checked;

// --- modele stenope -------------------------------------------------------
// Repere camera : X a droite, Y en haut, Z vers l'avant.
// Monde (E, N, Up) relatif au sol sous la camera ; JS soustrait la hauteur.
function makeCam(P) {
  const a = P.az * D2R, t = P.pitch * D2R, r = P.roll * D2R;
  const sa = Math.sin(a), ca = Math.cos(a);
  const st = Math.sin(t), ct = Math.cos(t);
  const sr = Math.sin(r), cr = Math.cos(r);
  const fpx = W / 24 * P.f;          // cote court capteur 35 mm (24 mm) = largeur image
  const cx = W / 2, cy = H / 2, h = P.h;
  return {
    fpx, h, pos: [0, 0, h],
    toCam(p) {
      const dE = p[0], dN = p[1], dU = p[2] - h;
      // 1. yaw : rotation autour de Up (azimut 0 = Nord, horaire)
      const x1 = dE * ca - dN * sa, z1 = dE * sa + dN * ca, y1 = dU;
      // 2. pitch : rotation autour de X (positif = camera relevee)
      const y2 = y1 * ct - z1 * st, z2 = y1 * st + z1 * ct, x2 = x1;
      // 3. roll : rotation autour de Z
      const x3 = x2 * cr - y2 * sr, y3 = x2 * sr + y2 * cr, z3 = z2;
      return [x3, y3, z3];
    },
    proj(c) {
      if (c[2] <= 0.5) return null;   // derriere ou trop pres
      return [cx + fpx * c[0] / c[2], cy - fpx * c[1] / c[2]];
    },
    // rayon (monde) passant par le pixel (u, v) : inverse de toCam/proj
    ray(u, v) {
      let x = (u - cx) / fpx, y = -(v - cy) / fpx, z = 1;
      // inverse roll
      let x2 = x * cr + y * sr, y2 = -x * sr + y * cr, z2 = z;
      // inverse pitch
      let y1 = y2 * ct + z2 * st, z1 = -y2 * st + z2 * ct, x1 = x2;
      // inverse yaw
      return [x1 * ca + z1 * sa, -x1 * sa + z1 * ca, y1];   // [dE, dN, dU]
    }
  };
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = a => Math.hypot(a[0], a[1], a[2]);

// --- pre-calcul geometrie (independant des curseurs) ------------------------
// Tables : sommets haut0, haut1, bas2, bas3 (bas3 sous haut0, bas2 sous haut1)
const TABLES = G.tables.map(t => {
  const q = t.q;
  const cen = [0, 1, 2].map(k => (q[0][k] + q[1][k] + q[2][k] + q[3][k]) / 4);
  let n = cross(sub(q[3], q[0]), sub(q[1], q[0]));
  if (n[2] < 0) n = n.map(v => -v);
  const L = Math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]);
  const nLegs = Math.max(2, Math.round(L / 5) + 1);
  const legs = [];
  for (let i = 0; i < nLegs; i++) {
    const s = 0.03 + 0.94 * i / (nLegs - 1);
    const bas = lerp(q[3], q[2], s), haut = lerp(q[0], q[1], s);
    const zsol = bas[2] - Z_BAS;
    legs.push([bas, [bas[0], bas[1], zsol]]);        // pied avant (sous le bord bas)
    legs.push([haut, [haut[0], haut[1], zsol]]);     // pied arriere (sous le bord haut)
  }
  const cols = [];
  for (let i = 1; i < t.cols; i++) {
    const s = i / t.cols;
    cols.push([lerp(q[3], q[2], s), lerp(q[0], q[1], s)]);
  }
  const rows = [];
  for (let i = 1; i < t.rows; i++) {
    const s = i / t.rows;
    rows.push([lerp(q[3], q[0], s), lerp(q[2], q[1], s)]);
  }
  return { q, cen, n, legs, cols, rows, dist: norm(cen) };
});

// Cloture et haie : segments entre poteaux (tous les 2,5 m), tries en profondeur
function segmenter(pts, pas) {
  const out = [];
  let carry = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    const L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (L < 1e-6) continue;
    let s = carry, prev = a;
    for (; s <= L; s += pas) {
      const p = lerp(a, b, s / L);
      if (s > 0) out.push([prev, p]);
      prev = p;
    }
    if (norm(sub(b, prev)) > 1e-6) out.push([prev, b]);
    carry = s - L;
  }
  return out.map(([p, q]) => ({ p, q, cen: lerp(p, q, 0.5), dist: norm(lerp(p, q, 0.5)) }));
}
const CLOTURE = segmenter(G.cloture, 2.5);
const HAIE = G.haie ? segmenter(G.haie, 2.5) : [];

// --- dessin ----------------------------------------------------------------
let lwScale = 1;   // epaisseur des traits (px canvas) adaptee a l'echelle d'affichage

function pathPoly(g, cam, pts) {
  const s = pts.map(p => cam.proj(cam.toCam(p)));
  if (s.some(p => p === null)) return false;
  g.beginPath();
  s.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]));
  g.closePath();
  return s;
}
function seg(g, cam, a, b) {
  const s0 = cam.proj(cam.toCam(a)), s1 = cam.proj(cam.toCam(b));
  if (!s0 || !s1) return;
  g.moveTo(s0[0], s0[1]); g.lineTo(s1[0], s1[1]);
}
function polyline(g, cam, pts) {
  let open = false;
  for (const p of pts) {
    const s = cam.proj(cam.toCam(p));
    if (!s) { open = false; continue; }
    if (!open) { g.moveTo(s[0], s[1]); open = true; } else g.lineTo(s[0], s[1]);
  }
}
function mix(c1, c2, t) {   // c = [r,g,b]
  return `rgb(${Math.round(c1[0] + (c2[0] - c1[0]) * t)},${Math.round(c1[1] + (c2[1] - c1[1]) * t)},${Math.round(c1[2] + (c2[2] - c1[2]) * t)})`;
}

function drawSol(g, cam, alpha) {
  g.save();
  g.globalAlpha = alpha;
  if (lay('zones')) {
    for (const z of G.zones) {
      if (!pathPoly(g, cam, z.pts)) continue;
      g.fillStyle = '#a8a8a8'; g.fill();
      g.strokeStyle = '#606060'; g.lineWidth = 1.2 * lwScale; g.stroke();
    }
  }
  if (lay('pistes')) {
    for (const p of G.pistes) {
      if (!pathPoly(g, cam, p.pts)) continue;
      g.fillStyle = p.type === 'lourde' ? '#c8b088' : '#dccfae'; g.fill();
      g.strokeStyle = p.type === 'lourde' ? '#7a6238' : '#9a8a60'; g.lineWidth = 1.3 * lwScale; g.stroke();
    }
  }
  g.restore();
}

function drawTable(g, cam, t, alpha) {
  const toCam = sub(cam.pos, t.cen);
  const face = dot(t.n, toCam) > 0;
  const s = pathPoly(g, cam, t.q);
  if (!s) return null;
  // structure : pieds (arriere derriere la face, avant dessous)
  if (lay('structure')) {
    g.save(); g.globalAlpha = alpha;
    g.strokeStyle = '#3a3a3a'; g.lineWidth = 1.4 * lwScale;
    g.beginPath(); for (const [a, b] of t.legs) seg(g, cam, a, b); g.stroke();
    g.restore();
  }
  if (lay('tables')) {
    g.save(); g.globalAlpha = alpha;
    // face modules (bleu nuit) ou structure arriere (gris) ; eclaircie avec la distance (lisibilite des rangees)
    const k = Math.min(0.45, Math.max(0, (t.dist - 180) / 600));
    g.fillStyle = face ? mix([30, 42, 68], [140, 160, 200], k) : mix([122, 122, 114], [190, 190, 185], k);
    pathPoly(g, cam, t.q); g.fill();
    // lignes de modules (colonnes et rangee intermediaire), discretes
    g.strokeStyle = 'rgba(255,255,255,0.28)'; g.lineWidth = 0.7 * lwScale;
    g.beginPath(); for (const [a, b] of t.cols) seg(g, cam, a, b); for (const [a, b] of t.rows) seg(g, cam, a, b); g.stroke();
    // contour : bas et cotes sombres, arete haute claire
    g.strokeStyle = '#0c1020'; g.lineWidth = 1.2 * lwScale;
    g.beginPath(); seg(g, cam, t.q[1], t.q[2]); seg(g, cam, t.q[2], t.q[3]); seg(g, cam, t.q[3], t.q[0]); g.stroke();
    g.strokeStyle = '#b8c4dc'; g.lineWidth = 1.4 * lwScale;
    g.beginPath(); seg(g, cam, t.q[0], t.q[1]); g.stroke();
    g.restore();
  }
  return face;
}

function drawPanneau(g, cam, sgm, alpha) {
  // cloture : poteau a chaque extremite, fil haut, fil intermediaire, ligne au sol
  const p = sgm.p, q = sgm.q;
  g.save(); g.globalAlpha = alpha;
  g.strokeStyle = '#666'; g.lineWidth = 0.9 * lwScale;
  g.beginPath();
  seg(g, cam, p, q);
  seg(g, cam, [p[0], p[1], p[2] + CLOT_H], [q[0], q[1], q[2] + CLOT_H]);
  seg(g, cam, [p[0], p[1], p[2] + CLOT_H / 2], [q[0], q[1], q[2] + CLOT_H / 2]);
  g.stroke();
  g.strokeStyle = '#2e2e2e'; g.lineWidth = 1.5 * lwScale;
  g.beginPath(); seg(g, cam, p, [p[0], p[1], p[2] + CLOT_H]); g.stroke();
  g.restore();
}

function drawHaie(g, cam, sgm, alpha) {
  const p = sgm.p, q = sgm.q;
  const s = pathPoly(g, cam, [p, q, [q[0], q[1], q[2] + HAIE_H], [p[0], p[1], p[2] + HAIE_H]]);
  if (!s) return;
  g.save(); g.globalAlpha = alpha * 0.45;
  g.fillStyle = '#4a8a3c'; g.fill();
  g.strokeStyle = '#2f5c26'; g.lineWidth = 0.8 * lwScale; g.stroke();
  g.restore();
}

function horizonPts(cam) {
  const pts = [];
  for (let d = -85; d <= 85; d += 1) {
    const a = (P.az + d) * D2R;
    pts.push([1e6 * Math.sin(a), 1e6 * Math.cos(a), cam.h]);
  }
  return pts;
}
function drawHorizon(g, cam) {
  g.save();
  g.globalAlpha = 0.85;
  g.strokeStyle = '#ffe600'; g.lineWidth = 1.3 * lwScale;
  g.setLineDash([10 * lwScale, 10 * lwScale]);
  g.beginPath(); polyline(g, cam, horizonPts(cam)); g.stroke();
  g.restore();
}

// --- plan (vue de dessus, L93 relatif camera) ---------------------------------
const plan = document.getElementById('plan');
plan.width = 736; plan.height = 600;
const pctx = plan.getContext('2d');
const PLAN = (() => {
  const xs = [0], ys = [0];
  const push = pts => { for (const p of pts) { xs.push(p[0]); ys.push(p[1]); } };
  for (const t of G.tables) push(t.q);
  push(G.cloture);
  for (const p of G.pistes) push(p.pts);
  const minX = Math.min(...xs) - 30, maxX = Math.max(...xs) + 30, minY = Math.min(...ys) - 30, maxY = Math.max(...ys) + 30;
  const s = Math.min(plan.width / (maxX - minX), plan.height / (maxY - minY));
  const ox = (plan.width - (maxX - minX) * s) / 2, oy = (plan.height - (maxY - minY) * s) / 2;
  return { s, toPx: p => [ox + (p[0] - minX) * s, plan.height - oy - (p[1] - minY) * s] };
})();
function planPoly(pts, fill, stroke, lw) {
  pctx.beginPath();
  pts.forEach((p, i) => { const q = PLAN.toPx(p); i ? pctx.lineTo(q[0], q[1]) : pctx.moveTo(q[0], q[1]); });
  if (fill) { pctx.closePath(); pctx.fillStyle = fill; pctx.fill(); }
  if (stroke) { pctx.strokeStyle = stroke; pctx.lineWidth = lw || 1; pctx.stroke(); }
}
function drawPlan(cam) {
  const g = pctx;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, plan.width, plan.height);
  // cercles de distance
  g.strokeStyle = '#c8c8c0'; g.lineWidth = 1; g.fillStyle = '#909088'; g.font = '16px system-ui';
  const c0 = PLAN.toPx([0, 0]);
  for (const r of [100, 200, 300, 400]) {
    g.beginPath(); g.arc(c0[0], c0[1], r * PLAN.s, 0, 2 * Math.PI); g.stroke();
    g.fillText(`${r} m`, c0[0] + 4, c0[1] - r * PLAN.s - 3);
  }
  for (const z of G.zones) planPoly(z.pts, '#b8b8b8', '#707070', 1);
  for (const p of G.pistes) planPoly(p.pts, p.type === 'lourde' ? '#c8b088' : '#dccfae', '#8a7648', 1);
  planPoly(G.cloture, null, '#222', 2.5);
  if (G.haie) planPoly(G.haie, null, '#3c7a30', 3);
  for (const t of G.tables) planPoly(t.q, '#1e2a44', null);
  // cone de vue courant
  const hf = Math.atan(12 / P.f), a = P.az * D2R, Lr = 700;
  g.strokeStyle = '#e00'; g.lineWidth = 2;
  for (const d of [-hf, 0, hf]) {
    g.beginPath(); g.moveTo(c0[0], c0[1]);
    const q = PLAN.toPx([Lr * Math.sin(a + d), Lr * Math.cos(a + d)]);
    g.setLineDash(d === 0 ? [6, 6] : []); g.lineTo(q[0], q[1]); g.stroke();
  }
  g.setLineDash([]);
  g.fillStyle = '#e00'; g.beginPath(); g.arc(c0[0], c0[1], 6, 0, 2 * Math.PI); g.fill();
  g.fillStyle = '#333'; g.font = '15px system-ui';
  g.fillText(`caméra · azimut ${P.az.toFixed(1)}° · champ ${(2 * hf / D2R).toFixed(1)}°`, 8, plan.height - 10);
  g.fillText('N ↑', plan.width - 40, 22);
}
function drawReperes(g, cam) {
  g.save();
  g.globalAlpha = 1;
  g.strokeStyle = '#00e5ff'; g.fillStyle = '#00e5ff';
  g.lineWidth = 1.5 * lwScale; g.setLineDash([6 * lwScale, 4 * lwScale]);
  g.font = `${13 * lwScale}px system-ui, sans-serif`;
  for (const r of G.reperes) {
    const s = cam.proj(cam.toCam([r.xy[0], r.xy[1], cam.h]));
    if (!s) continue;
    g.beginPath(); g.moveTo(s[0], s[1] + 40 * lwScale); g.lineTo(s[0], s[1] - 300 * lwScale); g.stroke();
    g.fillText(r.nom, s[0] + 5 * lwScale, s[1] - 290 * lwScale);
  }
  g.restore();
}

// Dessine tout l'overlay dans le contexte g (canvas principal ou loupe). Retourne des stats.
function drawOverlay(g, cam) {
  const alpha = P.op / 100;
  drawSol(g, cam, alpha);
  // algorithme du peintre sur tables + panneaux de cloture + haie : du plus loin au plus pres
  const items = [];
  for (const t of TABLES) items.push({ d: t.dist, k: 't', o: t });
  if (lay('cloture')) for (const s of CLOTURE) items.push({ d: s.dist, k: 'c', o: s });
  if (lay('haie')) for (const s of HAIE) items.push({ d: s.dist, k: 'h', o: s });
  items.sort((a, b) => b.d - a.d);
  let nBleu = 0, nGris = 0, nHors = 0;
  let umin = Infinity, umax = -Infinity, vmin = Infinity, vmax = -Infinity;
  for (const it of items) {
    if (it.k === 't') {
      const face = drawTable(g, cam, it.o, alpha);
      if (face === null) { nHors++; continue; }
      if (face) nBleu++; else nGris++;
      for (const p of it.o.q) {
        const s = cam.proj(cam.toCam(p));
        umin = Math.min(umin, s[0]); umax = Math.max(umax, s[0]); vmin = Math.min(vmin, s[1]); vmax = Math.max(vmax, s[1]);
      }
    } else if (it.k === 'c') drawPanneau(g, cam, it.o, alpha);
    else drawHaie(g, cam, it.o, alpha);
  }
  if (lay('reperes')) drawReperes(g, cam);
  if (lay('horizon')) drawHorizon(g, cam);
  return { nBleu, nGris, nHors, umin, umax, vmin, vmax };
}

function horizonV(cam) {
  const c = cam.proj(cam.toCam([1e6 * Math.sin(P.az * D2R), 1e6 * Math.cos(P.az * D2R), cam.h]));
  return c ? c[1] : NaN;
}

function draw() {
  const cam = makeCam(P);
  const scale = stage.getBoundingClientRect().width / W;      // px ecran par px canvas
  lwScale = Math.min(4, Math.max(1, 1 / scale));
  ctx.clearRect(0, 0, W, H);
  const st = drawOverlay(ctx, cam);
  const vh = horizonV(cam);
  const hfov = 2 * Math.atan(12 / P.f) / D2R, vfov = 2 * Math.atan(18 / P.f) / D2R;
  const grisTxt = st.nGris ? `<span class="warn">${st.nGris} gris (face structure) : v&eacute;rifier l'ordre des sommets</span>`
                           : `<span class="ok">0 gris</span>`;
  document.getElementById('stats').innerHTML =
    `<b>f</b> = ${cam.fpx.toFixed(0)} px &middot; champ ${hfov.toFixed(1)}&deg; &times; ${vfov.toFixed(1)}&deg; &middot; affichage ${(scale * 100).toFixed(0)} %\n` +
    `<b>Tables</b> : ${st.nBleu} bleu (face modules), ${grisTxt}, ${st.nHors} rejet&eacute;es (Zc &le; 0,5 m)\n` +
    `<b>Emprise tables</b> : u [${st.umin.toFixed(0)}, ${st.umax.toFixed(0)}] &middot; v [${st.vmin.toFixed(0)}, ${st.vmax.toFixed(0)}] px\n` +
    `<b>Horizon</b> sur l'axe central : v = ${vh.toFixed(0)} px (${(100 * vh / H).toFixed(1)} % de la hauteur)`;
  document.getElementById('vals').textContent =
    `az=${P.az.toFixed(1)}  pitch=${P.pitch.toFixed(1)}  roll=${P.roll.toFixed(1)}  f=${P.f.toFixed(1)}  h=${P.h.toFixed(2)}  op=${P.op}`;
  drawPlan(cam);
  drawLoupe();
}

// --- loupe -------------------------------------------------------------------
const L = { on: false, k: 4, u: W / 2, v: H / 2, lock: false };
function drawLoupe() {
  if (!L.on) { loupe.classList.add('hidden'); return; }
  loupe.classList.remove('hidden');
  const k = L.k * 2;                                     // canvas loupe = 2x CSS
  const sw = loupe.width / k, sh = loupe.height / k;
  const sx = Math.min(Math.max(0, L.u - sw / 2), W - sw), sy = Math.min(Math.max(0, L.v - sh / 2), H - sh);
  lctx.setTransform(1, 0, 0, 1, 0, 0);
  lctx.clearRect(0, 0, loupe.width, loupe.height);
  lctx.drawImage(img, sx, sy, sw, sh, 0, 0, loupe.width, loupe.height);
  const save = lwScale;
  lwScale = 2 / k;                                       // traits ~1 px CSS dans la loupe
  lctx.setTransform(k, 0, 0, k, -sx * k, -sy * k);
  drawOverlay(lctx, makeCam(P));
  lwScale = save;
  lctx.setTransform(1, 0, 0, 1, 0, 0);
  lctx.strokeStyle = '#ffe600'; lctx.lineWidth = 1;
  lctx.strokeRect(0.5, 0.5, loupe.width - 1, loupe.height - 1);
  lctx.fillStyle = '#ffe600'; lctx.font = '22px system-ui';
  lctx.fillText(`x${L.k}  u ${L.u.toFixed(0)}  v ${L.v.toFixed(0)}${L.lock ? '  (verrouillée)' : ''}`, 10, 28);
}

// --- UI ---------------------------------------------------------------------
const FMT = { az: v => v.toFixed(1), pitch: v => v.toFixed(1), roll: v => v.toFixed(1),
              f: v => v.toFixed(1), h: v => v.toFixed(2), op: v => v.toFixed(0) };
for (const k of Object.keys(P)) {
  const el = document.getElementById(k), out = document.getElementById('o_' + k);
  const upd = () => { P[k] = parseFloat(el.value); out.textContent = FMT[k](P[k]); };
  el.addEventListener('input', () => { upd(); draw(); });   // redessin a chaque input, sans throttling
  upd();
}
function applyPreset(v) {
  for (const k of Object.keys(v)) {
    const el = document.getElementById(k); el.value = v[k];
    el.dispatchEvent(new Event('input'));
  }
}
document.getElementById('reset').addEventListener('click', () => applyPreset(INIT));
document.getElementById('calage').addEventListener('click', () => applyPreset(CALAGE));
for (const el of document.querySelectorAll('.lay')) el.addEventListener('change', draw);

const zoomSel = document.getElementById('zoom');
zoomSel.addEventListener('change', () => {
  const z = zoomSel.value;
  stage.style.height = z === 'fit' ? '' : `${H * parseFloat(z)}px`;
  draw();
});
document.getElementById('center').addEventListener('click', () => {
  const r = stage.getBoundingClientRect(), scale = r.width / W;
  const vh = horizonV(makeCam(P));
  view.scrollTop = vh * scale - view.clientHeight / 2;
  view.scrollLeft = (W / 2) * scale - view.clientWidth / 2;
});
document.getElementById('loupeon').addEventListener('change', e => { L.on = e.target.checked; drawLoupe(); });
document.getElementById('loupek').addEventListener('change', e => { L.k = parseFloat(e.target.value); drawLoupe(); });
window.addEventListener('resize', draw);

function mouseUV(e) {
  const r = cv.getBoundingClientRect();
  return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height];
}
cv.addEventListener('mousemove', e => {
  const [u, v] = mouseUV(e);
  const cam = makeCam(P), d = cam.ray(u, v);
  let sol = '';
  if (d[2] < -1e-6) {                                   // intersection avec le plan sol (Z = sol camera)
    const t = -cam.h / d[2];
    const x = d[0] * t, y = d[1] * t;
    const az = ((Math.atan2(x, y) / D2R) + 360) % 360;
    sol = ` · sol plat à ${Math.hypot(x, y).toFixed(0)} m, azimut ${az.toFixed(1)}°, L93 (${(G.camera_l93[0] + x).toFixed(0)}, ${(G.camera_l93[1] + y).toFixed(0)})`;
  }
  document.getElementById('mouse').textContent =
    `Souris : u = ${u.toFixed(0)} px, v = ${v.toFixed(0)} px (${(100 * v / H).toFixed(1)} % hauteur)${sol}`;
  if (L.on && !L.lock) { L.u = u; L.v = v; drawLoupe(); }
});
cv.addEventListener('click', e => {
  if (!L.on) return;
  const [u, v] = mouseUV(e);
  L.lock = !L.lock; L.u = u; L.v = v; drawLoupe();
});
// Export : photo + overlay redessine a l'echelle 1 (traits fins), pas le canvas d'affichage
function renderExport() {
  const oc = document.createElement('canvas');
  oc.width = W; oc.height = H;
  const c = oc.getContext('2d');
  c.drawImage(img, 0, 0, W, H);
  const save = lwScale; lwScale = 1;
  drawOverlay(c, makeCam(P));
  lwScale = save;
  return oc;
}
document.getElementById('export').addEventListener('click', () => {
  const oc = renderExport();
  oc.toBlob(b => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(b);
    a.download = `photomontage_IMG_6941_az${P.az.toFixed(1)}_p${P.pitch.toFixed(1)}_r${P.roll.toFixed(1)}_f${P.f.toFixed(1)}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }, 'image/png');
});

if (img.complete) draw(); else img.addEventListener('load', draw);
draw();
</script>
</body>
</html>
"""


def main():
    print(f"DXF   : {DXF_PATH.name}")
    doc = ezdxf.readfile(DXF_PATH)
    msp = doc.modelspace()

    tables = extraire_tables(msp)
    topo = extraire_topo(msp)
    rehausser_point_bas(tables, topo)
    cloture, haie, pistes, zones = extraire_lignes(msp, topo)
    controle(tables, cloture, haie, pistes, zones, topo)

    geom = {
        "camera_l93": [CAM_X, CAM_Y, CAM_Z_SOL],
        "note": "coordonnees relatives au sol sous la camera (X-Xcam, Y-Ycam, Z-Zsol), m",
        "tables": [{"q": relatif(t["q"]), "rows": t["rows"], "cols": t["cols"]} for t in tables],
        "cloture": relatif(cloture),
        "haie": relatif(haie) if haie else None,
        "pistes": [{"type": p["type"], "pts": relatif(p["pts"])} for p in pistes],
        "zones": [{"nom": z["nom"], "pts": relatif(z["pts"])} for z in zones],
        "reperes": [{"nom": r["nom"],
                     "xy": [round(r["xy"][0] - CAM_X, 1), round(r["xy"][1] - CAM_Y, 1)]}
                    for r in REPERES],
    }
    geom_js = json.dumps(geom, separators=(",", ":"))
    OUT_JSON.write_text(geom_js, encoding="utf-8")
    print(f"JSON  : {OUT_JSON.name} ({OUT_JSON.stat().st_size / 1e3:.0f} ko)")

    b64, w, h = photo_base64(PHOTO_PATH, HTML_W, JPEG_Q)
    if len(b64) / 1e6 > HTML_MAX_MB - 0.3:
        b64, w, h = photo_base64(PHOTO_PATH, 1800, JPEG_Q)
    html = (HTML
            .replace("{{B64}}", b64)
            .replace("{{GEOM}}", geom_js)
            .replace("{{W}}", str(w)).replace("{{H}}", str(h))
            .replace("{{AZ}}", f"{AZIMUT:.1f}")
            .replace("{{AZMIN}}", f"{AZIMUT - AZ_PLAGE:.1f}").replace("{{AZMAX}}", f"{AZIMUT + AZ_PLAGE:.1f}")
            .replace("{{F}}", f"{FOCALE:.1f}")
            .replace("{{FMIN}}", f"{F_MIN:.1f}").replace("{{FMAX}}", f"{F_MAX:.1f}")
            .replace("{{H_CAM}}", f"{CAM_H:.2f}")
            .replace("{{OP}}", str(CALAGE["op"]))
            .replace("{{CALAGE}}", json.dumps(CALAGE))
            .replace("{{CLOT_H}}", f"{CLOTURE_H:.2f}").replace("{{HAIE_H}}", f"{HAIE_H:.2f}")
            .replace("{{Z_BAS}}", f"{Z_POINT_BAS:.2f}")
            .replace("{{CAMX}}", f"{CAM_X:.0f}").replace("{{CAMY}}", f"{CAM_Y:.0f}")
            .replace("{{CAMZ}}", f"{CAM_Z_SOL:.1f}"))
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"HTML  : {OUT_HTML.name} ({OUT_HTML.stat().st_size / 1e6:.2f} Mo)")


if __name__ == "__main__":
    main()
