import json, sys, math
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
argv = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, argv[2])
import blender_rendu as BR
data = json.load(open(argv[0], encoding="utf-8"))
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.view_settings.view_transform = "Standard"
scene.render.film_transparent = False          # on VEUT voir le monde
scene.render.resolution_x = 64
scene.render.resolution_y = 256
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = argv[1]
BR.eclairer(scene, data)
# camera verticale : du nadir au zenith
cam_data = bpy.data.cameras.new("c"); cam_data.lens = 8.0
cam = bpy.data.objects.new("c", cam_data)
scene.collection.objects.link(cam); scene.camera = cam
cam.rotation_euler = (0.0, 0.0, 0.0)           # regarde vers -Z, donc le nadir
bpy.ops.render.render(write_still=True)
print("DIAG NADIR ECRIT")
cam.rotation_euler = (math.radians(180.0), 0.0, 0.0)   # zenith
scene.render.filepath = argv[1].replace(".png", "_zenith.png")
bpy.ops.render.render(write_still=True)
print("DIAG ZENITH ECRIT")
