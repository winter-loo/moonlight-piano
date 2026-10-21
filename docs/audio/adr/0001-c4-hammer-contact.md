# ADR 0001: A bounded, dissipative C4 hammer experiment

Date: 2026-10-21

Status: accepted for the C4 development experiment; physical calibration and the
final production solver remain unresolved

Issue: [#7](https://github.com/winter-loo/moonlight-piano/issues/7)

Specification: [professional piano specification](../../product/月光琴房-专业物理建模钢琴音色规范-v0.1.md),
especially sections 6, 14, 16, 17, 19, and 25.1

## Objective and scope

The previous C4 tracer excited a modal string with an instantaneous, velocity-scaled
impulse. That established the shared Rust/offline/WASM render boundary but could
not establish a physical connection between touch, contact duration, and spectrum.
The hypothesis for this experiment is that a moving hammer with nonlinear felt
compression can produce continuous, audibly different weak and strong attacks
through its interaction with the existing string state.

This decision changes `PianoEngine`'s C4 development path. It does not replace the
accepted full-keyboard `BasicPianoEngine`, its PR #46 tone fixes, or the production
practice pages' default instrument. The lab can compare the two. A preference for
one listening example is not evidence that this candidate is a calibrated piano.

The experiment retains the common engine, event, model-validation, and host
boundaries. It uses no note recordings, cached note waveforms, triggered noise,
EQ, or room effect to create its dynamic response. Damper/repedal behavior (#8),
the physical octave (#9), detailed key action (#15), and soundboard/radiation
remain separate work.

## Decision

Represent each retained string mode by displacement and velocity. Couple all
modes to one hammer through reciprocal strike weights. Use implicit midpoint for
the linear mechanical equations and a discrete gradient of the one-sided felt
potential for the nonlinear interaction. Solve one scalar contact force with a
fixed bisection budget per substep.

The candidate choices are:

| Choice | Candidate value or rule |
| --- | --- |
| Felt elastic exponent | `p = 3` |
| Felt damping exponent | `q = 2` |
| Hammer mass | `0.008 kg` |
| Elastic coefficient | `1e11 N/m^3` |
| Damping coefficient | `3e6 N s/m^3` |
| Mass of each retained mode | `0.02 kg` |
| Strike position | `1/7` of the equivalent string length |
| Strike weight of mode `i`, starting at 1 | `sin(i pi / 7)` |
| Velocity map | Continuous Hermite bridge below MIDI 1; geometric launch-speed curve from `.12` to `5 m/s` above it, as defined below |
| Internal rate | Four mechanical substeps per output sample |
| Scalar contact solve | 32 bisection iterations, no convergence-dependent loop |
| Mechanical precision | `f64`; host PCM is `f32` |
| Contact lifecycle | One impact per positive NoteOn, then passive backcheck |

These numbers are independently chosen equivalent parameters, not measurements
of a particular piano. They are explicit in `HammerParameters` and validated by
`PianoEngine::new_with_hammer` outside the audio callback. Changing them requires
fresh evidence; the constructor is the experimental calibration seam. They are
not a claim that the current minimal model-pack schema is a complete production
instrument format.

Finite velocity inputs are clamped to `[0, 1]`; zero does not strike. Non-finite
events are rejected before any event in the block is applied. The retained seed
argument does not add random gain to this deterministic mechanical model.

For the launch curve, let `u0 = 1/127`, `s = 0.12 m/s`, `V = 5 m/s`, and
`ell = ln(V/s)`. For `u >= u0`, set `t = (u-u0)/(1-u0)` and
`v_h = s exp(ell t)`. For `0 <= u < u0`, set `t = u/u0`, `d = s ell / 126`, and
`v_h = t^2 ((3s-d) + (d-2s)t)`. The ideal curve is continuous with a continuous
first derivative at `u0`; it starts at zero and reaches the upper speed anchor
at full velocity. The validated anchor range also gives `0 <= d <= 3s`, making
the lower Hermite segment monotone. This is an input-to-mechanics curve, not an
audio gain floor or a switch between excitation layers.

Initialization computes `ell`. The realtime path approximates `exp(x)` by a
degree-six positive Taylor polynomial at `x/16`, followed by four squarings.
All operations have a fixed budget and work within the validated nonnegative
interval. The approximation must be tested over the complete allowed anchor
range; its error is distinct from the mechanical integration error. At `x = 0`
the approximation has value and derivative one, preserving the Hermite join.

Earlier polynomial launch curves placed the lowest MIDI velocities in an
almost inaudible contact regime or produced adjacent level changes beyond the
declared gate. The geometric curve is an explicit development response. It is
not a measured controller or real-piano calibration. The full MIDI sweep and
the continuous input below MIDI 1 remain inspectable; monotone launch speed
alone does not prove an acoustically smooth or perceptually satisfactory curve.

The current model file supplies frequencies, decay times, and output weights.
Its amplitudes do not masquerade as measured modal masses or strike geometry.
Output is a provisional weighted sum of modal velocities, not calibrated sound
pressure or the final body-radiation model.

## Mechanical equations and reciprocal coupling

Let `q_i`, `v_i`, `m_i`, `k_i`, and `c_i` be modal displacement, velocity, mass,
stiffness, and viscous damping, and let `g_i` be the strike weight. Let `x_h`,
`v_h`, and `m_h` describe the hammer. The string displacement at contact is

\[
y_s=\sum_i g_i q_i,\qquad \delta=x_h-y_s.
\]

The equations solved are

\[
m_i\dot v_i=-k_iq_i-c_iv_i+g_iF,\quad \dot q_i=v_i,
\qquad m_h\dot v_h=-F,\quad \dot x_h=v_h.
\]

Using the same `g_i` for displacement observation and applied force is essential:
the contact work on the mechanical subsystems then sums to `-F d(delta)`.
Output weighting is separate from this mechanical coupling.

For the conservative part of the felt, define

\[
\Phi(\delta)=\frac K4[\delta]_+^4.
\]

The continuous candidate force during compression is
`K delta^3 + C delta^2 delta_dot`, clamped to be nonnegative. A detached hammer
does not exert a force. The discrete force below is an interval-averaged
approximation to this law, not its value at the end of a substep.

## Discrete contact law and bounded solve

For one step of duration `h`, let `a = delta_before`, `b = delta_after`. The
elastic discrete gradient is

\[
G(a,b)=\frac{\Phi(b)-\Phi(a)}{b-a},
\]

with its continuous limit when `a = b`. When both endpoints are nonnegative,
the implementation uses the cancellation-resistant factorization

\[
G(a,b)=\frac K4(a+b)(a^2+b^2).
\]

Positive-part branches handle a step that crosses the contact boundary. The
damping force is

\[
D(a,b)=\frac C{3h}\left([b]_+^3-[a]_+^3\right).
\]

This choice is a project derivation. It is the nonnegative secant conductance of
`C [delta]_+^3 / 3`, multiplied by the average relative velocity `(b-a)/h`.
Consequently `D(a,b) (b-a) >= 0`. It converges to `C delta^2 delta_dot` for a
smooth compressed trajectory. It is also monotone in `b`, which matters for a
bounded solver. Using `C delta_mid^2 delta_dot_mid` directly would lose that
monotonicity on sufficiently deep unloading.

The linear midpoint update makes the final compression affine in contact force:

\[
b=A-BF,\qquad B>0.
\]

Define `H(b) = G(a,b) + D(a,b)` and solve

\[
R(F)=F-\max(0,H(A-BF))=0.
\]

The potential is convex, so its discrete gradient is monotone in its second
argument. The damping term is also monotone. Thus `R` is strictly increasing,
and a root is bracketed by

\[
0\le F\le\max(0,H(A)).
\]

At the lower endpoint the residual is nonpositive; at the upper endpoint it is
nonnegative. This gives a bracket without a search loop. Thirty-two bisections
reduce its width by `2^32` in exact arithmetic. Floating-point rounding and the
remaining root error are measured; a fixed iteration count is not a proof of
exact conservation or unlimited-precision stability.

## Energy argument and diagnostic checks

For the coupled equivalent model, use

\[
E=\frac12m_hv_h^2+
\sum_i\left(\frac12m_iv_i^2+\frac12k_iq_i^2\right)+\Phi(\delta).
\]

Midpoint integration gives modal loss
`h sum(c_i v_mid_i^2)`, which is nonnegative. Without force clipping, the
discrete gradient cancels the change in felt potential against contact work;
the remaining felt loss is `D(a,b) (b-a) >= 0`.

If the candidate force is negative and is clamped to zero, then the damping
term must be negative and the compression must be decreasing. In that branch
the potential decrease is dissipated: the loss is `-(Phi(b)-Phi(a)) >= 0`.
Clipping therefore does not inject mechanical energy in the exact discrete
equations.

The code accumulates the analytic modal and felt losses, and separately records
energy removed by a backcheck. It does not define loss as the observed difference
between total energies. The independently computed ledger residual is

\[
E+E_{\mathrm{dissipated}}-E_{\mathrm{input}}.
\]

`max_energy_error_joules` retains the maximum absolute cumulative residual.
Tests and reports must check it against the input-energy scale, including weak
notes, repeated strikes into a moving string, and parameter extremes. The
residual is not itself an audible-distortion metric. A bounded mechanical
trajectory also does not certify that an arbitrary output gain is unclipped.

## Separation, backcheck, and repeated strikes

After a positive contact force has occurred, either a zero solved force or a
nonpositive endpoint compression catches the hammer. The backcheck removes and
accounts for remaining hammer kinetic energy and any residual felt potential.
It does not alter the modal string state. The force becomes exactly zero and
cannot restart until a subsequent NoteOn launches a new hammer. A one-second
limit on hammer activity handles exceptionally weak or nonintersecting flights;
its removed energy follows the same accounting.

This is a passive, explicitly simplified action model. It is not a claim to
simulate all possible within-strike recontacts, escapement, or incomplete key
reset. Those mechanisms remain #15. The simplification is stronger than the
specification's prohibition on restoring contact before renewed compression and
closing motion: this experiment waits for another NoteOn.

A repeated NoteOn first catches any old hammer and removes its stored felt
energy. It then positions the new hammer at the current string contact point
with zero compression and the prescribed velocity. Only its new kinetic energy
is added to the input ledger. Existing modal displacement and phase survive.
Reset intentionally clears the entire experimental state and its ledger.

During a step that crosses separation, the integrated force can be positive
although the final compression is nonpositive. Diagnostics expose zero current
force after the backcheck while retaining the peak force and accumulated contact
duration. Endpoint contact status and interval-averaged force must not be
interpreted as simultaneous continuous-time samples.

## Frequency, decay, and bandwidth

Plain midpoint integration warps modal frequencies. Initialization instead maps
each desired damped pole `z = r exp(j theta)` through the inverse bilinear map

\[
s=\frac2h\frac{z-1}{z+1},\quad
c_i=-2m_i\Re(s),\quad k_i=m_i|s|^2.
\]

Thus free modal evolution targets the model file's frequency and T60. The energy
argument uses this equivalent stiffness, not an unwarped stiffness substituted
after the solve. The output Nyquist guard is enforced before compilation; at
the four-times internal rate the compiled modes stay away from the bilinear
map's Nyquist singularity.

The current implementation returns one modal-velocity sample after four
substeps. It has no dedicated output decimation filter. Four-times integration
and a guarded modal list do not by themselves prove suppression of nonlinear
aliasing. The candidate must not be described as alias-free based on either
the passivity argument or native/WASM agreement. The evidence script compares
44.1/48 kHz output with a 176.4/192 kHz render, low-pass filtered and downsampled
using `scipy.signal.resample_poly`. It aligns their end-of-sample timestamps.
That measures combined integration and output-sampling convergence for one
strong C4 gesture. It cannot isolate an alias-only error or certify the entire
parameter space. A justified output bandwidth treatment remains a separate
requirement; the present solver/rate choice remains provisional.

## Alternatives considered

| Alternative | Decision for this experiment |
| --- | --- |
| Scaled impulse or a velocity-dependent output filter | Rejected: does not solve hammer/string contact. |
| Explicit contact integration | Not selected: would require a separate stable-step analysis over the entire parameter range. |
| Fully implicit Newton solve until convergence | Not selected: a convergence-dependent iteration count does not meet this callback's bounded-work contract. |
| Fixed-budget Newton with fallback | Not selected initially: more branch and convergence cases than the monotone scalar bisection. |
| Frozen nonnegative damping conductance | Valid alternative described by [1]; the chosen secant conductance retains monotonicity while averaging the compression-dependent coefficient. |
| Midpoint-evaluated `C delta^2` damping | Rejected here: its force can cease to be monotone in the final compression on unloading. |
| Energy quadratisation | Retained as an alternative: [3] avoids iterative nonlinear solves, but introduces auxiliary state and its own contact-force treatment. No comparative performance or fidelity advantage is claimed for our choice. |
| More substeps or a different felt exponent | Unresolved; select using convergence, contact, acoustic, listening, and deadline evidence. |

The four-times rate, polynomial exponents, eight-mode C4 fixture, and bisection
budget are experimental settings. They are not final sufficient-order claims
for the full instrument, nor approved exceptions to the professional gates.

## Data, evidence, and acceptance

No external piano recording, calibration set, development recording, or sealed
outer-test result was used to choose these parameters. The physical model file
and generated test signals are synthetic development inputs. The missing real
reference matrix in #20 remains missing; this experiment cannot close that issue.

Use [the C4 quality report instructions](../c4-hammer-quality.md) for the current
measurements and listening sequence. The commands below reproduce the numerical,
host, and realtime evidence; command availability is not a claim that a run
passed:

```sh
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
sh scripts/check-realtime-boundary.sh
npm run audio:wasm
python3 scripts/render-hammer-review.py
node --test tests/browser/physical-hammer-parity.test.mjs
```

Realtime smoke reports use the existing benchmark and checker:

```sh
MOONLIGHT_SOURCE_REVISION=$(git rev-parse HEAD) cargo run --release -p moonlight-bench -- \
  --mode smoke --blocks 2048 --device-id local-development \
  --output work/realtime/hammer.json
python3 scripts/check-realtime-report.py work/realtime/hammer.json
```

For a dirty source tree, supply the commit-plus-patch identity required by
`docs/audio/realtime-budget.md` instead of attributing measurements to the bare
commit. Reports must retain source/model hashes and actual CPU, fixed state
memory, executable/model bytes, sample rate, block size, and deadline quantiles.
Before/after comparisons require equivalent environments and actual reports;
none of the constants in this ADR are performance measurements. Hosted CI or a
local smoke run does not replace dedicated-device or thermal certification.

Acceptance requires the measured dynamic curve, force/energy checks, host
conformance, realtime audit, and listening evidence together. A matched-RMS
comparison uses one gain per whole sequence so that the dynamic curve remains
audible. The basic and physical candidates have different modal and excitation
models, so that comparison does not isolate the causal effect of the hammer.

For the declared MIDI 1–127 sweep, retain the specification's `0.5 dB`
neighbor-level and `3%` neighbor-centroid limits under the report's fixed analysis
definitions. A loose regression sentinel is not a substitute for those limits.
Failure keeps the corresponding gate open; this ADR does not authorize a
threshold exception. The silence-to-positive-input transition and the continuous
sub-MIDI bridge are tested separately from the 127-step acoustic sweep.

Roll back or keep the candidate confined to the lab if force signs, energy
residuals, finite-state handling, event timing, runtime safety, or host parity
regress. Revisit the solver/rate choice for bandwidth or convergence failures,
or if measured cost fails the applicable deadline gate. Do not relax a
professional threshold to make this experiment pass. New listening approval
and broader evidence are required before promoting it to production playback.

## Primary research references and attribution boundary

1. S. Bilbao, A. Torin, V. Chatziioannou, **Numerical Modeling of Collisions in
   Musical Instruments**, *Acta Acustica united with Acustica* 101(1), 155–173
   (2015), [DOI 10.3813/AAA.918813](https://doi.org/10.3813/AAA.918813),
   [author preprint](https://arxiv.org/html/1405.2589v1).
   Sections 2.3–2.4 motivate potential-based discretization and nonnegative
   damping; section 4 treats hammer/string coupling; Appendix A discusses
   scalar-solve uniqueness. The paper explicitly separates stability from
   unaddressed nonlinear aliasing.
2. V. Chatziioannou, M. van Walstijn, **Energy Conserving Schemes for the
   Simulation of Musical Instrument Contact Dynamics**, *Journal of Sound and
   Vibration* 339, 262–279 (2015),
   [DOI 10.1016/j.jsv.2014.11.017](https://doi.org/10.1016/j.jsv.2014.11.017),
   [author preprint](https://arxiv.org/pdf/1501.01493).
   This provides the first-order Hamiltonian/discrete-gradient numerical
   framework. Its dispersion and aliasing discussion is relevant to the
   distinction between stability and accurate audio rendering.
3. M. Ducceschi, S. Bilbao, S. Willemsen, S. Serafin, **Linearly-implicit schemes
   for collisions in musical acoustics based on energy quadratisation**,
   *Journal of the Acoustical Society of America* (2021),
   [author paper](https://www.mdphys.org/PDF/jasa_2021.pdf),
   [author companion page](https://www.mdphys.org/collisions.html).
   This is an alternative route to bounded collision updates through auxiliary
   energy state; it is not the algorithm implemented here.

These references support numerical design choices. They do not supply our
candidate parameter values, prove the implemented clipping/backcheck policy,
validate its perceptual quality, or establish license/FTO clearance for a
commercial release. The secant damping, clipping argument, and bounded bracket
above are explicit project derivations. No reference implementation or
commercial piano data was copied into this experiment.
