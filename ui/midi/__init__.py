from . import realtime, file, mapping
from .realtime import input_device_options

classes = file.classes + realtime.classes + mapping.classes


def register():
    mapping.register()


def unregister():
    mapping.unregister()
