# AudVis – notes for coding agents

AudVis is a Blender add-on/extension (manifest `blender_manifest.toml`, min Blender 4.2) for live audio
visualization: sound/MIDI analyzers feed an `audvis()` driver function, plus generators, Motion FX and live
performance tools. The maintainer develops on an Apple-silicon Mac with **Blender 5.2.2** at
`/Applications/Blender.app` and uses both Claude Code and Codex on this repo. Keep this file current for both.

## Layout

- `__init__.py` – add-on entry. `register2()` registers `ui.classes + scripting.classes` and **silently swallows
  `register_class` errors**, so a broken class just disappears. `tests/blender_compatibility_smoke.py` catches that.
- `audvis_class.py` – the `AudVis` singleton (`bpy.audvis`). `driver(low, high, ch, **kw)` is the driver function;
  it reads `bpy.context.scene`, not a scene argument. `update_data` runs on `frame_change_pre`.
  `midi_cc(control, channel)` → 0..1 or None. `get_midi_realtime_analyzer(scene)` can return None.
- `analyzer/` – analyzers. `analyzer/motion/` is the Motion FX engine (`MotionEngine(driver, cc_reader)`);
  `audio.py` holds the shared sound sampling, triggers, MIDI CC helpers and the EQ band edges/gain (`EQ_EDGES`,
  `eq_gain`, `eq_band`). Keep it free of `bpy` imports where possible – tests drive it with `SimpleNamespace` props.
- `ui/` – panels and operators, one module per feature (`motion.py`, `eq.py`, `partymode/`, `midi/`…).
  Sidebar panels subclass `AudVisButtonsPanel_Npanel` (`ui/buttonspanel.py`). Add new modules to the import list,
  `classes` and `register()/unregister()` in `ui/__init__.py`.
- `ui/props/` – PropertyGroups. A group used by `AudvisSceneProperties` must be listed **before** it in
  `ui/props/__init__.py`. Window-level flags live in `AudvisWindowProperties` (`ui/__init__.py`).
- Compat helpers: `utils.py` (VSE strips, slotted-action f-curves, `call_ops_override`), `grease_pencil_compat.py`,
  `switchscenes.py` (`switch_window_scene` – the one way to switch scenes and restart playback).
- `doc/*.md` – user docs, linked from `README.md`. Update them with every user-facing change.

## Conventions and gotchas

- Motion FX props get an automatic `update=motion.refresh` via `_refresh_on_change` in `ui/props/motion.py`;
  add internal/state props to its `skip` set.
- Don't write RNA properties from timers or every frame just for display (it dirties the file and triggers
  depsgraph updates). Keep transient UI state such as meter levels in module-level dicts (see `ui/eq.py`).
- Modal operators: store names, not RNA references (scenes/objects may be deleted), and handle the MIDI analyzer
  becoming None / MIDI Realtime being switched off mid-modal – cancel cleanly and reset any `is_learning` flag.
- MIDI thread messages: `msg.channel` is 1-based; CC messages have `.control`.
- Blender 5.2: `GizmoGroup`/`Gizmo` classes have no `is_registered`; `LOGIC_EDITOR` exists only in UPBGE, so
  `AUDVIS_PT_Bge` never registers in regular Blender (expected). `SoundSequence` became `SoundStrip`.
- Match the surrounding style: short docstrings, `bpy.props` annotations, descriptions on user-facing props.

## Test

All of these must pass before committing (headless, ~1 min total):

```sh
B=/Applications/Blender.app/Contents/MacOS/Blender
$B --background --factory-startup --python-exit-code 1 --python tests/blender_motion_smoke.py
$B --background --factory-startup --python-exit-code 1 --python tests/blender_motion_features_smoke.py
$B --background --factory-startup --python-exit-code 1 --python tests/blender_grease_pencil_smoke.py
$B --background --factory-startup --python-exit-code 1 --python tests/blender_compatibility_smoke.py -- "$(mktemp -d)"
python3 -m unittest tests.test_blender_compatibility tests.test_grease_pencil_compat
```

Headless tests can't exercise drawing, windows or real MIDI hardware – say so when reporting UI work.

## Build and install locally

```sh
python3 build-macos.py --blender-version 5.2 --skip-download   # dist/audvis-<ver>-blender5.2-macos-arm64.zip
$B --command extension install-file -r user_default dist/audvis-8.0.1-blender5.2-macos-arm64.zip
```

`--skip-download` uses the wheels cached in `wheels/blender52/macos-arm64/`. Without `--blender-version 5.2` it
builds the Blender 4.2–5.0 (Python 3.11) packages. `dist/` and `wheels/` are git-ignored.

## Git

- Work on `main` unless asked otherwise; commit only when asked.
- Commit messages: a short summary line plus bullet points of what changed – not a chat transcript.
