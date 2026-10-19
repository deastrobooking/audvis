import bpy

class AudvisSnapshotValue(bpy.types.PropertyGroup):
    full_path: bpy.props.StringProperty(name="Data Path")
    value: bpy.props.FloatProperty(name="Value")

class AudvisSnapshot(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="Look")
    values: bpy.props.CollectionProperty(type=AudvisSnapshotValue)

classes = [AudvisSnapshotValue, AudvisSnapshot]
