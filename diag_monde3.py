import json, sys, math
from pathlib import Path
import bpy
argv = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, argv[2])
import blender_rendu as BR
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
data = json.load(open(argv[0], encoding="utf-8"))
scene = bpy.context.scene
scene.render.engine = "CYCLES"; scene.cycles.samples = 8
scene.view_settings.view_transform = "Standard"
scene.render.film_transparent = False
scene.render.resolution_x = 64; scene.render.resolution_y = 64
scene.render.image_settings.file_format = "PNG"
BR.eclairer(scene, data)
cd = bpy.data.cameras.new("c"); cd.lens = 10.0
cam = bpy.data.objects.new("c", cd); scene.collection.objects.link(cam); scene.camera = cam
for nom, rot in (("nadir", (0,0,0)), ("zenith", (math.pi,0,0)), ("horizon", (math.pi/2,0,0))):
    cam.rotation_euler = rot
    scene.render.filepath = argv[1].replace(".png", f"_{nom}.png")
    bpy.ops.render.render(write_still=True)
print("DIAG3 OK")
