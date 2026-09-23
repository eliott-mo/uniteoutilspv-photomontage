#!/usr/bin/env python3
"""Materiaux procedured pour Blender : beton peint et grave.

Pourquoi procedural plutot qu'un aplat : a 26 m, un local technique dessine
comme un rectangle d'une seule couleur se lit comme un rectangle d'une seule
couleur. Ce qui trahit n'est pas la geometrie, c'est l'absence de joints de
banche, de coulures sous la couvertine et de granulometrie au sol.

Tout est indexe sur les COORDONNEES OBJET, qui sont en metres dans ce projet
(`exporter_*.py` produit du metre). Un joint tous les 1,20 m est donc un joint
tous les 1,20 m quelle que soit la taille du volume, et le meme materiau sert
pour un poste de 5,5 m et pour un local de stockage de 12,2 m.

  PALETTE : mesuree, pas choisie
  ------------------------------
Les valeurs de `RAL` sont les aplats reellement traces dans les elevations des
PC5 HOCH (19 dossiers depouilles), pas des tables RAL recopiees. Le releve des
mentions ecrites donne la hierarchie : RAL 6003 vert olive domine partout
(53 % des citations sur le poste, 58 % sur la citerne, 67 % sur la cloture),
RAL 7013 brun gris vient second. Un local technique de centrale PV est donc
un prefabrique PEINT en vert olive sombre, pas du beton clair brut.
"""
from pathlib import Path

try:
    import bpy
except ImportError:                      # import hors de Blender, pour les tests
    bpy = None


HERE = Path(__file__).resolve().parent

#   ATLAS DE FEUILLES
#   -----------------
# Source : ambientCG LeafSet024, sous licence CC0 (domaine public, usage
# commercial libre, sans attribution) — des feuilles ovales dentees
# photographiees, 40 x 40 cm reels, environ 12 cm par feuille : la feuille du
# charme ou du noisetier, essences de haie champetre.
#
# La planche utilisee n'est pas la source mais sa recomposition en touffe par
# `atlas_feuilles.py`, la grille 3 x 3 d'origine se lisant comme une trame de
# pois sur la haie rendue.
#
#   L'ATLAS N'EST PAS LE DEFAUT
#   ---------------------------
# Il apporte ce qu'un alpha calcule ne sait pas inventer — nervure,
# dissymetrie, morsures d'insecte — mais ses feuilles sont OVALES, et a 17 m
# une feuille ovale de 5 px rend un aplat la ou une feuille LOBEE accroche la
# lumiere par ses decoupes. Compare aux deux rendus, le motif calcule tient
# mieux la distance ; c'est le jugement d'Eliott Moreau du 21/09/2026, et il
# est conforme a ce qu'on voit.
#
# Le materiau prend donc `_alpha_touffe` par defaut. Pour demander l'atlas,
# poser `atlas_feuilles` a vrai dans les materiaux de la scene.
ATLAS_NOM = "touffe_LeafSet010"
ATLAS_COULEUR = HERE / "textures" / f"{ATLAS_NOM}_Color.png"
ATLAS_OPACITE = HERE / "textures" / f"{ATLAS_NOM}_Opacity.png"
ATLAS_MOYENNE = (115.2, 156.8, 35.4)
"""Couleur moyenne des feuilles de l'atlas, PONDEREE PAR L'ALPHA.

Mesuree sur le fichier, pas lue sur la fiche : elle sert a ramener l'atlas sur
la teinte de vegetation relevee dans la photo, pour que `GAIN_FEUILLAGE` garde
un sens. Sans cette normalisation, la couleur du rendu serait celle du studio
d'ambientCG et non celle du ciel de Sarnois."""


# Aplats releves dans les PC5 (surface cumulee sur les pages de facade).
RAL = {
    "6003": (61, 69, 46),      # vert olive   - la teinte de reference UNITe/HOCH
    "7013": (87, 80, 68),      # brun gris    - variante
    "6009": (39, 53, 42),      # vert sapin
    "6032": (59, 170, 114),    # vert de securite - citerne, un seul dossier
    "6011": (104, 130, 91),    # vert reseda - CITERNE SOUPLE, releve sur la
                               # planche PC5 « CITERNE ~ 120 m3 » fournie
}

# Couvertine : les PC5 la tracent systematiquement PLUS CLAIRE que le corps et
# debordante. C'est elle qui donne l'ombre portee sous l'acrotere, donc la
# lecture du volume.
COUVERTINE = (122, 120, 114)


def _srgb_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgba(c):
    return (*[_srgb_lin(v) for v in c], 1.0)


def _teinte(c, k, vers=None):
    """Eclaircit (k>1) ou assombrit (k<1), en tirant vers `vers` si donne."""
    if vers is None:
        return tuple(min(255.0, max(0.0, v * k)) for v in c)
    return tuple(v + (w - v) * k for v, w in zip(c, vers))


def _n(nt, cls, **kw):
    n = nt.nodes.new(cls)
    for k, v in kw.items():
        if k in n.inputs:
            n.inputs[k].default_value = v
        else:
            setattr(n, k, v)
    return n


def _mix(nt, fac, c1, c2):
    """MixRGB : `fac` est une sortie de noeud ou un flottant."""
    m = _n(nt, "ShaderNodeMixRGB")
    if hasattr(fac, "node"):
        nt.links.new(fac, m.inputs["Fac"])
    else:
        m.inputs["Fac"].default_value = fac
    for nom, c in (("Color1", c1), ("Color2", c2)):
        if hasattr(c, "node"):
            nt.links.new(c, m.inputs[nom])
        else:
            m.inputs[nom].default_value = _rgba(c)
    return m.outputs["Color"]


def _raie(nt, coord, pas, largeur):
    """1 sur une raie de `largeur` m tous les `pas` m, 0 ailleurs.

    Meme procede que la maille du grillage : un WRAP puis un seuil. Un Wave
    donnerait une sinusoide, c'est-a-dire une ondulation, pas un joint.
    """
    w = _n(nt, "ShaderNodeMath", operation="WRAP")
    w.inputs[1].default_value = pas
    w.inputs[2].default_value = 0.0
    nt.links.new(coord, w.inputs[0])
    s = _n(nt, "ShaderNodeMath", operation="LESS_THAN")
    s.inputs[1].default_value = largeur
    nt.links.new(w.outputs["Value"], s.inputs[0])
    return s.outputs["Value"]


def _max(nt, *sorties):
    cur = sorties[0]
    for s in sorties[1:]:
        m = _n(nt, "ShaderNodeMath", operation="MAXIMUM")
        nt.links.new(cur, m.inputs[0])
        nt.links.new(s, m.inputs[1])
        cur = m.outputs["Value"]
    return cur


def _rampe(nt, entree, arrets):
    r = _n(nt, "ShaderNodeValToRGB")
    nt.links.new(entree, r.inputs["Fac"])
    el = r.color_ramp.elements
    while len(el) > 1:
        el.remove(el[-1])
    for i, (pos, val) in enumerate(arrets):
        e = el[0] if i == 0 else el.new(pos)
        e.position = pos
        e.color = _rgba(val) if isinstance(val, tuple) else (val, val, val, 1.0)
    return r.outputs["Color"]


def beton_peint(nom="beton", base=None, hauteur=3.0, pas_joint=1.20,
                usure=1.0):
    """Prefabrique beton peint : joints de banche, grain, coulures, boue.

    `hauteur` est celle du volume, en metres : elle sert a placer les coulures
    sous la couvertine. `usure` de 0 (neuf) a 1,5 (sale).
    """
    base = base or RAL["6003"]
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]

    tc = _n(nt, "ShaderNodeTexCoord")
    sep = _n(nt, "ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])

    # 1. joints de banche. Les raies en X et en Y se cumulent par un MAXIMUM :
    #    sur une face perpendiculaire a X la raie en X est constante sur toute
    #    la face, donc invisible, et c'est la raie en Y qui trace les verticales.
    #    Le maximum donne donc des joints justes sur les quatre faces, sans
    #    rayer celle qui regarde l'observateur.
    joints = _max(nt,
                  _raie(nt, sep.outputs["X"], pas_joint, 0.016),
                  _raie(nt, sep.outputs["Y"], pas_joint, 0.016),
                  _raie(nt, sep.outputs["Z"], 1.05, 0.014))

    # 2. grain de surface et marbrures.
    #    ECHELLE : a 26 m avec cette focale, un pixel couvre environ 2 cm sur le
    #    mur. Un grain de 1,7 cm, physiquement juste, est donc sous-pixellique et
    #    se moyenne en un aplat — c'etait le cas de la premiere version. Ce qui
    #    porte la matiere a cette distance, ce sont les taches decimetriques.
    grain = _n(nt, "ShaderNodeTexNoise", Scale=14.0, Detail=6.0, Roughness=0.65)
    nt.links.new(tc.outputs["Object"], grain.inputs["Vector"])
    marbre = _n(nt, "ShaderNodeTexNoise", Scale=0.9, Detail=4.0, Roughness=0.55)
    nt.links.new(tc.outputs["Object"], marbre.inputs["Vector"])

    # 3. coulures : un bruit ecrase en Z, donc etire verticalement, et masque
    #    par un degrade qui ne le laisse vivre que sous la couvertine.
    map_c = _n(nt, "ShaderNodeMapping")
    map_c.inputs["Scale"].default_value = (2.2, 2.2, 0.05)
    nt.links.new(tc.outputs["Object"], map_c.inputs["Vector"])
    coul = _n(nt, "ShaderNodeTexNoise", Scale=4.5, Detail=6.0, Roughness=0.70)
    nt.links.new(map_c.outputs["Vector"], coul.inputs["Vector"])
    # Z ramene a [0,1] AVANT la rampe : une ColorRamp sature au-dela de 1, et
    # lui donner des metres faisait deborder les coulures sur tout le mur.
    zn = _n(nt, "ShaderNodeMath", operation="DIVIDE")
    zn.inputs[1].default_value = max(hauteur, 0.1)
    nt.links.new(sep.outputs["Z"], zn.inputs[0])
    haut = _rampe(nt, zn.outputs["Value"], [(max(0.0, (hauteur - 1.6) / hauteur), 0.0),
                                            (min(1.0, (hauteur - 0.10) / hauteur), 1.0)])
    # meme raison : les coulures doivent naitre dans la queue haute du bruit,
    # donc juste au-dessus de 0,5, sinon elles n'apparaissent jamais.
    seuil = _rampe(nt, coul.outputs["Fac"],
                   [(0.56, 0.0), (0.66, min(1.0, 0.45 * usure))])
    mc = _n(nt, "ShaderNodeMixRGB", blend_type="MULTIPLY")
    mc.inputs["Fac"].default_value = 1.0        # produit pur, cf. ci-dessus
    nt.links.new(seuil, mc.inputs["Color1"])
    nt.links.new(haut, mc.inputs["Color2"])

    # 4. projections de boue sur les 35 premiers centimetres
    bas = _rampe(nt, zn.outputs["Value"],
                 [(0.40 / max(hauteur, 0.1), 1.0), (1.00 / max(hauteur, 0.1), 0.0)])

    # composition, du fond vers la salissure.
    #
    #   PIEGE, corrige ici : la sortie Fac d'un bruit de Perlin ne parcourt PAS
    #   0..1. Elle se masse autour de 0,5, typiquement entre 0,39 et 0,61. Une
    #   rampe large — 0,18 vers 0,82 — ETALE ce domaine, donc COMPRESSE la
    #   sortie : le melange ne quittait plus la plage 0,33-0,67 et le mur
    #   rendait un aplat malgre trois reglages d'amplitude successifs. Il faut
    #   une rampe ETROITE autour de 0,5 pour retrouver tout le contraste.
    fm = _rampe(nt, marbre.outputs["Fac"], [(0.40, 0.0), (0.60, 1.0)])
    c = _mix(nt, fm, _teinte(base, 0.86), _teinte(base, 1.14))
    fg = _rampe(nt, grain.outputs["Fac"], [(0.42, 0.0), (0.58, 0.34)])
    c = _mix(nt, fg, c, _teinte(base, 1.16))
    c = _mix(nt, joints, c, _teinte(base, 0.58))
    c = _mix(nt, mc.outputs["Color"], c, _teinte(base, 0.88, vers=(102, 104, 98)))
    c = _mix(nt, bas, c, _teinte(base, 0.55, vers=(86, 78, 62)))
    nt.links.new(c, p.inputs["Base Color"])

    # rugosite : le grain la fait varier, le joint est plus mat que le nu
    rg = _rampe(nt, grain.outputs["Fac"], [(0.0, 0.74), (1.0, 0.90)])
    rg = _mix(nt, joints, rg, (242, 242, 242))
    nt.links.new(rg, p.inputs["Roughness"])
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.30

    # relief : joints en creux, grain en surface
    h = _n(nt, "ShaderNodeMath", operation="MULTIPLY_ADD")
    h.inputs[1].default_value = -1.0
    h.inputs[2].default_value = 1.0
    nt.links.new(joints, h.inputs[0])
    hg = _n(nt, "ShaderNodeMath", operation="MULTIPLY_ADD")
    hg.inputs[1].default_value = 0.13
    nt.links.new(grain.outputs["Fac"], hg.inputs[0])
    nt.links.new(h.outputs["Value"], hg.inputs[2])
    bump = _n(nt, "ShaderNodeBump", Strength=0.55, Distance=0.012)
    nt.links.new(hg.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def grave(nom="grave", taille=0.032):
    """Grave calcaire : cailloux individuels par Voronoi, a la bonne taille.

    ATTENTION a la source : le gris uni des PC5 (162,162,162) est une
    convention de dessin, pas une couleur photographique. La palette ci-dessous
    est celle d'un concasse calcaire courant ; elle sera a recaler le jour ou
    une photo de plateforme reelle sera disponible.

    `taille` est le diametre moyen d'un caillou, en metres : 32 mm correspond
    a un 20/40 de plateforme.
    """
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = _n(nt, "ShaderNodeTexCoord")

    gros = _n(nt, "ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature="F1",
              Scale=1.0 / taille, Randomness=1.0)
    nt.links.new(tc.outputs["Object"], gros.inputs["Vector"])
    fin = _n(nt, "ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature="F1",
             Scale=3.1 / taille, Randomness=1.0)
    nt.links.new(tc.outputs["Object"], fin.inputs["Vector"])

    # une couleur par caillou : la sortie Color du Voronoi est un tirage par
    # cellule, ramene ici a une luminance puis a une palette de calcaire.
    cg = _rampe(nt, gros.outputs["Color"], [(0.06, (88, 84, 76)), (0.34, (140, 134, 120)),
                                            (0.66, (176, 170, 153)), (0.95, (203, 198, 182))])
    cf = _rampe(nt, fin.outputs["Color"], [(0.10, (120, 116, 104)), (0.90, (188, 183, 168))])
    c = _mix(nt, 0.28, cg, cf)
    # poussiere de concassage dans les creux
    creux = _rampe(nt, gros.outputs["Distance"], [(0.0, 1.0), (0.55, 0.0)])
    c = _mix(nt, creux, c, (150, 145, 132))
    nt.links.new(c, p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.93
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.22

    h = _n(nt, "ShaderNodeMath", operation="MULTIPLY_ADD")
    h.inputs[1].default_value = 0.35
    nt.links.new(fin.outputs["Distance"], h.inputs[0])
    nt.links.new(gros.outputs["Distance"], h.inputs[2])
    bump = _n(nt, "ShaderNodeBump", Strength=0.85, Distance=taille * 0.55)
    nt.links.new(h.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def _math(nt, op, a, b=None, c=None):
    n = _n(nt, "ShaderNodeMath", operation=op)
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if hasattr(v, "node"):
            nt.links.new(v, n.inputs[i])
        else:
            n.inputs[i].default_value = v
    return n.outputs["Value"]


def _ligne(nt, coord, pas, demi):
    """Bourrelet doux centre sur une ligne tous les `pas` metres.

    `_raie` donne un creneau net, bon pour un joint de banche. Une soudure de
    bache est un recouvrement de quelques centimetres, donc un RELIEF adouci :
    il faut la distance a la ligne la plus proche, puis une decroissance.
    """
    w = _math(nt, "WRAP", coord, pas, 0.0)
    d = _math(nt, "MINIMUM", w, _math(nt, "SUBTRACT", pas, w))
    return _rampe(nt, _math(nt, "DIVIDE", d, demi), [(0.0, 1.0), (1.0, 0.0)])


def bache_pvc(nom="pvc", base=None, laize=1.50, usure=1.0):
    """Bache souple : soudures de les, fronçage en pied, tension du tissu.

    Releve sur des photos de citernes incendie 60 et 120 m3 en service, dont
    deux sur des centrales PV, et sur le dessin de fabrication d'un fournisseur.
    Ce qu'on y voit, et qu'on ne voit PAS :

      - les soudures courent DANS LA LONGUEUR : la toile arrive en les de
        1,50 m que l'on assemble bord a bord. Sur la surface, ce sont des
        lignes a hauteur constante le long des flancs, qui se rejoignent aux
        extremites. Elles se lisent comme un mince bourrelet, pas comme un
        trait de couleur.
      - la toile est TENDUE sur toute la partie haute : pas de plis. Les plis
        se concentrent en PIED, ou le tissu se fronce en se retournant sous
        la citerne.
      - AUCUNE sangle sur le corps. Les cinq photos n'en montrent pas une.
        Ce qui ceinture le pied est la bande anti-vegetation, une bache grise
        posee au sol, pas un arrimage.
      - le PVC est SATINE : le dessus attrape un large reflet du ciel, le
        flanc reste mat. C'est ce contraste qui donne le volume.

    D'ou un materiau ou presque tout passe par la NORMALE, et tres peu par la
    couleur : une toile se lit a l'ombrage de son relief, pas a des taches.

    Les UV sont en METRES : u le long du contour, v l'abscisse curviligne du
    meridien depuis le sol (voir `exporter_equipements.geometrie_citerne`).
    """
    base = base or RAL["6011"]
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]

    uv = _n(nt, "ShaderNodeUVMap")
    uv.uv_map = "metres"
    sep = _n(nt, "ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs["Vector"])
    u, v = sep.outputs["X"], sep.outputs["Y"]

    # 1. soudures des les, tous les 1,50 m d'abscisse curviligne
    soud = _ligne(nt, v, laize, 0.045)

    # 2. fronçage de pied : plis verticaux, donc variant vite selon u et
    #    lentement selon v. Ils s'eteignent au-dessus de 1,2 m de meridien.
    #    ECHELLE : un fronçage reel fait des plis de 40 a 80 cm, irreguliers.
    #    A 0,20 m ils rendaient un peigne regulier, ce qui se voit tout de
    #    suite comme du calcul. Un pli tous les 0,55 m environ.
    map_p = _n(nt, "ShaderNodeMapping")
    map_p.inputs["Scale"].default_value = (1.9, 0.20, 1.0)
    nt.links.new(uv.outputs["UV"], map_p.inputs["Vector"])
    plis = _n(nt, "ShaderNodeTexNoise", Scale=0.95, Detail=4.0, Roughness=0.60)
    nt.links.new(map_p.outputs["Vector"], plis.inputs["Vector"])
    #    le haut de la zone frongee ondule : une limite horizontale nette
    #    trahit le masque. On lui ajoute un bruit lent le long du contour.
    map_l = _n(nt, "ShaderNodeMapping")
    map_l.inputs["Scale"].default_value = (0.42, 0.02, 1.0)
    nt.links.new(uv.outputs["UV"], map_l.inputs["Vector"])
    limite = _n(nt, "ShaderNodeTexNoise", Scale=1.0, Detail=2.0, Roughness=0.5)
    nt.links.new(map_l.outputs["Vector"], limite.inputs["Vector"])
    vlim = _math(nt, "MULTIPLY_ADD", limite.outputs["Fac"], 0.85,
                 _math(nt, "SUBTRACT", v, 0.42))
    bas = _rampe(nt, _math(nt, "DIVIDE", vlim, 1.60), [(0.0, 1.0), (0.78, 0.0)])

    # 3. tension generale de la toile : ondulation large et faible
    map_o = _n(nt, "ShaderNodeMapping")
    map_o.inputs["Scale"].default_value = (0.30, 0.30, 1.0)
    nt.links.new(uv.outputs["UV"], map_o.inputs["Vector"])
    onde = _n(nt, "ShaderNodeTexNoise", Scale=1.0, Detail=3.0, Roughness=0.5)
    nt.links.new(map_o.outputs["Vector"], onde.inputs["Vector"])

    # couleur : tres peu de variation, une salissure basse et le liseré sombre
    # du pli de pied, rien d'autre
    sal = _rampe(nt, _math(nt, "DIVIDE", v, 0.60),
                 [(0.0, min(1.0, 0.55 * usure)), (0.75, 0.0)])
    c = _mix(nt, _rampe(nt, onde.outputs["Fac"], [(0.40, 0.0), (0.60, 0.22)]),
             _teinte(base, 0.96), _teinte(base, 1.07))
    c = _mix(nt, soud, c, _teinte(base, 0.90))
    c = _mix(nt, sal, c, _teinte(base, 0.72, vers=(96, 94, 82)))
    nt.links.new(c, p.inputs["Base Color"])

    # SATINE, pas verni. Une enduction PVC sur trame polyester garde un reflet
    # LARGE et doux ; a 0,42 de rugosite et 0,52 de specular, le Fresnel en
    # incidence rasante lavait la teinte et posait un trait brillant net en
    # bas de flanc, la ou la bache se retourne. Le reflet doit rester diffus.
    rg = _mix(nt, sal, (150, 150, 150), (212, 212, 212))    # 0,58 -> 0,83
    nt.links.new(rg, p.inputs["Roughness"])
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.33

    # relief : soudure en bourrelet, plis de pied, ondulation de fond
    h = _math(nt, "MULTIPLY_ADD", soud, 0.55,
              _math(nt, "MULTIPLY_ADD",
                    _math(nt, "MULTIPLY", plis.outputs["Fac"], bas), 1.7,
                    _math(nt, "MULTIPLY", onde.outputs["Fac"], 0.35)))
    bump = _n(nt, "ShaderNodeBump", Strength=0.85, Distance=0.070)
    nt.links.new(h, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def tole_peinte(nom="tole", base=None, usure=1.0):
    """Bardage acier laque : peu de matiere, le relief vient de l'ONDULATION.

    Contrairement au beton, une tole laquee est lisse et reguliere. Lui donner
    des marbrures la ferait lire comme du crepi. Ce qui la date, ce sont des
    coulures fines sous la lisse haute et un encrassement au pied, plus une
    legere irregularite de brillance : une tole n'est jamais parfaitement plane,
    et c'est le reflet ondulant qui le montre.
    """
    base = base or RAL["6003"]
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = _n(nt, "ShaderNodeTexCoord")
    sep = _n(nt, "ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])

    map_c = _n(nt, "ShaderNodeMapping")
    map_c.inputs["Scale"].default_value = (3.0, 3.0, 0.06)
    nt.links.new(tc.outputs["Object"], map_c.inputs["Vector"])
    coul = _n(nt, "ShaderNodeTexNoise", Scale=5.0, Detail=5.0, Roughness=0.65)
    nt.links.new(map_c.outputs["Vector"], coul.inputs["Vector"])
    tr = _rampe(nt, coul.outputs["Fac"], [(0.56, 0.0), (0.66, min(1.0, 0.30 * usure))])

    grand = _n(nt, "ShaderNodeTexNoise", Scale=0.7, Detail=3.0, Roughness=0.5)
    nt.links.new(tc.outputs["Object"], grand.inputs["Vector"])
    fg = _rampe(nt, grand.outputs["Fac"], [(0.42, 0.0), (0.58, 1.0)])

    c = _mix(nt, fg, _teinte(base, 0.94), _teinte(base, 1.06))
    c = _mix(nt, tr, c, _teinte(base, 0.80, vers=(104, 102, 94)))
    nt.links.new(c, p.inputs["Base Color"])
    rg = _mix(nt, fg, (118, 118, 118), (150, 150, 150))       # 0,46 -> 0,59
    nt.links.new(rg, p.inputs["Roughness"])
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.45
    p.inputs["Metallic"].default_value = 0.10
    return m


def feuillage(nom="haie", base=None, trouee=0.30, graine=0.0,
              gain=None, interieur=0.42):
    """Feuillage de haie : touffes, cime clairsemee, aucun brillant.

    La couleur de base vient de la VEGETATION DE LA PHOTO, pas d'un choix :
    c'est le seul moyen d'avoir la lumiere et la saison du cliche. Le materiau
    n'ajoute que ce que la photo ne peut pas donner — la variation par touffes
    et le fait que le ciel passe a travers la cime.

    Les UV sont en metres pour u (le long de la haie) et en fraction pour v
    (0 au sol, 1 a la cime), produits par `exporter_blender.geometrie_haie`.
    """
    base = base or (86, 94, 66)
    # Le coeur transparait entre les cartes : sans le MEME gain, il tire
    # toute la masse vers le bas et l'etalonnage des cartes n'aboutit pas.
    g = gain if gain is not None else GAIN_FEUILLAGE
    g = (g, g, g) if isinstance(g, (int, float)) else tuple(g)
    base = tuple(min(255.0, b * k) for b, k in zip(base, g))
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    if hasattr(m, "blend_method"):
        m.blend_method = "BLEND"
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = _n(nt, "ShaderNodeTexCoord")
    uv = _n(nt, "ShaderNodeUVMap")
    uv.uv_map = "metres"
    sep = _n(nt, "ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs["Vector"])
    v = sep.outputs["Y"]

    # touffes : bruit 3D a l'echelle du feuillage, environ 35 cm
    # pas d'entree W : elle n'existe que si le bruit est passe en 4D.
    touffe = _n(nt, "ShaderNodeTexNoise", Scale=2.9, Detail=6.0, Roughness=0.70)
    nt.links.new(tc.outputs["Object"], touffe.inputs["Vector"])
    fin = _n(nt, "ShaderNodeTexNoise", Scale=11.0, Detail=5.0, Roughness=0.60)
    nt.links.new(tc.outputs["Object"], fin.inputs["Vector"])

    # couleur : une haie n'est jamais d'un vert uni. Les creux virent au brun
    # sombre (bois et ombre interne), les cretes au vert clair.
    ft = _rampe(nt, touffe.outputs["Fac"], [(0.42, 0.0), (0.58, 1.0)])
    c = _mix(nt, ft, _teinte(base, 0.56), _teinte(base, 1.26))
    ff = _rampe(nt, fin.outputs["Fac"], [(0.44, 0.0), (0.56, 0.55)])
    c = _mix(nt, ff, c, _teinte(base, 0.78))

    # INTERIEUR DE HAIE. Ce volume n'est pas du feuillage vu de face : c'est ce
    # qu'on apercoit ENTRE les cartes. A egalite de valeur avec elles il BOUCHE
    # les trous au lieu de les creuser, et la masse rend un voile uniforme —
    # c'est exactement ce qu'on voyait sur la planche a 17 m des que les cartes
    # ont ete ramenees a une taille de feuille. Il doit donc etre nettement plus
    # sombre, et d'autant plus qu'on descend : la lumiere ne penetre pas au pied
    # d'une haie dense, alors qu'elle baigne la cime.
    ombre = _rampe(nt, v, [(0.0, interieur), (0.55, min(1.0, interieur * 1.45)),
                           (1.0, 1.0)])
    mo = _n(nt, "ShaderNodeMixRGB", blend_type="MULTIPLY")
    mo.inputs["Fac"].default_value = 1.0        # produit pur : un Fac < 1 fuit
    nt.links.new(c, mo.inputs["Color1"])
    nt.links.new(ombre, mo.inputs["Color2"])
    c = mo.outputs["Color"]
    nt.links.new(c, p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.96
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.06
    # un peu de lumiere passe au travers des feuilles
    if "Transmission Weight" in p.inputs:
        p.inputs["Transmission Weight"].default_value = 0.0
    if "Subsurface Weight" in p.inputs:
        p.inputs["Subsurface Weight"].default_value = 0.12
        if "Subsurface Radius" in p.inputs:
            p.inputs["Subsurface Radius"].default_value = (0.02, 0.05, 0.01)

    # ALPHA : le ciel passe a travers la CIME, pas a travers le pied. Sans cela
    # la haie garde une silhouette de gelee, ce qui la trahit immediatement.
    haut = _rampe(nt, v, [(0.62, 0.0), (1.0, 1.0)])
    # seuil FRANC : un degrade doux rendait une fumee au lieu de feuillage
    seuil = _rampe(nt, fin.outputs["Fac"],
                   [(0.50, 1.0), (0.50 + 0.10 * trouee, 0.0)])
    mx = _n(nt, "ShaderNodeMixRGB", blend_type="MULTIPLY")
    mx.inputs["Fac"].default_value = 1.0
    nt.links.new(seuil, mx.inputs["Color1"])
    nt.links.new(haut, mx.inputs["Color2"])
    a = _math(nt, "SUBTRACT", 1.0, mx.outputs["Color"])
    nt.links.new(a, p.inputs["Alpha"])
    return m


GAIN_FEUILLAGE = (2.93, 2.68, 2.85)
"""Correction PAR CANAL du feuillage, mesuree et non choisie.

Une masse de cartes translucides ne renvoie qu'environ UN TIERS de ce que
renverrait une surface plane de meme albedo : chaque carte est ombree par
celles de devant. Il faut donc remonter la base d'autant pour retrouver la
teinte visee.

MESURE, pas choix : montage PV9, ciel couvert, haie a 334 m. Rendu (29, 26,
14) pour une base a (48, 50, 31) deja multipliee par (1,78 / 1,42 / 1,33),
soit un facteur de restitution de 0,34 par canal ; deux tours de mesure
ferment l'ecart a (2,62 / 2,35 / 2,47), soit 3 pour cent pres.

REMESURE apres le travail sur la planche a 17 m (21/09/2026). L'alpha des
cartes est passe du disque flou a la touffe lobee, leur taille de 0,10-0,24 a
0,09-0,20 m, la densite de 34 a 52, et surtout le coeur a ete assombri a 0,42
au pied. La haie rendait alors 11 a 13 pour cent sous la cible : le gain passe
a (2,93 / 2,68 / 2,85). TOUTE retouche de ces reglages demande de refaire cette
mesure — c'est un couple, pas deux constantes independantes.

CE GAIN DEPEND DE LA SCENE, comme le calage des modules depend de
l'incidence. Il vaut pour un montage sous ciel couvert. Une planche sans
photo n'a aucune cible a atteindre : elle passe `gain=1` et choisit sa base
directement. Une scene franchement ensoleillee demanderait de le remesurer,
en isolant la haie au rendu et en comparant a `couleur_vegetation`."""


def _alpha_touffe(nt, tc, sep):
    """Silhouette CALCULEE d'une touffe lobee — la solution de repli.

    C'est le motif par defaut : ses folioles decoupees accrochent la lumiere la
    ou une feuille ovale de cinq pixels rend un aplat.

    Les UV vont de 0 a 1 sur la carte, comme pour l'atlas.
    """
    dx = _math(nt, "SUBTRACT", sep.outputs["X"], 0.5)
    dy = _math(nt, "SUBTRACT", sep.outputs["Y"], 0.5)
    r = _math(nt, "MULTIPLY",
              _math(nt, "SQRT", _math(nt, "ADD", _math(nt, "MULTIPLY", dx, dx),
                                      _math(nt, "MULTIPLY", dy, dy))), 2.0)
    th = _math(nt, "ARCTAN2", dy, dx)
    # Deux bruits LENTS (periode ~1 m) pilotent la forme : le nombre de
    # folioles doit etre constant SUR une carte et varier d'un buisson a
    # l'autre — une meme espece garde sa feuille.
    va = _n(nt, "ShaderNodeTexNoise", Scale=0.8, Detail=2.0)
    nt.links.new(tc.outputs["Object"], va.inputs["Vector"])
    vb = _n(nt, "ShaderNodeTexNoise", Scale=1.3, Detail=2.0)
    nt.links.new(tc.outputs["Object"], vb.inputs["Vector"])
    # ENTIER, obligatoirement : cos(n.theta) avec n fractionnaire ne se
    # referme pas en +/- pi et fend la carte d'une entaille radiale.
    nlob = _math(nt, "ADD", 4.0,
                 _math(nt, "FLOOR",
                       _math(nt, "MULTIPLY",
                             _rampe(nt, va.outputs["Fac"], [(0.40, 0.0), (0.60, 1.0)]),
                             4.99)))
    phase = _math(nt, "MULTIPLY", vb.outputs["Fac"], 25.0)
    lobe = _math(nt, "MULTIPLY_ADD",
                 _math(nt, "COSINE",
                       _math(nt, "ADD", _math(nt, "MULTIPLY", th, nlob), phase)),
                 0.42, 0.58)
    lobe = _math(nt, "POWER", lobe, 0.55)       # folioles PLEINES, pas des pointes
    gr = _n(nt, "ShaderNodeTexNoise", Scale=24.0, Detail=5.0, Roughness=0.65)
    nt.links.new(tc.outputs["Object"], gr.inputs["Vector"])
    ir = _rampe(nt, gr.outputs["Fac"], [(0.40, 0.0), (0.60, 1.0)])
    limite = _math(nt, "MULTIPLY", lobe,
                   _math(nt, "MULTIPLY_ADD", ir, 0.45, 0.72))
    # (r - limite) vaut -1 a +1 ; une ColorRamp n'accepte pas de position
    # negative, on le recentre donc sur 0,5 avant de trancher SERRE.
    bord = _math(nt, "MULTIPLY_ADD", _math(nt, "SUBTRACT", r, limite), 0.5, 0.5)
    return _rampe(nt, bord, [(0.475, 1.0), (0.515, 0.0)])


def feuillage_carte(nom="feuillage", base=None, translucide=0.30,
                    gain=GAIN_FEUILLAGE, atlas=False):
    """Carte de feuillage : feuille PHOTOGRAPHIEE et TRANSLUCIDITE.

    Une feuille n'est pas opaque : elle transmet. C'est ce qui fait qu'un
    feuillage a contre-jour s'allume au lieu de s'eteindre, et c'est ce qui
    manquait le plus au volume texture d'origine, qui rendait trois fois trop
    sombre. Un Translucent melange au Principled suffit a le rendre.

    La SILHOUETTE est CALCULEE par `_alpha_touffe` — une touffe a folioles,
    qui tient mieux la distance que l'ovale photographie, cf. ATLAS_COULEUR.
    Avec `atlas=True` elle vient de la planche photographique, dont la couleur
    est alors normalisee sur `base` : l'image apporte la matiere, la photo
    garde la teinte.

    Les UV vont de 0 a 1 SUR CHAQUE CARTE dans les deux cas — c'est la
    convention de `exporter_blender._carte`, et elle vaut aussi bien pour lire
    la planche entiere que pour tracer une touffe.
    """
    base = base or (96, 85, 52)
    g = (gain, gain, gain) if isinstance(gain, (int, float)) else tuple(gain)
    base = tuple(min(255.0, b * k) for b, k in zip(base, g))
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    if hasattr(m, "blend_method"):
        m.blend_method = "BLEND"
    if hasattr(m, "use_backface_culling"):
        m.use_backface_culling = False
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    sortie = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    tc = _n(nt, "ShaderNodeTexCoord")
    uv = _n(nt, "ShaderNodeUVMap")
    uv.uv_map = "metres"
    sep = _n(nt, "ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs["Vector"])

    if atlas and ATLAS_COULEUR.exists() and ATLAS_OPACITE.exists():
        img = _n(nt, "ShaderNodeTexImage")
        img.image = bpy.data.images.load(str(ATLAS_COULEUR), check_existing=True)
        img.image.colorspace_settings.name = "sRGB"
        img.extension = "CLIP"
        nt.links.new(uv.outputs["UV"], img.inputs["Vector"])
        opa = _n(nt, "ShaderNodeTexImage")
        opa.image = bpy.data.images.load(str(ATLAS_OPACITE), check_existing=True)
        opa.image.colorspace_settings.name = "Non-Color"
        opa.extension = "CLIP"
        nt.links.new(uv.outputs["UV"], opa.inputs["Vector"])
        # SEUIL FRANC sur l'alpha photographie : son lisere de bord, anodin sur
        # une feuille, se cumule sur cent mille cartes et voile toute la masse.
        a = _rampe(nt, opa.outputs["Color"], [(0.38, 0.0), (0.52, 1.0)])
        # FONDU DE LISIERE. La touffe couvre 64 % de la planche, donc le bord du
        # quad tranche des feuilles en plein milieu : on lisait des decoupes
        # carrees dans la masse. Six pour cent de fondu sur le pourtour suffisent
        # a les effacer, sans entamer la silhouette des feuilles interieures.
        bord = _math(nt, "MINIMUM",
                     _math(nt, "MINIMUM", sep.outputs["X"],
                           _math(nt, "SUBTRACT", 1.0, sep.outputs["X"])),
                     _math(nt, "MINIMUM", sep.outputs["Y"],
                           _math(nt, "SUBTRACT", 1.0, sep.outputs["Y"])))
        fondu = _rampe(nt, bord, [(0.0, 0.0), (0.06, 1.0)])
        mb = _n(nt, "ShaderNodeMixRGB", blend_type="MULTIPLY")
        mb.inputs["Fac"].default_value = 1.0
        nt.links.new(a, mb.inputs["Color1"])
        nt.links.new(fondu, mb.inputs["Color2"])
        a = mb.outputs["Color"]

        # Normalisation de la teinte, canal par canal et EN LINEAIRE — c'est
        # l'espace dans lequel Cycles multiplie, l'image sortant deja
        # delinearisee par son profil sRGB. Le rapport se prend sur la moyenne
        # PONDEREE PAR L'ALPHA de l'atlas : le fond transparent ne compte pas.
        kl = tuple(_srgb_lin(b) / max(_srgb_lin(mm), 1e-6)
                   for b, mm in zip(base, ATLAS_MOYENNE))
        sc = _n(nt, "ShaderNodeSeparateColor")
        nt.links.new(img.outputs["Color"], sc.inputs["Color"])
        cc = _n(nt, "ShaderNodeCombineColor")
        for canal, k in zip(("Red", "Green", "Blue"), kl):
            nt.links.new(_math(nt, "MULTIPLY", sc.outputs[canal], k),
                         cc.inputs[canal])
        # Variation a l'echelle de la MASSE : une haie n'est jamais d'une seule
        # valeur. L'atlas donne la variation DANS la feuille, pas d'une touffe a
        # l'autre — le motif calcule, lui, porte deja la sienne.
        masse = _n(nt, "ShaderNodeTexNoise", Scale=1.6, Detail=5.0, Roughness=0.65)
        nt.links.new(tc.outputs["Object"], masse.inputs["Vector"])
        fm = _math(nt, "MULTIPLY_ADD",
                   _rampe(nt, masse.outputs["Fac"], [(0.40, 0.0), (0.60, 1.0)]),
                   0.62, 0.68)                  # 0,68 a 1,30
        mv = _n(nt, "ShaderNodeMixRGB", blend_type="MULTIPLY")
        mv.inputs["Fac"].default_value = 1.0    # produit pur : un Fac < 1 fuit
        nt.links.new(cc.outputs["Color"], mv.inputs["Color1"])
        nt.links.new(fm, mv.inputs["Color2"])
        c = mv.outputs["Color"]
    else:
        a = _alpha_touffe(nt, tc, sep)
        # Les deux extremes sont PROPORTIONNELS a la base, pas tires vers une
        # couleur fixe : sinon la reponse au gain n'est pas lineaire et
        # l'etalonnage ne converge pas — mesure a l'appui, un gain de 1,78
        # ne remontait la mediane que de 54 a 64.
        gros_ = _n(nt, "ShaderNodeTexNoise", Scale=1.6, Detail=5.0, Roughness=0.65)
        nt.links.new(tc.outputs["Object"], gros_.inputs["Vector"])
        ft = _rampe(nt, gros_.outputs["Fac"], [(0.38, 0.0), (0.62, 1.0)])
        c = _mix(nt, ft, _teinte(base, 0.58), _teinte(base, 1.32))
    nt.links.new(c, p.inputs["Base Color"])

    nt.links.new(a, p.inputs["Alpha"])
    p.inputs["Roughness"].default_value = 0.88
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.18

    # la part translucide, melangee au diffus
    tr = _n(nt, "ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = _rgba(_teinte(base, 1.15))
    mel = _n(nt, "ShaderNodeMixShader")
    mel.inputs["Fac"].default_value = float(translucide)
    nt.links.new(p.outputs["BSDF"], mel.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mel.inputs[2])
    # l'alpha doit rester pilote apres le melange
    trans = _n(nt, "ShaderNodeBsdfTransparent")
    mel2 = _n(nt, "ShaderNodeMixShader")
    nt.links.new(a, mel2.inputs["Fac"])
    nt.links.new(trans.outputs["BSDF"], mel2.inputs[1])
    nt.links.new(mel.outputs["Shader"], mel2.inputs[2])
    nt.links.new(mel2.outputs["Shader"], sortie.inputs["Surface"])
    return m
