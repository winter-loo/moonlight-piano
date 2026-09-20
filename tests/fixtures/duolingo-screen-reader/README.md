# Duolingo screen-reader regression fixtures

These are unmodified ADB screenshots captured from the OPPO PHJ110 during
Duolingo Music exercises. `expected.json` records the manually verified events
at and to the right of the visible judgment line.

- `beamed-note-groups.png`: dense eighth-note beams; historically exposed five
  missed noteheads and incorrect judgment-line detection with a non-green avatar.
- `rests-and-edge-note.png`: quarter, half, and eighth rests plus a clipped C4;
  historically exposed piano-key tops misidentified as A3 notes.
- `low-notes-and-rests.png`: genuine A3/B3/C4 notes mixed with rests; protects
  against filters that remove the keyboard false positives by deleting low notes.
- `quarter-half-whole-rests.png`: one F4 followed by quarter, half, and whole
  rests; covers whole-rest classification and an eight-beat two-measure result.
- `dotted-quarter-and-beamed-notes.png`: a dotted F4 quarter followed by an
  eighth note, quarter notes, beamed eighths, and low C4; covers augmentation-dot
  detection and an eight-beat two-measure result.
- `bidirectional-stems-and-steep-beams.png`: upward and downward stems, steeply
  slanted beams, and a B-flat under a light-gray key signature; protects the
  structural stem/beam detector from direction and angle assumptions.
- `downstem-flag-touching-notehead.png`: a B4 eighth note whose downward
  stem and single flag form one compact silhouette with the notehead; protects
  notehead discovery and flag classification for this orientation.
- `two-flats-occluded-downstem.png`: B-flat/E-flat key signature and an E-flat
  note whose downward stem overlaps the translucent judgment line; protects
  multi-flat pitch mapping and occlusion-tolerant stem detection.
- `single-flat-mixed-rhythm-and-edge-note.png`: manually verified one-flat
  screen containing standalone upward/downward eighth-note flags, a downward
  C5-B-flat4 beam, four eighth rests, one quarter rest, and a clipped G4 with
  deliberately unknown duration; the complete visible sequence totals eight
  known beats before the clipped note.

The PNGs are test inputs, not generated test output. Do not replace them with
annotated images because the detector must receive the original pixels.
