import bpy


def try_switch_scenes(current_scene):
    if not current_scene.audvis.realtime_enable:
        return False
    if not current_scene.audvis.realtime_switchscenes:
        return False
    if current_scene.frame_current == current_scene.frame_start:
        return False
    if current_scene.frame_current != current_scene.frame_end:
        return False
    if current_scene.frame_start == current_scene.frame_end:
        return False
    if len(bpy.data.scenes) < 2:
        return False
    if not hasattr(bpy.context.window, 'scene'):  # while rendering, there is not window thankfully
        return False
    if not bpy.context.screen.is_animation_playing:
        return False
    try:
        for particle_settings in bpy.data.particles:
            particle_settings.frame_start = particle_settings.frame_start  # clear cache - really ugly way
    except Exception as e:
        # print(e)
        pass
    use_next = False
    set_this_scene = None
    for s in bpy.data.scenes:
        if use_next:
            set_this_scene = s
            break
        elif s is current_scene:
            use_next = True
    if set_this_scene is None:
        set_this_scene = bpy.data.scenes[0]
    _skip_to_start(current_scene)
    _skip_to_start(set_this_scene)
    bpy.context.window.scene = set_this_scene
    # Scene changes are evaluated after this handler returns in newer Blender
    # versions. Toggling playback synchronously can therefore leave playback
    # paused until the user presses Play. Resume on the next main-loop tick.
    _resume_playback_after_scene_change()
    return True


def _skip_to_start(scene):
    scene.frame_current = scene.frame_start


def _resume_playback_after_scene_change():
    attempts = 0

    def resume():
        nonlocal attempts
        attempts += 1
        windows = list(getattr(bpy.context.window_manager, "windows", ()))
        if not windows and bpy.context.window is not None:
            windows = [bpy.context.window]
        for window in windows:
            screen = window.screen
            try:
                with bpy.context.temp_override(window=window, screen=screen):
                    # A normal scene swap leaves playback stopped. If the
                    # flag is stale and still says playing, the first toggle
                    # pauses it and the second starts it again.
                    was_playing = bool(screen.is_animation_playing)
                    bpy.ops.screen.animation_play()
                    if was_playing:
                        bpy.ops.screen.animation_play()
                    return None
            except (RuntimeError, AttributeError):
                continue
        # Scene evaluation and operator context can take more than one tick.
        # Give Blender a bounded retry window, then leave its state alone.
        return 0.05 if attempts < 40 else None

    bpy.app.timers.register(resume, first_interval=0.0)
