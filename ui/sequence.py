import os
import bpy
from bpy.types import (Operator, UIList)
from bpy_extras.io_utils import ImportHelper

from .buttonspanel import AudVisButtonsPanel_Npanel
from ..utils import get_all_vse_strips


def _seq_has_error(name):
    if bpy.audvis.sequence_analyzers is None:
        return False
    analyzer = bpy.audvis.sequence_analyzers.get(name, None)
    if analyzer is None:
        return False
    return analyzer.load_error is not None


def _get_selected_sound_sequence(context):
    if context.scene.sequence_editor is None:
        return None
    props = context.scene.audvis
    seq_all = get_all_sound_sequences(context)
    if 0 <= props.sequence_list_index < len(seq_all):
        seq = seq_all[props.sequence_list_index]
        if seq.type == 'SOUND':
            return seq
    return None


class AUDVIS_UL_soundSequenceList(UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        filtered = [self.bitflag_filter_item] * len(items)
        ordered = [index for index, item in enumerate(items)]
        for i in range(len(items)):
            if items[i].type != 'SOUND':
                filtered[i] &= ~self.bitflag_filter_item
        return filtered, ordered

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        custom_icon = 'SEQ_SEQUENCER'
        if _seq_has_error(item.sound.name):
            layout.alert = True
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item.audvis, "enable", text="")
            layout.label(text=item.name)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon=custom_icon)


# copied from space_sequencer.py
def get_all_sound_sequences(context):
    try:
        ret = []
        for seq in get_all_vse_strips(context.scene):
            if seq.type == 'SOUND':
                ret.append(seq)
        return ret
    except AttributeError as e:
        return []


class AUDVIS_OT_FrameAlign(Operator):
    bl_idname = "audvis.framealign"
    bl_label = "Align End Frame by Sequences"

    def execute(self, context):
        value = 1
        for seq in get_all_sound_sequences(context):
            value = max(value, seq.frame_final_end)
        context.scene.frame_end = value
        return {"FINISHED"}


class AUDVIS_OT_SequenceRemove(Operator):
    bl_idname = "audvis.sequence_remove"
    bl_label = "Remove Sound Sequence"
    bl_description = ""

    @classmethod
    def poll(cls, context):
        if _get_selected_sound_sequence(context) is None:
            return False
        return True

    def execute(self, context):
        seq = _get_selected_sound_sequence(context)
        if seq is not None:
            for seq2 in list(get_all_vse_strips(context.scene)):
                seq2.select = False
            seq.select = True
            bpy.ops.sequencer.delete()
        return {'FINISHED'}


class AUDVIS_OT_SequenceAdd(Operator, ImportHelper):
    bl_idname = "audvis.sequence_add"
    bl_label = "Add Sound Sequence"

    filename_ext: bpy.props.StringProperty(default=";".join(bpy.path.extensions_audio))
    filter_glob: bpy.props.StringProperty(
        default=";".join(["*" + ext for ext in bpy.path.extensions_audio]),
        options={'HIDDEN'},
    )
    files: bpy.props.CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    directory: bpy.props.StringProperty(
        subtype='DIR_PATH',
    )

    # filter_glob = ";".join(["*." + ext for ext in bpy.path.extensions_audio])

    def _find_free_channel(self, context):
        free_channels = [True for x in range(len(context.scene.sequence_editor.channels))]
        for tmp in context.scene.sequence_editor.strips_all:
            free_channels[tmp.channel - 1] = False
        if True not in free_channels:
            return {"CANCELLED"}
        if True in free_channels:
            return free_channels.index(True) + 1
        return -1

    def execute(self, context):
        context.scene.sequence_editor_create()
        channel = self._find_free_channel(context)
        if channel == -1:
            return {"CANCELLED"}
        frame = 0
        for filepath in self.files:
            strip = getattr(context.scene.sequence_editor,
                            "strips" if hasattr(context.scene.sequence_editor, "strips") else "sequences").new_sound(
                name=filepath.name,
                filepath=os.path.join(self.directory, filepath.name),
                channel=channel,
                frame_start=frame)
            if strip:
                frame = strip.frame_final_end

        return {"FINISHED"}


class AUDVIS_PT_sequenceNpanel(AudVisButtonsPanel_Npanel):
    bl_label = "Sequence Analyzer"

    @classmethod
    def poll(cls, context):
        return True

    def draw_header(self, context):
        col = self.layout.column(align=True)
        col.prop(context.scene.audvis, "sequence_enable", text="")

    def draw(self, context):
        props = context.scene.audvis
        layout = self.layout
        col = layout.column(align=True)
        col.template_list("AUDVIS_UL_soundSequenceList", "sound_sequence_list",
                          context.scene.sequence_editor,
                          "sequences_all" if hasattr(context.scene.sequence_editor, "sequences_all") else "strips_all",
                          props, "sequence_list_index")
        row = col.row()
        row.operator("audvis.sequence_add")
        row.operator("audvis.sequence_remove")
        seq = _get_selected_sound_sequence(context)
        if seq is not None:
            col = layout.column(align=True)
            if _seq_has_error(seq.sound.name):
                col.alert = True
                col.label(text="File not found", icon="ERROR")
            col.prop(seq, "name")
            col.prop(seq, "frame_start")
            col.prop(seq, "frame_offset_start")
            col.prop(seq, "frame_final_duration")
        col = layout.column(align=True)
        col.prop(context.scene.audvis, "sequence_chunks")
        col.operator("audvis.framealign")


classes = [
    AUDVIS_OT_FrameAlign,
    AUDVIS_OT_SequenceRemove,
    AUDVIS_OT_SequenceAdd,
    AUDVIS_PT_sequenceNpanel,
    AUDVIS_UL_soundSequenceList,
]
