#!/usr/bin/env python3
"""Recompose une planche de feuilles en TOUFFE, a partir d'un atlas ambientCG.

Pourquoi. Les planches d'ambientCG presentent leurs feuilles bien rangees, avec
du vide entre elles — LeafSet024 sur une grille 3 x 3, LeafSet010 en quinconce.
Appliquee telle quelle a une carte de feuillage, cette mise en page se voit :
la haie rendue porte une trame, d'autant plus lisible que les cartes tournees
face a l'oeil montrent la planche entiere. Et pour refermer la masse malgre ces
vides, il faudrait multiplier les quads.

On decoupe donc les feuilles une a une — par COMPOSANTES CONNEXES de l'alpha,
ce qui marche quelle que soit la mise en page — et on les redistribue :
rotation quelconque, echelle variable, positions tirees au sort, avec
recouvrement. La planche obtenue est une touffe, sans direction privilegiee ni
lattis, qui couvre 60 a 65 % de sa surface.

ECHELLE. Par convention toutes les planches de ce dossier valent 40 x 40 cm
reels pour 1024 px (`exporter_blender.ATLAS_METRES`), et leurs feuilles sont
ramenees a une taille commune. Deux atlas sont donc interchangeables sans
retoucher la taille des cartes.

Usage :
    python atlas_feuilles.py                 # LeafSet024, feuille ovale
    python atlas_feuilles.py LeafSet010      # feuille palmee
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
TEX = HERE / "textures"

DEFAUT = "LeafSet024"
CIBLE_PX = 330          # plus grand cote d'une feuille sur la planche recomposee
AIRE_MIN = 2000         # px : en deca, c'est un debris de decoupe, pas une feuille
COUVERTURE = 0.60       # visee ; le semis s'arrete des qu'elle est atteinte
SEMIS_MAX = 80
GRAINE = 7


def _feuilles(rgba, aire_min=AIRE_MIN):
    """Decoupe la planche en feuilles isolees, par composantes connexes de l'alpha.

    Plus robuste qu'un decoupage en cellules : il n'y a pas de mise en page a
    connaitre, et une planche en quinconce passe aussi bien qu'une grille.
    """
    lab, n = ndimage.label(rgba[..., 3] > 127)
    out = []
    for i, tranche in enumerate(ndimage.find_objects(lab), start=1):
        if tranche is None or (lab[tranche] == i).sum() < aire_min:
            continue
        bout = rgba[tranche].copy()
        # on efface les voisines qui depassent dans la meme boite englobante,
        # sinon une feuille arrive flanquee d'un morceau de sa voisine
        bout[..., 3] = np.where(lab[tranche] == i, bout[..., 3], 0)
        out.append(bout)
    return out


def composer(nom=DEFAUT, graine=GRAINE, couverture=COUVERTURE, cible_px=CIBLE_PX):
    src_c, src_o = TEX / f"{nom}_Color.png", TEX / f"{nom}_Opacity.png"
    for f in (src_c, src_o):
        if not f.exists():
            sys.exit(f"manque {f} — telecharger {nom} sur ambientCG (CC0)")
    co = np.array(Image.open(src_c).convert("RGB")).astype(np.uint8)
    op = np.array(Image.open(src_o).convert("L")).astype(np.uint8)
    rgba = np.dstack([co, op])
    H, W = rgba.shape[:2]
    feuilles = _feuilles(rgba)
    if not feuilles:
        sys.exit(f"aucune feuille trouvee dans {nom}")
    print(f"{nom} : {len(feuilles)} feuilles decoupees "
          f"({', '.join(f'{f.shape[1]}x{f.shape[0]}' for f in feuilles)})")

    # SEMIS A COUVERTURE VISEE, et non a nombre fixe : une planche de quatre
    # feuilles palmees (LeafSet010) et une de neuf feuilles ovales
    # (LeafSet024) ne se referment pas au meme compte. Viser la couverture rend
    # les deux atlas equivalents, et le script reproductible pour un troisieme.
    rng = np.random.default_rng(graine)
    planche = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for pose in range(SEMIS_MAX):
        if pose and (np.array(planche)[..., 3] > 127).mean() >= couverture:
            break
        f = feuilles[int(rng.integers(0, len(feuilles)))]
        src = Image.fromarray(f, "RGBA")
        # ramenee a la taille commune, puis variee : deux atlas restent
        # interchangeables sans toucher a la taille des cartes.
        k = cible_px / max(src.width, src.height) * float(rng.uniform(0.80, 1.15))
        src = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))),
                         Image.LANCZOS)
        # expand=True : sans lui, la rotation rogne la feuille dans son cadre
        src = src.rotate(float(rng.uniform(0, 360)), Image.BICUBIC, expand=True)
        # Centre tire dans la planche, en la laissant DEBORDER : une feuille
        # coupee au bord est normale dans une touffe, et l'alternative —
        # confiner les centres — creuse une bordure vide tout autour.
        x = int(rng.integers(0, W)) - src.width // 2
        y = int(rng.integers(0, H)) - src.height // 2
        planche.alpha_composite(src, dest=(max(0, x), max(0, y)),
                                source=(max(0, -x), max(0, -y)))

    a = np.array(planche)
    plein = a[..., 3] > 127
    couv = float(plein.mean())
    # La couleur doit rester definie LA OU l'alpha est nul : Cycles interpole la
    # couleur et l'alpha separement, et un fond noir bave en lisere sombre sur
    # le pourtour de chaque feuille. On remplit donc le vide avec la teinte
    # moyenne des feuilles.
    moy = a[plein][:, :3].mean(axis=0)
    fond = np.where(plein[..., None], a[..., :3], moy.astype(np.uint8))

    TEX.mkdir(exist_ok=True)
    dst_c = TEX / f"touffe_{nom}_Color.png"
    dst_o = TEX / f"touffe_{nom}_Opacity.png"
    Image.fromarray(fond.astype(np.uint8), "RGB").save(dst_c)
    Image.fromarray(a[..., 3], "L").save(dst_o)

    # moyenne PONDEREE PAR L'ALPHA : c'est la teinte que verra le rendu
    al = a[..., 3].astype(float) / 255.0
    m = (a[..., :3].astype(float) * al[..., None]).sum(axis=(0, 1)) / al.sum()
    print(f"couverture   : {couv * 100:.1f} % de la planche, en {pose + 1} feuilles posees")
    print(f"ATLAS_MOYENNE = {tuple(round(float(x), 1) for x in m)}")
    print(f"ecrit : {dst_c.name}, {dst_o.name}")
    return tuple(float(x) for x in m)


if __name__ == "__main__":
    composer(sys.argv[1] if len(sys.argv) > 1 else DEFAUT)
