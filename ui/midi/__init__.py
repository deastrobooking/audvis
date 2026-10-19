from . import realtime, file, mapping, map_mode, profiles
from .realtime import input_device_options

classes = file.classes + realtime.classes + mapping.classes + map_mode.classes + profiles.classes


def register():
    mapping.register()


def unregister():
    map_mode.unregister()
    mapping.unregister()
