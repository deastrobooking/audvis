# Motion FX: Cascade, Scatter, Orbit

Motion FX are algorithmic animations driven by sound (or MIDI, or plain keyframes). They live in the
**Motion FX** panel of the AudVis sidebar. Enable Motion FX in the panel header, select an object and use one
of the three sub-panels. Every effect runs live while playing (also with the Realtime Analyzer / Party Mode) and
follows the sliders while the animation is paused.

All effects share the same **Sound** settings:

- **Audio Source** - Sound (frequency range of the enabled analyzers), MIDI (a note) or Off (keyframes only)
- **Spread** - how the value is distributed over elements (copies, satellites, groups of pieces)
    - **Same for All** - one frequency range for everything
    - **Frequency Bands** - element *i* uses `Frequency Start + i * Frequency Step` (or `MIDI Note + i`)
    - **Time Delay** - element *i* gets the value from *i × Delay* frames ago - a wave travels through
- **Sensitivity** - multiplies the analyzer value. The effects expect values around 0..1
- **Attack / Release** - how fast values rise and fall back. Low Release = pieces float back slowly after a hit

Smoothing and Time Delay need the frames to be played one after another; after a jump (scrubbing) they start
over. Render from the first frame, or [bake](#baking), if you need identical results.

## Cascade

Duplicates the active object into a chain of copies. Each copy is the previous one moved by **Offset**, rotated by
**Rotation** and scaled by **Scale**. The steps compound, so a small rotation gives a spiral or a helix, scale
below 1 gives a tunnel.

- **Generate / Regenerate** - creates the copies in a new collection (linked data by default). The trash button
  deletes them. The source object itself stays where it is - it is copy number 0
- **Reveal** - shows the copies one after another. Keyframe it from 0 to 1 for a build-up
- **Sound → Offset / Rotation** - sound stretches the steps. With Time Delay, the chain whips like a tail
- **Sound → Pulse** - scales each copy (not compounding)
- **Sound → Reveal** - the sound of the first copy grows the chain
- **Color Gradient** - sets the Object Color of the copies. Use it with *Object Info > Color* in shaders or
  *Viewport Shading > Color > Object*

## Scatter

Tears a mesh apart into pieces and puts it back together.

- **Tear Into** - Faces (every face becomes a shard), Loose Parts (every mesh island moves as one), Vertices
  (every vertex alone - faces stretch like a web)
- **Tear Apart** - splits the mesh and keeps a copy of the original. **Restore Original Mesh** (the arrow button)
  puts it back. Changing *Tear Into* needs *Tear Apart Again*. Meshes with shape keys are not supported
- **Amount** - 0 = assembled, 1 = fully scattered. Keyframe it, or let **Sound → Amount** do it
- **Direction** - Outward (from the object origin), Face Normal, Random or a fixed Vector, mixed with randomness
- **Tumble / Tumble Speed / Shrink / Turbulence** - how the pieces behave while flying
- **Stagger** - pieces leave one after another, ordered by Distance (inner first), Height or randomly. With
  Frequency Bands, the order also picks the band: by default bass shatters the core and treble peels the surface
  (*Bands / Delay Steps* sets the number of groups). With Time Delay, the shattering travels through the mesh

The rest positions are stored in the `audvis_rest` and `audvis_piece` mesh attributes - you can use them in
Geometry Nodes or shaders too. Like the Shape Modifier, Scatter writes mesh data for every frame: enable
*Render > Lock Interface* when rendering.

## Orbit / Gravity

The active object (an Empty works best) is the center. Satellites circle it on tilted orbits.

- **Populate** - creates **Count** linked copies of **Satellite Object** (small ico spheres if empty). You can also
  pick any existing collection in **Satellites**
- **Radius Min / Max, Inclination** - the size and thickness of the swarm. Inclination 90+ gives a spherical swarm
- **Speed, Kepler Speeds** - turns per second; with Kepler, outer orbits are slower like planets
- **Rotation** - Spin (random axis), Follow Orbit (face the flight direction) or None
- **Sound → Speed** - sound pushes the orbits forward (it accumulates, so it never jumps back)
- **Sound → Radius** - sound pushes satellites outward

**Gravity Sphere** - *Gravity* (0..1, keyframe it and/or drive it with *Sound → Gravity*) pulls the satellites
in, onto a sphere of **Sphere Radius** around the center:

- **Sphere Shell** - satellites spread evenly over the sphere surface - the swarm becomes a sphere of objects.
  **Shell Spin** rotates it
- **Radial** - satellites fall straight down onto the sphere
- **Core** - satellites are swallowed by the center and shrink to nothing
- **Gravity Stagger** - outer satellites arrive later
- **Show Sphere** - if the center is an Empty, it is displayed as the gravity sphere

Moving, rotating or scaling the center moves the whole system.

## Baking

Cascade and Orbit can be baked to keyframes (**Bake to Keyframes**) for the scene frame range. The live effect is
disabled afterwards so the keyframes play. Scatter is a function of Amount and time and doesn't need baking -
keyframe *Amount* instead.

## Scripting

The settings are in `obj.audvis.cascade`, `obj.audvis.scatter` and `obj.audvis.orbit`; Motion FX for the scene is
`scene.audvis.motion_enable`.
