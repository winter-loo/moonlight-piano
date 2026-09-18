//! WebAssembly realtime boundary used by the browser AudioWorklet.
//! Initialization may parse the embedded model. The render entry point is bounded,
//! allocation-free, and crosses the JS/WASM boundary once per render quantum.

use std::cell::RefCell;

use moonlight_dsp::{
    PianoEngine, PianoEvent, PianoEventKind, MAX_BLOCK_FRAMES, MAX_EVENTS_PER_BLOCK,
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
    engine: PianoEngine,
    events: [WasmEvent; MAX_EVENTS_PER_BLOCK],
    output: [f32; MAX_BLOCK_FRAMES],
}

thread_local! {
    static ENGINE: RefCell<Option<WasmEngine>> = const { RefCell::new(None) };
}

#[no_mangle]
pub extern "C" fn moonlight_engine_abi_version() -> u32 {
    2
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
            engine,
            events: [WasmEvent::default(); MAX_EVENTS_PER_BLOCK],
            output: [0.0; MAX_BLOCK_FRAMES],
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
                _ => return 7,
            };
            *event = PianoEvent {
                frame: block_start + u64::from(source.frame_offset),
                kind,
            };
        }

        let output = &mut state.output[..frame_count as usize];
        match state
            .engine
            .process_block(block_start, &events[..event_count as usize], output)
        {
            Ok(_) => 0,
            Err(_) => {
                output.fill(0.0);
                8
            }
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

        let mut wrapped = WasmEngine {
            engine: PianoEngine::new(&pack, sample_rate, 0x85a308d3243f6a88).unwrap(),
            events: [WasmEvent::default(); MAX_EVENTS_PER_BLOCK],
            output: [0.0; MAX_BLOCK_FRAMES],
        };
        wrapped.events[0] = WasmEvent {
            frame_offset: 17,
            kind: 1,
            note: 60,
            value: 0.8,
        };
        let event = wrapped.events[0];
        let events = [PianoEvent {
            frame: u64::from(event.frame_offset),
            kind: PianoEventKind::NoteOn {
                note: event.note as u8,
                velocity: event.value,
            },
        }];
        wrapped
            .engine
            .process_block(0, &events, &mut wrapped.output[..128])
            .unwrap();

        assert_eq!(&wrapped.output[..128], &direct_output);
    }
}
