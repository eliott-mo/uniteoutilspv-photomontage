import sys, math
from pathlib import Path
import bpy
argv = sys.argv[sys.argv.index("--") + 1:]
sortie = argv[0]
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)   # le cube par defaut enfermait la camera
scene = bpy.context.scene
scene.render.engine = "CYCLES"; scene.cycles.samples = 8
scene.view_settings.view_transform = "Standard"
scene.render.film_transparent = False
scene.render.resolution_x = 64; scene.render.resolution_y = 64
scene.render.image_settings.file_format = "PNG"
cam_data = bpy.data.cameras.new("c"); cam_data.lens = 10.0
cam = bpy.data.objects.new("c", cam_data)
scene.collection.objects.link(cam); scene.camera = cam

# 1. monde constant rouge
m = bpy.data.worlds.new("test"); m.use_nodes = True
m.node_tree.nodes["Background"].inputs["Color"].default_value = (1.0, 0.0, 0.0, 1.0)
m.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
scene.world = m
scene.render.filepath = sortie.replace(".png", "_rouge.png")
bpy.ops.render.render(write_still=True)

# 2. degrade : que sort Texture Coordinate > Generated dans un monde ?
m2 = bpy.data.worlds.new("degrade"); m2.use_nodes = True
nt = m2.node_tree
for n in list(nt.nodes):
    if n.type != "OUTPUT_WORLD":
        nt.nodes.remove(n)
out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
coord = nt.nodes.new("ShaderNodeTexCoord")
fond = nt.nodes.new("ShaderNodeBackground")
nt.links.new(coord.outputs["Generated"], fond.inputs["Color"])
nt.links.new(fond.outputs["Background"], out.inputs["Surface"])
fond.inputs["Strength"].default_value = 1.0
scene.world = m2
for nom, rot in (("nadir", (0, 0, 0)), ("zenith", (math.pi, 0, 0)), ("horizon", (math.pi/2, 0, 0))):
    cam.rotation_euler = rot
    scene.render.filepath = sortie.replace(".png", f"_{nom}.png")
    bpy.ops.render.render(write_still=True)
print("DIAG2 OK")
