import math

import bpy

from .midi import AudvisMidiGeneratorsProperties
from .. import motion


class AudvisMotionAudioProperties(bpy.types.PropertyGroup):
    source: bpy.props.EnumProperty(name="Audio Source", default='sound', items=[
        ('off', "Off", "No sound - use only keyframed / manual values"),
        ('sound', "Sound", "Frequency range of the sound analyzers"),
        ('midi', "MIDI", "MIDI note"),
    ])
    spread: bpy.props.EnumProperty(name="Spread", default='same', items=[
        ('same', "Same for All", "Every element reacts to the same frequency range"),
        ('bands', "Frequency Bands", "Each element gets its own frequency range (or MIDI note)"),
        ('delay', "Time Delay", "Each element reacts later than the previous one - a wave travels through"),
    ])
    freq_start: bpy.props.FloatProperty(name="Frequency Start", default=20, min=0)
    freq_width: bpy.props.FloatProperty(name="Frequency Range", default=150, min=.01)
    freq_step: bpy.props.FloatProperty(name="Frequency Step", default=100, min=0,
                                       description="With Frequency Bands: distance between bands of two elements")
    delay: bpy.props.IntProperty(name="Delay (frames)", default=2, min=0, soft_max=30)
    midi_note: bpy.props.IntProperty(name="MIDI Note", default=36, min=0, max=127)
    midi: bpy.props.PointerProperty(name="MIDI", type=AudvisMidiGeneratorsProperties)
    channel: bpy.props.IntProperty(name="Sound Channel", default=1, min=1, soft_max=32)
    sound_sequence: bpy.props.StringProperty(name="Sequence", default="")
    sequence_channel: bpy.props.IntProperty(name="Sequence Channel", default=0, min=0,
                                            description="Channel number in Video Sequence Editor")
    factor: bpy.props.FloatProperty(name="Sensitivity", default=.1, min=0, soft_max=2, precision=3,
                                    description="Multiply the analyzer value. Effects expect values around 0..1")
    attack: bpy.props.FloatProperty(name="Attack", default=1, min=.01, max=1, subtype='FACTOR',
                                    description="How fast values rise (1 = immediately)")
    release: bpy.props.FloatProperty(name="Release", default=.15, min=.01, max=1, subtype='FACTOR',
                                     description="How fast values fall back (lower = slower, floatier)")


class AudvisMotionCascadeProperties(bpy.types.PropertyGroup):
    enable: bpy.props.BoolProperty(name="Enable Cascade", default=False)
    is_baking: bpy.props.BoolProperty(default=False)
    collection: bpy.props.PointerProperty(name="Copies", type=bpy.types.Collection)
    count: bpy.props.IntProperty(name="Copies", default=12, min=1, soft_max=200)
    linked: bpy.props.BoolProperty(name="Linked Data", default=True,
                                   description="Copies share the mesh/curve data with the source")
    offset: bpy.props.FloatVectorProperty(name="Offset", default=(0, 0, .5), subtype='TRANSLATION',
                                          description="Each copy moves this much from the previous one")
    rotation: bpy.props.FloatVectorProperty(name="Rotation", default=(0, 0, math.radians(15)),
                                            subtype='EULER', description="Added to each copy")
    scale_step: bpy.props.FloatVectorProperty(name="Scale", default=(.95, .95, .95), min=.01, soft_max=2,
                                              subtype='XYZ', description="Multiplied for each copy")
    audio: bpy.props.PointerProperty(type=AudvisMotionAudioProperties)
    audio_offset: bpy.props.FloatProperty(name="Sound → Offset", default=1, soft_min=-5, soft_max=5,
                                          description="Sound stretches the offset step")
    audio_rotation: bpy.props.FloatProperty(name="Sound → Rotation", default=0, soft_min=-5, soft_max=5,
                                            description="Sound twists the rotation step")
    audio_scale: bpy.props.FloatProperty(name="Sound → Pulse", default=0, soft_min=-2, soft_max=5,
                                         description="Sound scales each copy (doesn't compound)")
    reveal: bpy.props.FloatProperty(name="Reveal", default=1, min=0, max=1, subtype='FACTOR',
                                    description="Show copies one after another. Keyframe it for a build-up")
    audio_reveal: bpy.props.FloatProperty(name="Sound → Reveal", default=0, soft_min=-2, soft_max=2,
                                          description="Sound of the first copy adds to Reveal")
    use_color: bpy.props.BoolProperty(name="Color Gradient", default=False,
                                      description="Set Object Color of the copies (Object Info > Color in shaders,"
                                                  " Viewport Shading > Color > Object)")
    hue: bpy.props.FloatProperty(name="Hue", default=0, min=0, max=1, subtype='FACTOR')
    hue_step: bpy.props.FloatProperty(name="Hue Step", default=.04, soft_min=-.2, soft_max=.2)
    hue_speed: bpy.props.FloatProperty(name="Hue Cycle Speed", default=0, soft_min=-1, soft_max=1,
                                       description="Hue rotations per second")
    saturation: bpy.props.FloatProperty(name="Saturation", default=.8, min=0, max=1, subtype='FACTOR')
    audio_hue: bpy.props.FloatProperty(name="Sound → Hue", default=0, soft_min=-1, soft_max=1)


class AudvisMotionScatterProperties(bpy.types.PropertyGroup):
    enable: bpy.props.BoolProperty(name="Enable Scatter", default=False, update=motion.scatter_enable_update)
    original_mesh: bpy.props.PointerProperty(name="Original Mesh", type=bpy.types.Mesh)
    prepared_id: bpy.props.IntProperty(default=0)
    prepared_mode: bpy.props.StringProperty(default="")
    piece_mode: bpy.props.EnumProperty(name="Tear Into", default='faces', items=[
        ('faces', "Faces", "Every face becomes a separate shard"),
        ('islands', "Loose Parts", "Every loose part (mesh island) moves as one piece"),
        ('vertices', "Vertices", "Every vertex moves alone - faces stretch like a web"),
    ])
    seed: bpy.props.IntProperty(name="Seed", default=1)
    amount: bpy.props.FloatProperty(name="Amount", default=0, min=0, max=1, subtype='FACTOR',
                                    description="0 = assembled, 1 = fully scattered. Keyframe it")
    audio: bpy.props.PointerProperty(type=AudvisMotionAudioProperties)
    audio_amount: bpy.props.FloatProperty(name="Sound → Amount", default=1, soft_min=-2, soft_max=2)
    audio_elements: bpy.props.IntProperty(name="Bands / Delay Steps", default=8, min=1, soft_max=64,
                                          description="With Frequency Bands or Time Delay: pieces are split into"
                                                      " this many groups by the Stagger order")
    distance: bpy.props.FloatProperty(name="Distance", default=2, soft_min=0, soft_max=20, subtype='DISTANCE')
    distance_random: bpy.props.FloatProperty(name="Distance Random", default=.5, min=0, max=1, subtype='FACTOR')
    direction: bpy.props.EnumProperty(name="Direction", default='outward', items=[
        ('outward', "Outward", "Away from the object origin"),
        ('normal', "Face Normal", "Along the piece's normal"),
        ('random', "Random", ""),
        ('vector', "Vector", "Every piece flies the same direction"),
    ])
    direction_vector: bpy.props.FloatVectorProperty(name="Vector", default=(0, 0, 1), subtype='XYZ')
    direction_random: bpy.props.FloatProperty(name="Direction Random", default=.2, min=0, max=1, subtype='FACTOR')
    rotation: bpy.props.FloatProperty(name="Tumble", default=180, soft_min=0, soft_max=720,
                                      description="Max rotation of a piece when fully scattered (degrees)")
    tumble_speed: bpy.props.FloatProperty(name="Tumble Speed", default=0, soft_min=0, soft_max=2,
                                          description="Keep rotating while scattered (turns per second)")
    shrink: bpy.props.FloatProperty(name="Shrink", default=0, min=0, max=1, subtype='FACTOR')
    turbulence: bpy.props.FloatProperty(name="Turbulence", default=0, min=0, soft_max=2, subtype='DISTANCE',
                                        description="Pieces float around while scattered")
    turbulence_speed: bpy.props.FloatProperty(name="Turbulence Speed", default=.5, min=0, soft_max=4)
    stagger: bpy.props.FloatProperty(name="Stagger", default=0, min=0, soft_max=4,
                                     description="Pieces leave one after another instead of all together")
    stagger_mode: bpy.props.EnumProperty(name="Stagger Order", default='distance', items=[
        ('distance', "Distance", "Inner pieces first"),
        ('z', "Height", "Bottom pieces first"),
        ('random', "Random", ""),
    ])
    stagger_invert: bpy.props.BoolProperty(name="Invert Order", default=False)


class AudvisMotionOrbitProperties(bpy.types.PropertyGroup):
    enable: bpy.props.BoolProperty(name="Enable Orbit", default=False)
    is_baking: bpy.props.BoolProperty(default=False)
    collection: bpy.props.PointerProperty(name="Satellites", type=bpy.types.Collection,
                                          description="Objects orbiting this object")
    source_object: bpy.props.PointerProperty(name="Satellite Object", type=bpy.types.Object,
                                             description="Copied by Populate. Empty = small ico spheres")
    count: bpy.props.IntProperty(name="Count", default=40, min=1, soft_max=2000)
    seed: bpy.props.IntProperty(name="Seed", default=1)
    radius_min: bpy.props.FloatProperty(name="Radius Min", default=2, min=.01, subtype='DISTANCE')
    radius_max: bpy.props.FloatProperty(name="Radius Max", default=5, min=.01, subtype='DISTANCE')
    inclination: bpy.props.FloatProperty(name="Inclination", default=25, min=0, max=180,
                                         description="Max tilt of the orbits (degrees). 90+ = spherical swarm")
    speed: bpy.props.FloatProperty(name="Speed", default=.1, soft_min=-2, soft_max=2,
                                   description="Turns per second of the innermost orbit")
    kepler: bpy.props.BoolProperty(name="Kepler Speeds", default=True,
                                   description="Outer orbits are slower, like planets")
    scale: bpy.props.FloatProperty(name="Scale", default=1, min=0, soft_max=5)
    scale_random: bpy.props.FloatProperty(name="Scale Random", default=.3, min=0, max=1, subtype='FACTOR')
    align: bpy.props.EnumProperty(name="Rotation", default='spin', items=[
        ('spin', "Spin", "Rotate around a random axis"),
        ('tangent', "Follow Orbit", "Face the flight direction"),
        ('none', "None", ""),
    ])
    spin_speed: bpy.props.FloatProperty(name="Spin Speed", default=.25, soft_min=-2, soft_max=2)
    audio: bpy.props.PointerProperty(type=AudvisMotionAudioProperties)
    audio_speed: bpy.props.FloatProperty(name="Sound → Speed", default=.5, soft_min=-5, soft_max=5,
                                         description="Sound pushes the orbits forward")
    audio_radius: bpy.props.FloatProperty(name="Sound → Radius", default=0, soft_min=-1, soft_max=2,
                                          description="Sound pushes satellites outward")
    gravity: bpy.props.FloatProperty(name="Gravity", default=0, min=0, max=1, subtype='FACTOR',
                                     description="Pull the satellites onto the gravity sphere. Keyframe it")
    audio_gravity: bpy.props.FloatProperty(name="Sound → Gravity", default=0, soft_min=-2, soft_max=2)
    gravity_mode: bpy.props.EnumProperty(name="Gravity Shape", default='shell', items=[
        ('shell', "Sphere Shell", "Satellites spread evenly over the sphere surface"),
        ('radial', "Radial", "Satellites fall straight down onto the sphere"),
        ('core', "Core", "Satellites are swallowed by the center and shrink"),
    ])
    sphere_radius: bpy.props.FloatProperty(name="Sphere Radius", default=1, min=0, subtype='DISTANCE',
                                           update=motion.orbit_sphere_update)
    show_sphere: bpy.props.BoolProperty(name="Show Sphere", default=True, update=motion.orbit_sphere_update,
                                        description="If the center is an Empty, display it as the gravity sphere")
    gravity_stagger: bpy.props.FloatProperty(name="Gravity Stagger", default=.5, min=0, soft_max=4,
                                             description="Outer satellites arrive later")
    shell_spin: bpy.props.FloatProperty(name="Shell Spin", default=.05, soft_min=-1, soft_max=1,
                                        description="Turns per second of the sphere shell")


def _refresh_on_change(cls):
    """Give every property without its own update callback motion.refresh, so the
    viewport follows the sliders while the animation is paused."""
    skip = {'is_baking', 'prepared_id', 'prepared_mode', 'original_mesh'}
    for name, prop in cls.__annotations__.items():
        if name not in skip and 'update' not in prop.keywords:
            cls.__annotations__[name] = prop.function(**prop.keywords, update=motion.refresh)
    return cls


classes = [_refresh_on_change(cls) for cls in [
    AudvisMotionAudioProperties,
    AudvisMotionCascadeProperties,
    AudvisMotionScatterProperties,
    AudvisMotionOrbitProperties,
]]
