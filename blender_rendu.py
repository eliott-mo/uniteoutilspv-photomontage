#!/usr/bin/env python3
"""Script execute DANS Blender : monte la scene exportee et rend une image.

Ne connait rien du photovoltaique : il recoit des maillages, des noms de
materiaux, une pose de camera et un eclairage, et rend un PNG a fond
transparent, pret a etre compose sur la photo.

Deux points qui font tout l'interet par rapport au rendu vectoriel :
  - les materiaux sont physiques (verre, acier, bois), donc la reflexion et la
    variation interne sortent du calcul au lieu d'etre imitees ;
  - le sol est un CAPTEUR D'OMBRE : invisible, mais les ombres portees qui
    tombent dessus deviennent les seuls pixels opaques de cette zone. On pose
    donc des ombres sur la vraie photo sans repeindre le terrain.

Usage (via le shell, jamais depuis un sous-processus Python) :
    blender -b -P blender_rendu.py -- scene.json sortie.png [echantillons]
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

# Blender ne met pas le dossier du script sur sys.path : sans cette ligne,
# l'import du module voisin echoue.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_camera import poser_camera
import materiaux_proc as MP


def _srgb_lin(c):
    """sRGB 0-255 vers lineaire. Cycles travaille en lineaire : donner du sRGB
    tel quel eclaircit et desature tout, et un rondin d'acacia vire au beton."""
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


#: Opacite du sol du site. La photo transparait du complement, ce qui ancre la
#: couverture dans le grain et la lumiere du terrain reel.
OPACITE_HERBE = 0.72


def _mat(nom, base, rugosite, metal=0.0, transmission=0.0, specular=0.5):
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*[_srgb_lin(c) for c in base], 1.0)
    p.inputs["Roughness"].default_value = rugosite
    p.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = specular
    if transmission and "Transmission Weight" in p.inputs:
        p.inputs["Transmission Weight"].default_value = transmission
    return m


def _mat_herbe(base, rugosite=0.94, opacite=OPACITE_HERBE):
    """Herbe rase du site, avec un grain — un aplat se lit comme une peinture.

    Le materiau plat convenait a Gannay, ou le sol du site ne servait qu'a
    boucher les jeux entre tables, a plus de cent metres. A quatre metres d'un
    point de vue, il couvre une grande surface et se lit alors comme une piste
    ou une pelouse peinte : c'est ce qu'a vu le chef de projet sur PM4.

    Deux octaves, aux deux echelles que l'oeil cherche sur une prairie fauchee :
    la touffe, autour de dix centimetres, et la trace de passage, autour du
    metre. Les coordonnees sont en metres — le sol est exporte dans le repere
    local — donc les echelles se lisent directement.
    """
    m = bpy.data.materials.new("herbe")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = rugosite
    p.inputs["Metallic"].default_value = 0.0
    # PARTIELLEMENT TRANSPARENT, ET C'EST LE POINT. Un sol opaque se lit comme
    # une piste : une surface lisse, d'une seule teinte, posee au milieu d'un
    # couvert qui, lui, a du grain, des accidents et sa propre lumiere. La
    # meme raison a conduit `montage._teinte_sol` a garder un quart de la
    # photo sous la couverture repeinte du cote Sarnois — « pour qu'elle reste
    # ancree dans la lumiere et les accidents du terrain reel, au lieu de
    # flotter comme un aplat peint ». Le rendu obtient la meme chose par son
    # alpha : la photo transparait d'autant.
    p.inputs["Alpha"].default_value = opacite

    coord = nt.nodes.new("ShaderNodeTexCoord")
    fin = nt.nodes.new("ShaderNodeTexNoise")
    fin.inputs["Scale"].default_value = 11.0        # ~ 9 cm
    fin.inputs["Detail"].default_value = 3.0
    large = nt.nodes.new("ShaderNodeTexNoise")
    large.inputs["Scale"].default_value = 0.8       # ~ 1,2 m
    large.inputs["Detail"].default_value = 2.0
    nt.links.new(coord.outputs["Object"], fin.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], large.inputs["Vector"])

    melange = nt.nodes.new("ShaderNodeMixRGB")
    melange.blend_type = "MIX"
    melange.inputs["Fac"].default_value = 0.45
    nt.links.new(fin.outputs["Fac"], melange.inputs["Color1"])
    nt.links.new(large.outputs["Fac"], melange.inputs["Color2"])

    # RAMPE ETROITE AUTOUR DE 0,5 : le Fac d'un bruit de Perlin n'occupe pas
    # 0-1, il se serre autour du milieu. Une rampe large ecraserait le contraste
    # au lieu de l'etaler — piege deja rencontre sur le feuillage.
    rampe = nt.nodes.new("ShaderNodeValToRGB")
    # RAMPE PLUS ETROITE ENCORE : le Fac d'un Perlin se serre autour de 0,5,
    # et la premiere version a 0,40-0,60 ne rendait que 4 niveaux d'ecart-type
    # sur 255 — un aplat. A 0,44-0,56 elle en rend 11 a 16, ce qui se lit.
    rampe.color_ramp.elements[0].position = 0.44
    rampe.color_ramp.elements[1].position = 0.56
    clair = [min(1.0, _srgb_lin(c) * 1.28) for c in base]
    sombre = [_srgb_lin(c) * 0.74 for c in base]
    rampe.color_ramp.elements[0].color = (*sombre, 1.0)
    rampe.color_ramp.elements[1].color = (*clair, 1.0)
    nt.links.new(melange.outputs["Color"], rampe.inputs["Fac"])
    nt.links.new(rampe.outputs["Color"], p.inputs["Base Color"])
    return m


def _grillage(maille=0.20, fil=0.006):
    """Grillage rigide : opaque sur les fils, transparent entre eux.

    Un quad plein a 3,8 m de l'objectif fait un mur de beton en travers du
    cadre. La maille se dessine par l'alpha, a partir d'UV exprimes en metres :
    modulo la maille, on est sur un fil si on est a moins d'un diametre du bord.
    """
    m = bpy.data.materials.new("grillage")
    m.use_nodes = True
    m.blend_method = "BLEND" if hasattr(m, "blend_method") else m.blend_method
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*[_srgb_lin(c) for c in (146, 148, 142)], 1.0)
    p.inputs["Roughness"].default_value = 0.55
    p.inputs["Metallic"].default_value = 0.65
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs["Vector"])
    sorties = []
    for axe in ("X", "Y"):
        mod = nt.nodes.new("ShaderNodeMath"); mod.operation = "WRAP"
        mod.inputs[1].default_value = maille
        mod.inputs[2].default_value = 0.0
        nt.links.new(sep.outputs[axe], mod.inputs[0])
        seuil = nt.nodes.new("ShaderNodeMath"); seuil.operation = "LESS_THAN"
        seuil.inputs[1].default_value = fil
        nt.links.new(mod.outputs["Value"], seuil.inputs[0])
        sorties.append(seuil.outputs["Value"])
    mx = nt.nodes.new("ShaderNodeMath"); mx.operation = "MAXIMUM"
    nt.links.new(sorties[0], mx.inputs[0])
    nt.links.new(sorties[1], mx.inputs[1])
    nt.links.new(mx.outputs["Value"], p.inputs["Alpha"])
    return m


def materiaux(reglages=None):
    """Materiaux, reglables depuis la scene pour pouvoir les CALER sur la charte.

    Un verre parfaitement lisse et plan devient un miroir en incidence rasante :
    Cycles le calcule justement, et les modules sortent blancs. Le verre solaire
    reel porte un traitement antireflet, il est sale, et une nappe reelle n'est
    jamais parfaitement coplanaire. D'ou une rugosite plus forte que la physique
    du verre nu, calee sur les references.
    """
    # CALAGE, pas physique. Mesure modules isoles : rapport au ciel 0,265 pour
    # 0,266 vise, teinte 1,028/1,127/0,845 pour 1,01/1,09/0,87.
    #
    # A LIRE AVANT DE REUTILISER : une base grise chaude a 84/74/44 avec une
    # rugosite de 0,80 ne decrit PAS un module photovoltaique, qui est bleu
    # sombre et lisse. Elle compense la reflexion du ciel dans la geometrie de
    # CETTE vue, prise a 78 degres d'incidence. Un verre nu y donnerait 0,64
    # fois la luminance du ciel, soit deux fois et demie la reference. Le
    # calage est donc valable pour cette geometrie ; une vue plus de face
    # demanderait de le refaire. Le bon modele serait une reflectance fonction
    # de l'angle d'incidence, calee sur des references dont on connaitrait la
    # geometrie de prise de vue — ce que le references.csv ne donne pas.
    r = dict(module_rugosite=0.80, module_specular=0.06,
             module_base=(84, 74, 44), acier_rugosite=0.58)
    r.update(reglages or {})
    return {
        # verre de module : tres lisse, donc il reflechit le ciel pour de vrai
        "module": _mat("module", tuple(r["module_base"]), r["module_rugosite"],
                       0.0, 0.0, r["module_specular"]),
        "acier": _mat("acier", (104, 106, 104), r["acier_rugosite"], 0.70),
        # acacia ecorce : miel grisant, pas brun sombre
        # Sous un ciel bleute diffus, un bois chaud se desature fortement au rendu :
        # il faut une base plus saturee que la couleur voulue pour la retrouver.
        "bois": _mat("bois", (226, 176, 104), 0.80, 0.0),
        "grillage": _grillage(r.get("maille", 0.20), r.get("fil", 0.006)),
        "cadre": _mat("cadre", (176, 178, 180), 0.34, 0.90),
        # Le poste n'est PAS du beton clair : les PC5 des 19 dossiers HOCH le
        # donnent peint, RAL 6003 vert olive dans plus d'un cas sur deux. Le
        # materiau est procedural (joints de banche, coulures, boue) parce que
        # l'aplat precedent se lisait comme un aplat.
        "beton": MP.beton_peint("beton", MP.RAL[r.get("ral_poste", "6003")],
                                hauteur=r.get("hauteur_poste", 3.0),
                                usure=r.get("usure", 1.0)),
        "couvertine": _mat("couvertine", MP.COUVERTINE, 0.72, 0.0),
        # fond des creux : ce qu'on voit entre deux lamelles
        "creux": _mat("creux", (26, 27, 24), 0.96, 0.0, 0.0, 0.02),
        # portes et lamelles : peintes du meme RAL que le corps, un ton plus
        # sombre. Les PC5 ne montrent nulle part d'acier nu sur un poste ; une
        # menuiserie metallique rendue en metal sort noire sous un ciel diffus.
        "menuiserie": _mat("menuiserie", MP._teinte(MP.RAL["6003"], 0.78), 0.48,
                           0.10, 0.0, 0.40),
        "grave": MP.grave("grave", r.get("grave_taille", 0.032)),
        # bache souple : soudures de les, fronçage de pied, satine du PVC,
        # releves sur des photos de citernes en service (cf. materiaux_proc).
        "pvc": MP.bache_pvc("pvc", MP.RAL["6011"], r.get("laize", 1.50),
                            r.get("usure", 1.0)),
        # raccord pompier : RAL 3000 rouge feu, laque. Seul element
        # franchement colore de l'ouvrage, et le plus reconnaissable.
        "pompier": _mat("pompier", (168, 38, 30), 0.38, 0.0, 0.0, 0.55),
        # ferrures de citerne : acier galvanise, donc CLAIR. Avec le 0,70 de
        # metallique du materiau "acier", le col de cygne et la trappe
        # rendaient presque noirs : un metal eclaire par le seul ciel, vu en
        # incidence rasante, ne renvoie rien.
        "ferrure": _mat("ferrure", (172, 176, 178), 0.44, 0.22, 0.0, 0.50),
        # plaques signaletiques : PVC blanc imprime, mat
        "plaque": _mat("plaque", (240, 239, 234), 0.62, 0.0, 0.0, 0.40),
        # bardage de conteneur : l'ondulation est de la GEOMETRIE, le
        # materiau ne porte que la patine.
        "tole": MP.tole_peinte("tole", MP.RAL[r.get("ral_conteneur", "6003")],
                               r.get("usure", 1.0)),
        "coin": _mat("coin", (58, 60, 58), 0.52, 0.45, 0.0, 0.45),
        # haie : teinte prise sur la vegetation de la photo
        # coeur de la haie : il ne sert plus qu'a boucher la vue au travers
        # MEME gain que les cartes : le coeur transparait entre elles, et
        # au gain par defaut il rendait un mur ocre sous un semis vert.
        "haie": MP.feuillage("haie", tuple(r.get("haie_rgb", (96, 85, 52))),
                             r.get("trouee_haie", 0.30), 0.0,
                             r.get("gain_haie", MP.GAIN_FEUILLAGE)),
        # cartes de feuillage : c'est elles qui font la silhouette
        "feuillage": MP.feuillage_carte(
            "feuillage", tuple(r.get("haie_rgb", (96, 85, 52))),
            r.get("translucide", 0.30),
            r.get("gain_haie", MP.GAIN_FEUILLAGE),
            bool(r.get("atlas_feuilles", False))),
        # ecorce de haie champetre : gris-brun sombre et MAT. Le materiau
        # "bois" existant est un acacia miel, juste pour un poteau de
        # cloture, faux pour un tronc de charme ou de noisetier.
        "branche": _mat("branche", (126, 114, 98), 0.90, 0.0, 0.0, 0.20),
        "herbe": _mat_herbe(tuple(r.get("herbe_rgb", (104, 120, 74)))),
        "sol_ombre": _mat("sol_ombre", (120, 130, 95), 0.95, 0.0),
    }


def monter(scene, data, mats):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    objets = []
    # `seulement` sert au calage : on isole un materiau pour le mesurer sans que
    # la cloture ou la structure viennent polluer le masque.
    seulement = data.get("seulement")
    for bloc in data["objets"]:
        if not bloc["f"]:
            continue
        if seulement and bloc["materiau"] not in seulement and bloc["materiau"] != "sol_ombre":
            continue
        me = bpy.data.meshes.new(bloc["materiau"])
        me.from_pydata([Vector(v) for v in bloc["v"]], [], bloc["f"])
        me.validate()
        me.update()
        if bloc.get("uv"):
            couche = me.uv_layers.new(name="metres")
            for i, boucle in enumerate(me.loops):
                couche.data[i].uv = bloc["uv"][boucle.vertex_index]
        ob = bpy.data.objects.new(bloc["materiau"], me)
        ob.data.materials.append(mats[bloc["materiau"]])
        scene.collection.objects.link(ob)
        if bloc["materiau"] == "sol_ombre":
            ob.is_shadow_catcher = True          # invisible, mais recoit les ombres
        objets.append(ob)
    return objets


def eclairer(scene, data):
    """Environnement a DEUX HEMISPHERES, plus un soleil si la date est connue.

    Un ciel uniforme est le piege du premier rendu : il eclaire aussi par en
    dessous, donc un module, qui est presque un miroir, renvoie du clair quelle
    que soit son orientation et sort blanc. Dans la realite la moitie basse du
    monde est le sol, sombre. D'ou le degrade : couleur du ciel au-dessus de
    l'horizon, couleur du sol en dessous, transition courte.
    """
    monde = bpy.data.worlds.new("environnement")
    monde.use_nodes = True
    nt = monde.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_WORLD":
            nt.nodes.remove(n)
    sortie = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    # `Geometry > Incoming` donne la direction du rayon en coordonnees monde,
    # dans -1..1. `Texture Coordinate > Generated` ne la donne PAS : verifie au
    # rendu, il sort une valeur qui ne s'annule pas a l'horizon.
    coord = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    rampe = nt.nodes.new("ShaderNodeValToRGB")
    fond = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(coord.outputs["Incoming"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rampe.inputs["Fac"])
    nt.links.new(rampe.outputs["Color"], fond.inputs["Color"])
    nt.links.new(fond.outputs["Background"], sortie.inputs["Surface"])
    # Les couleurs echantillonnees sur la photo sont en sRGB ; Cycles travaille en
    # LINEAIRE. Les passer telles quelles rend le monde environ deux fois trop
    # lumineux, et les modules, presque des miroirs, sortent blancs.
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    ciel = [lin(v) for v in data.get("ciel", [135, 156, 173])]
    sol = [lin(v) for v in data.get("sol_rgb", [86, 92, 62])]
    r = rampe.color_ramp
    r.interpolation = "LINEAR"
    # ATTENTION au sens : `Incoming` pointe de la surface VERS l'observateur,
    # donc son Z est POSITIF quand le rayon descend, c'est-a-dire quand on
    # regarde le sol. Verifie au rendu : sans cette inversion les deux
    # hemispheres sont echanges et les modules renvoient du ciel par en dessous.
    # Le Fac d'une rampe etant borne a [0, 1], tout le haut du monde tombe sur
    # l'element 0 ; la transition se place juste au-dessus de 0.
    r.elements[0].position = 0.0
    r.elements[0].color = (*ciel, 1.0)
    r.elements[1].position = 0.05
    r.elements[1].color = (*sol, 1.0)
    fond.inputs["Strength"].default_value = float(data.get("force_ciel", 1.0))
    scene.world = monde

    s = data.get("soleil")
    if not s:
        return None                        # lumiere diffuse : pas de soleil
    d = bpy.data.lights.new("soleil", type="SUN")
    d.angle = math.radians(0.53)
    d.energy = float(s.get("puissance", 3.0))
    ob = bpy.data.objects.new("soleil", d)
    scene.collection.objects.link(ob)
    az = math.radians(s["azimut"]); el = math.radians(s["elevation"])
    vers = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = (-vers).to_track_quat("-Z", "Y")
    return ob


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    data = json.load(open(argv[0], encoding="utf-8"))
    sortie = argv[1]
    ech = int(argv[2]) if len(argv) > 2 else 64
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    # AgX, le defaut de Blender 4.x, est une transformation de vue cinema : elle
    # delave les sombres et desature. Sur un photomontage elle transforme un
    # module bleu nuit en aplat beige. Pour composer sur une photo il faut que
    # les valeurs rendues arrivent telles quelles en sRGB.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.cycles.samples = ech
    scene.cycles.use_denoising = True
    scene.render.film_transparent = True          # fond transparent pour la composition
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = sortie
    mats = materiaux(data.get("materiaux"))
    monter(scene, data, mats)
    eclairer(scene, data)
    poser_camera(scene, data["camera"])
    bpy.ops.render.render(write_still=True)
    print("RENDU ECRIT", sortie)


if __name__ == "__main__":
    main()
