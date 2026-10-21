//! WebAssembly realtime boundary used by the browser AudioWorklet.
//! Initialization may parse the embedded model. The render entry point is bounded,
//! allocation-free, and crosses the JS/WASM boundary once per render quantum.

use std::cell::RefCell;

use moonlight_dsp::{
    BasicPianoEngine, PianoEngine, PianoEvent, PianoEventKind, MAX_BLOCK_FRAMES,
    MAX_EVENTS_PER_BLOCK,
};
use moonlight_model::parse_model_pack;

const C4_MODEL: &str = include_str!("../../../fixtures/physical-c4/minimal-c4.mlpiano");

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct WasmEvent {
    frame_offset: u32,
    kind: u32,
    note: u32,
    value: f32,
}

struct WasmEngine {
    engine: Core,
    active_voices: u32,
    // ABI 5: sixteen f64 slots, refreshed by the same block render call.
    // The final slot is reserved. Basic mode exposes zeroed diagnostics.
    hammer_diagnostics: [f64; 16],
    events: [WasmEvent; MAX_EVENTS_PER_BLOCK],
    output: [f32; MAX_BLOCK_FRAMES * 2],
}

enum Core {
    C4(Box<PianoEngine>),
    Basic(Box<BasicPianoEngine>),
}

thread_local! {
    static ENGINE: RefCell<Option<WasmEngine>> = const { RefCell::new(None) };
}

#[no_mangle]
pub extern "C" fn moonlight_engine_abi_version() -> u32 {
    5
}

#[no_mangle]
pub extern "C" fn moonlight_engine_init(sample_rate_hz: u32, seed_lo: u32, seed_hi: u32) -> i32 {
    let seed = (u64::from(seed_hi) << 32) | u64::from(seed_lo);
    let pack = match parse_model_pack(C4_MODEL, sample_rate_hz) {
        Ok(pack) => pack,
        Err(_) => return 1,
    };
    let engine = match PianoEngine::new(&pack, sample_rate_hz, seed) {
        Ok(engine) => engine,
        Err(_) => return 2,
    };
    ENGINE.with(|slot| {
        *slot.borrow_mut() = Some(WasmEngine {
            engine: Core::C4(Box::new(engine)),
            active_voices: 0,
            hammer_diagnostics: [0.0; 16],
            events: [WasmEvent::default(); MAX_EVENTS_PER_BLOCK],
            output: [0.0; MAX_BLOCK_FRAMES * 2],
        });
    });
    0
}

#[no_mangle]
pub extern "C" fn moonlight_basic_init(sample_rate_hz: u32) -> i32 {
    let engine = match BasicPianoEngine::new(sample_rate_hz) {
        Ok(engine) => engine,
        Err(_) => return 2,
    };
    ENGINE.with(|slot| {
        *slot.borrow_mut() = Some(WasmEngine {
            engine: Core::Basic(Box::new(engine)),
            active_voices: 0,
            hammer_diagnostics: [0.0; 16],
            events: [WasmEvent::default(); MAX_EVENTS_PER_BLOCK],
            output: [0.0; MAX_BLOCK_FRAMES * 2],
        });
    });
    0
}

#[no_mangle]
pub extern "C" fn moonlight_event_buffer_ptr() -> *mut WasmEvent {
    ENGINE.with(|slot| {
        let mut slot = slot.borrow_mut();
        slot.as_mut()
            .map_or(std::ptr::null_mut(), |state| state.events.as_mut_ptr())
    })
}

#[no_mangle]
pub extern "C" fn moonlight_output_buffer_ptr() -> *const f32 {
    ENGINE.with(|slot| {
        let slot = slot.borrow();
        slot.as_ref()
            .map_or(std::ptr::null(), |state| state.output.as_ptr())
    })
}

#[no_mangle]
pub extern "C" fn moonlight_active_voices_ptr() -> *const u32 {
    ENGINE.with(|slot| {
        let slot = slot.borrow();
        slot.as_ref()
            .map_or(std::ptr::null(), |state| &state.active_voices)
    })
}

/// Read-only shared diagnostic block. Obtain once after initialization; reading
/// it does not require another JS/WASM call in the realtime render path.
#[no_mangle]
pub extern "C" fn moonlight_hammer_diagnostics_ptr() -> *const f64 {
    ENGINE.with(|slot| {
        let slot = slot.borrow();
        slot.as_ref()
            .map_or(std::ptr::null(), |state| state.hammer_diagnostics.as_ptr())
    })
}

#[no_mangle]
pub extern "C" fn moonlight_process_block(
    block_start_lo: u32,
    block_start_hi: u32,
    frame_count: u32,
    event_count: u32,
) -> i32 {
    if frame_count == 0 || frame_count as usize > MAX_BLOCK_FRAMES {
        return 3;
    }
    if event_count as usize > MAX_EVENTS_PER_BLOCK {
        return 4;
    }
    let block_start = (u64::from(block_start_hi) << 32) | u64::from(block_start_lo);

    ENGINE.with(|slot| {
        let mut slot = slot.borrow_mut();
        let Some(state) = slot.as_mut() else {
            return 5;
        };

        let mut events = [PianoEvent {
            frame: 0,
            kind: PianoEventKind::Reset,
        }; MAX_EVENTS_PER_BLOCK];

        for (source, event) in state
            .events
            .iter()
            .copied()
            .zip(events.iter_mut())
            .take(event_count as usize)
        {
            if source.frame_offset >= frame_count {
                return 6;
            }
            if matches!(source.kind, 1 | 2) && source.note > 127 {
                return 6;
            }
            let Some(frame) = block_start.checked_add(u64::from(source.frame_offset)) else {
                return 6;
            };
            let kind = match source.kind {
                1 => PianoEventKind::NoteOn {
                    note: source.note as u8,
                    velocity: source.value,
                },
                2 => PianoEventKind::NoteOff {
                    note: source.note as u8,
                    release_velocity: source.value,
                },
                3 => PianoEventKind::Reset,
                4 => PianoEventKind::Sustain {
                    position: source.value,
                },
                _ => return 7,
            };
            *event = PianoEvent { frame, kind };
        }

        let (left, remaining) = state.output.split_at_mut(MAX_BLOCK_FRAMES);
        let output = &mut left[..frame_count as usize];
        let okay = match &mut state.engine {
            Core::C4(engine) => engine
                .process_block(block_start, &events[..event_count as usize], output)
                .is_ok(),
            Core::Basic(engine) => engine
                .process_stereo_block(
                    block_start,
                    &events[..event_count as usize],
                    output,
                    &mut remaining[..frame_count as usize],
                )
                .is_ok(),
        };
        state.active_voices = match &state.engine {
            Core::C4(engine) => engine.state_counts().active_strings as u32,
            Core::Basic(engine) => engine.active_voices() as u32,
        };
        if let Core::C4(engine) = &state.engine {
            let hammer = engine.hammer_diagnostics();
            state.hammer_diagnostics = [
                hammer.force_newtons,
                hammer.peak_force_newtons,
                hammer.compression_meters,
                hammer.peak_compression_meters,
                hammer.initial_velocity_mps,
                hammer.hammer_velocity_mps,
                hammer.contact_seconds,
                hammer.hammer_energy_joules,
                hammer.string_energy_joules,
                hammer.total_energy_joules,
                hammer.dissipated_energy_joules,
                hammer.input_energy_joules,
                hammer.max_energy_error_joules,
                f64::from(hammer.contact_count),
                if hammer.in_contact { 1.0 } else { 0.0 },
                0.0,
            ];
        }
        if okay {
            0
        } else {
            output.fill(0.0);
            remaining[..frame_count as usize].fill(0.0);
            8
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use moonlight_model::parse_model_pack;

    #[test]
    fn wasm_block_path_matches_direct_core_exactly() {
        let sample_rate = 48_000;
        let pack = parse_model_pack(C4_MODEL, sample_rate).unwrap();
        let mut direct = PianoEngine::new(&pack, sample_rate, 0x85a308d3243f6a88).unwrap();
        let mut direct_output = [0.0_f32; 128];
        direct
            .process_block(
                0,
                &[PianoEvent {
                    frame: 17,
                    kind: PianoEventKind::NoteOn {
                        note: 60,
                        velocity: 0.8,
                    },
                }],
                &mut direct_output,
            )
            .unwrap();

        assert_eq!(
            moonlight_engine_init(sample_rate, 0x243f6a88, 0x85a308d3),
            0
        );
        assert_eq!(moonlight_engine_abi_version(), 5);
        assert!(!moonlight_hammer_diagnostics_ptr().is_null());
        ENGINE.with(|slot| {
            slot.borrow_mut().as_mut().unwrap().events[0] = WasmEvent {
                frame_offset: 17,
                kind: 1,
                note: 60,
                value: 0.8,
            };
        });
        assert_eq!(moonlight_process_block(0, 0, 128, 1), 0);
        ENGINE.with(|slot| {
            let state = slot.borrow();
            let state = state.as_ref().unwrap();
            assert_eq!(&state.output[..128], &direct_output);
            assert_eq!(
                state.hammer_diagnostics[1],
                direct.hammer_diagnostics().peak_force_newtons
            );
            assert_eq!(
                state.hammer_diagnostics[6],
                direct.hammer_diagnostics().contact_seconds
            );
            assert!(state.hammer_diagnostics[11] > 0.0);
        });
    }

    #[test]
    fn malformed_wide_note_cannot_wrap_to_c4_in_the_abi() {
        assert_eq!(moonlight_engine_init(48_000, 1, 0), 0);
        ENGINE.with(|slot| {
            slot.borrow_mut().as_mut().unwrap().events[0] = WasmEvent {
                frame_offset: 0,
                kind: 1,
                note: 316,
                value: 0.8,
            };
        });
        assert_ne!(moonlight_process_block(0, 0, 128, 1), 0);
        ENGINE.with(|slot| {
            assert!(slot
                .borrow()
                .as_ref()
                .unwrap()
                .hammer_diagnostics
                .iter()
                .all(|value| *value == 0.0));
        });
    }

    #[test]
    fn reset_clears_diagnostics_in_the_same_render_call() {
        assert_eq!(moonlight_engine_init(48_000, 1, 0), 0);
        ENGINE.with(|slot| {
            slot.borrow_mut().as_mut().unwrap().events[0] = WasmEvent {
                frame_offset: 0,
                kind: 1,
                note: 60,
                value: 1.0,
            };
        });
        assert_eq!(moonlight_process_block(0, 0, 128, 1), 0);
        ENGINE.with(|slot| {
            slot.borrow_mut().as_mut().unwrap().events[0].kind = 3;
        });
        assert_eq!(moonlight_process_block(128, 0, 128, 1), 0);
        ENGINE.with(|slot| {
            let state = slot.borrow();
            let state = state.as_ref().unwrap();
            assert!(state.hammer_diagnostics.iter().all(|value| *value == 0.0));
            assert!(state.output[..128].iter().all(|value| *value == 0.0));
        });
    }
}
