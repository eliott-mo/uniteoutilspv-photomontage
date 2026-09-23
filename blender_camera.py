#!/usr/bin/env python3
"""Script execute DANS Blender : pose la camera et projette des points de controle.

Sert au test de parite. Le repere camera du projet est GAUCHER (det R = -1, voir
camera.py et test_geometrie.py) : X a droite, Y en haut, Z VERS L'AVANT. Blender
est droitier et sa camera regarde vers son -Z. Une erreur de signe ici retourne
le projet sans rien signaler, exactement comme le tangage inverse du 17/09.

La conversion tient en une ligne : les colonnes de la matrice monde de la camera
Blender sont (droite, haut, -avant), ou droite/haut/avant sont les axes du repere
camera du projet exprimes dans le monde, c'est-a-dire les lignes de R.

Usage (jamais en direct) :
    blender -b -P blender_camera.py -- parametres.json sortie.json
"""
import json
import sys

import bpy
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view


def poser_camera(scene, p):
    """Camera Blender equivalente a camera.Camera(W, H, azimut, tangage, roulis, f_px)."""
    W, H = int(p["largeur"]), int(p["hauteur"])
    scene.render.resolution_x = W
    scene.render.resolution_y = H
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0

    data = bpy.data.cameras.new("cam")
    data.type = "PERSP"
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0
    data.lens = p["f_px"] * 36.0 / W          # f_px = W / sensor * lens
    data.shift_x = 0.0
    data.shift_y = 0.0
    cam = bpy.data.objects.new("cam", data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    # R : monde (E, N, Up) -> camera (droite, haut, avant), fournie par camera.Camera.R
    R = p["R"]
    droite = Vector(R[0])
    haut = Vector(R[1])
    avant = Vector(R[2])
    M = Matrix(((droite.x, haut.x, -avant.x, p["position"][0]),
                (droite.y, haut.y, -avant.y, p["position"][1]),
                (droite.z, haut.z, -avant.z, p["position"][2]),
                (0.0, 0.0, 0.0, 1.0)))
    cam.matrix_world = M
    return cam, W, H


def traiter(scene, p):
    for o in list(scene.collection.objects):
        scene.collection.objects.unlink(o)
    cam, W, H = poser_camera(scene, p)
    bpy.context.view_layer.update()
    uv = []
    for pt in p["points"]:
        co = world_to_camera_view(scene, cam, Vector(pt))
        uv.append([co.x * W, (1.0 - co.y) * H, co.z])    # z = profondeur camera
    return {"uv": uv, "lens_mm": cam.data.lens,
            "matrice": [list(r) for r in cam.matrix_world]}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    cas = json.load(open(argv[0], encoding="utf-8"))
    scene = bpy.context.scene
    if isinstance(cas, dict):                # compatibilite : un seul cas
        cas = [cas]
    json.dump([traiter(scene, c) for c in cas],
              open(argv[1], "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
