//! Stable native-host boundary. Platform callbacks are added by later tickets.

pub use moonlight_dsp::{PianoEngine, PianoEvent, PianoEventKind};
pub use moonlight_model::{ModelPack, MODEL_SCHEMA_VERSION};

#[no_mangle]
pub extern "C" fn moonlight_engine_abi_version() -> u32 {
    1
}
