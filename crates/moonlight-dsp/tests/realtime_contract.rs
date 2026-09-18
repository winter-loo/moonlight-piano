//! Exercise the public render seam, not internal modal implementation details.
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::hint::black_box;

use moonlight_dsp::{PianoEngine, PianoEvent, PianoEventKind};
use moonlight_model::parse_model_pack;

struct ObservedAllocator;
thread_local! {
    static WATCH: Cell<bool> = const { Cell::new(false) };
    static ALLOCS: Cell<usize> = const { Cell::new(0) };
    static FREES: Cell<usize> = const { Cell::new(0) };
}

fn record(counter: &'static std::thread::LocalKey<Cell<usize>>) {
    if WATCH.try_with(Cell::get).unwrap_or(false) {
        let _ = counter.try_with(|value| value.set(value.get() + 1));
    }
}

// SAFETY: all operations forward their original pointer/layout to System;
// observation uses initialized, non-allocating TLS and never panics or unwinds.
unsafe impl GlobalAlloc for ObservedAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        record(&ALLOCS);
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        record(&ALLOCS);
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        record(&FREES);
        unsafe { System.dealloc(pointer, layout) }
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        record(&ALLOCS);
        record(&FREES);
        unsafe { System.realloc(pointer, layout, size) }
    }
}

#[global_allocator]
static ALLOCATOR: ObservedAllocator = ObservedAllocator;

struct Watch;
impl Watch {
    fn start() -> Self {
        ALLOCS.with(|value| value.set(0));
        FREES.with(|value| value.set(0));
        WATCH.with(|value| value.set(true));
        Self
    }
    fn finish(self) -> (usize, usize) {
        drop(self);
        (ALLOCS.with(Cell::get), FREES.with(Cell::get))
    }
}
impl Drop for Watch {
    fn drop(&mut self) {
        WATCH.with(|value| value.set(false));
    }
}

fn engine(rate: u32) -> PianoEngine {
    let model = include_str!("../../../fixtures/physical-c4/minimal-c4.mlpiano");
    PianoEngine::new(&parse_model_pack(model, rate).unwrap(), rate, 17).unwrap()
}

fn note(frame: u64) -> PianoEvent {
    PianoEvent {
        frame,
        kind: PianoEventKind::NoteOn {
            note: 60,
            velocity: 0.4,
        },
    }
}

#[test]
fn observer_detects_allocation_and_deallocation_negative_control() {
    let layout = Layout::from_size_align(128, 8).unwrap();
    let watch = Watch::start();
    // SAFETY: nonzero valid layout; free only the allocation returned for it.
    unsafe {
        let pointer = std::alloc::alloc(black_box(layout));
        if !pointer.is_null() {
            pointer.write_volatile(42);
            std::alloc::dealloc(black_box(pointer), layout);
        }
    }
    let counts = watch.finish();
    assert!(counts.0 > 0 && counts.1 > 0, "observer did not see control");
}

#[test]
fn successful_and_rejected_renders_and_reset_do_not_allocate_or_free() {
    for rate in [44_100, 48_000] {
        let mut engine = engine(rate);
        let mut output = [0.0; 512];
        let watch = Watch::start();
        let first = engine.process_block(0, &[note(0)], &mut output);
        let tail = engine.process_block(512, &[], &mut output);
        let invalid = engine.process_block(1024, &[note(0)], &mut output);
        engine.reset();
        let counts = watch.finish();
        assert!(first.is_ok() && tail.is_ok() && invalid.is_err());
        assert_eq!(counts, (0, 0));
    }
}

#[test]
fn event_flood_is_rejected_before_rendering() {
    let mut engine = engine(48_000);
    let events = [note(0); 257];
    let mut output = [0.0; 128];
    assert!(engine.process_block(0, &events, &mut output).is_err());
    assert!(
        !engine.key_down(),
        "rejection must not apply partial events"
    );
}

#[test]
fn oversized_host_buffer_is_rejected() {
    let mut engine = engine(48_000);
    let mut output = vec![0.0; 16_385];
    assert!(engine.process_block(0, &[], &mut output).is_err());
}

#[test]
fn block_partition_does_not_change_pcm_or_event_timing() {
    let events = [note(43), note(317)];
    let mut whole = [0.0; 1024];
    engine(48_000)
        .process_block(0, &events, &mut whole)
        .unwrap();
    for size in [1, 64, 128, 256, 512] {
        let mut split_engine = engine(48_000);
        let mut split = [0.0; 1024];
        for (block, output) in split.chunks_mut(size).enumerate() {
            let start = (block * size) as u64;
            let end = start + output.len() as u64;
            let first = events.partition_point(|event| event.frame < start);
            let last = events.partition_point(|event| event.frame < end);
            split_engine
                .process_block(start, &events[first..last], output)
                .unwrap();
        }
        assert_eq!(whole, split);
    }
}
