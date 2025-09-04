import bpy
import sys
from bpy.types import (
    Operator,
)
import bpy
from bpy_extras.io_utils import ImportHelper

from .. import midi_file_baker


class AUDVIS_OT_midiFileOpen(Operator, ImportHelper):
    bl_idname = "audvis.midi_file_open"
    bl_label = "Add Midi File"
    bl_description = ""

    filter_glob: bpy.props.StringProperty(
        default='*.mid;*.midi',
        options={'HIDDEN'}
    )

    strip_silent_start: bpy.props.BoolProperty(
        name="Strip Silent Beginning of MIDI",
        description="MIDI files use to have sometimes quite a long time from beginning to first note."
                    " This cuts that empty, silent part.",
        default=True
    )

    midi_note_base: bpy.props.EnumProperty(
        name="Midi base",
        description="AudVis internally uses C-1=0. Here you can adjust imported data",
        items = [
            ("-2", "C-2=0 ; C4=72", ""),
            ("-1", "C-1=0 ; C4=60", ""),
            ("0", "C0=0 ; C4=48", ""),
        ],
        default="-1"
    )

    @classmethod
    def poll(cls, context):
        return bpy.audvis.is_midi_realtime_supported()

    def execute(self, context):
        midi_file_baker.bake(context.scene, self.filepath, self.strip_silent_start, self.midi_note_base)

        return {'FINISHED'}
