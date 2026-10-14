class MoonlightPhysicalC4Processor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.instance = null;
    this.exports = null;
    this.memory = null;
    this.eventView = null;
    this.outputView = null;
    this.eventPtr = 0;
    this.outputPtr = 0;
    this.activeVoicePtr = 0;
    this.ready = false;
    this.failed = false;
    this.queueCapacity = 256;
    this.queueLength = 0;
    this.frames = new Float64Array(this.queueCapacity);
    this.kinds = new Uint8Array(this.queueCapacity);
    this.notes = new Uint8Array(this.queueCapacity);
    this.values = new Float32Array(this.queueCapacity);
    this.immediate = new Uint8Array(this.queueCapacity);
    this.sourceIds = new Array(this.queueCapacity).fill(null);
    // Source ownership follows sorted render events, never message dispatch.
    // Fixed slots bound work and avoid Map growth/allocation in process().
    this.sourceCapacity = 256;
    this.heldSourceIds = new Array(this.sourceCapacity).fill(null);
    this.heldNotes = new Uint8Array(this.sourceCapacity);
    this.pressed = new Uint16Array(128);
    this.underruns = 0;
    this.lateEvents = 0;
    this.telemetryCountdown = 0;
    this.lastBlockSize = 0;
    this.lastDeadlineRatio = 0;
    this.basic = options.processorOptions?.mode === "basic";
    this.overflowEvents = 0;

    this.port.onmessage = (event) => {
      const message = event.data;
      if (message.type === "event") this.enqueue(message.frame, message.kind, message.note, message.value, message.immediate === true, message.sourceId);
      else if (message.type === "reset") {
        // A stop cancels previously scheduled notes, including future ones.
        this.sourceIds.fill(null);
        this.queueLength = 0;
        this.enqueue(message.frame, 3, 60, 0);
      }
    };

    const bytes = options.processorOptions && options.processorOptions.wasmBytes;
    if (!(bytes instanceof ArrayBuffer)) {
      this.fail("WASM bytes were not provided to AudioWorklet.");
      return;
    }
    WebAssembly.instantiate(bytes, {}).then(({ instance }) => {
      this.instance = instance;
      this.exports = instance.exports;
      this.memory = instance.exports.memory;
      const status = this.basic
        ? this.exports.moonlight_basic_init(sampleRate)
        : this.exports.moonlight_engine_init(sampleRate, 0x243f6a88, 0x85a308d3);
      if (status !== 0) {
        this.fail(`Rust engine initialization failed with status ${status}.`);
        return;
      }
      this.eventPtr = this.exports.moonlight_event_buffer_ptr();
      this.outputPtr = this.exports.moonlight_output_buffer_ptr();
      this.activeVoicePtr = this.exports.moonlight_active_voices_ptr();
      this.eventView = new DataView(this.memory.buffer);
      this.outputView = new Float32Array(this.memory.buffer, this.outputPtr, 32768);
      this.ready = true;
      this.port.postMessage({ type: "ready", memoryBytes: this.memory.buffer.byteLength });
    }).catch((error) => this.fail(error instanceof Error ? error.message : String(error)));
  }

  enqueue(frame, kind, note, value, immediate = false, sourceId = null) {
    if (!Number.isSafeInteger(frame) || frame < 0) {
      this.lateEvents += 1;
      return;
    }
    if (this.queueLength >= this.queueCapacity) {
      this.overflowEvents += 1;
      if (kind === 1) return;
      // Never lose a release or reset: silence the instrument at the next
      // quantum when the host has filled the queue with unbounded future work.
      this.sourceIds.fill(null);
      this.queueLength = 0;
      frame = currentFrame;
      kind = 3;
    }
    let index = this.queueLength;
    while (index > 0 && this.frames[index - 1] > frame) {
      this.frames[index] = this.frames[index - 1];
      this.kinds[index] = this.kinds[index - 1];
      this.notes[index] = this.notes[index - 1];
      this.values[index] = this.values[index - 1];
      this.immediate[index] = this.immediate[index - 1];
      this.sourceIds[index] = this.sourceIds[index - 1];
      index -= 1;
    }
    this.frames[index] = frame;
    this.kinds[index] = kind;
    this.notes[index] = note;
    this.values[index] = value;
    this.immediate[index] = immediate ? 1 : 0;
    this.sourceIds[index] = sourceId;
    this.queueLength += 1;
  }

  process(_inputs, outputs) {
    const channel = outputs[0] && outputs[0][0];
    const right = this.basic && outputs[0] && outputs[0][1];
    if (!channel) return true;
    const frames = channel.length;
    this.lastBlockSize = frames;
    if (!this.ready || !this.exports || !this.eventView || !this.outputView) {
      channel.fill(0);
      if (right) right.fill(0);
      return !this.failed;
    }

    // Include bounded JS event/ownership work in the render deadline metric.
    const start = globalThis.performance ? performance.now() : 0;
    const blockStart = currentFrame;
    const blockEnd = blockStart + frames;
    let eventCount = 0;
    let consumed = 0;
    while (consumed < this.queueLength && this.frames[consumed] < blockEnd) {
      let frame = this.frames[consumed];
      if (frame < blockStart) {
        this.lateEvents += 1;
        if (this.kinds[consumed] === 1 && !this.immediate[consumed]) {
          consumed += 1;
          continue;
        }
        // Deliver NOW inputs and safety controls even if message delivery was late.
        frame = blockStart;
      }
      const kind = this.kinds[consumed];
      const note = this.notes[consumed];
      const sourceId = this.sourceIds[consumed];
      if (this.basic && kind === 3) {
        this.heldSourceIds.fill(null);
        this.pressed.fill(0);
      } else if (this.basic && (kind === 1 || kind === 2) && sourceId !== null) {
        let held = -1;
        let available = -1;
        for (let slot = 0; slot < this.sourceCapacity; slot += 1) {
          if (this.heldSourceIds[slot] === sourceId) {
            held = slot;
            break;
          }
          if (available < 0 && this.heldSourceIds[slot] === null) available = slot;
        }
        if (kind === 1) {
          if (held >= 0 || available < 0) {
            if (held < 0) this.overflowEvents += 1;
            consumed += 1;
            continue;
          }
          this.heldSourceIds[available] = sourceId;
          this.heldNotes[available] = note;
          this.pressed[note] += 1;
        } else {
          if (held < 0 || this.heldNotes[held] !== note) {
            consumed += 1;
            continue;
          }
          this.heldSourceIds[held] = null;
          this.pressed[note] -= 1;
          if (this.pressed[note] > 0) {
            consumed += 1;
            continue;
          }
        }
      }
      const base = this.eventPtr + eventCount * 16;
      this.eventView.setUint32(base, frame - blockStart, true);
      this.eventView.setUint32(base + 4, this.kinds[consumed], true);
      this.eventView.setUint32(base + 8, this.notes[consumed], true);
      this.eventView.setFloat32(base + 12, this.values[consumed], true);
      eventCount += 1;
      consumed += 1;
    }
    if (consumed > 0) {
      this.frames.copyWithin(0, consumed, this.queueLength);
      this.kinds.copyWithin(0, consumed, this.queueLength);
      this.notes.copyWithin(0, consumed, this.queueLength);
      this.values.copyWithin(0, consumed, this.queueLength);
      this.immediate.copyWithin(0, consumed, this.queueLength);
      this.sourceIds.copyWithin(0, consumed, this.queueLength);
      this.sourceIds.fill(null, this.queueLength - consumed, this.queueLength);
      this.queueLength -= consumed;
    }

    const lo = blockStart >>> 0;
    const hi = Math.floor(blockStart / 4294967296) >>> 0;
    const status = this.exports.moonlight_process_block(lo, hi, frames, eventCount);
    const elapsed = globalThis.performance ? performance.now() - start : 0;
    const deadlineMs = frames * 1000 / sampleRate;
    this.lastDeadlineRatio = deadlineMs > 0 ? elapsed / deadlineMs : 0;
    if (this.lastDeadlineRatio >= 1) this.underruns += 1;

    if (status !== 0) {
      channel.fill(0);
      if (right) right.fill(0);
      this.fail(`Rust block render failed with status ${status}.`);
      return false;
    }
    for (let index = 0; index < frames; index += 1) {
      channel[index] = this.outputView[index];
      if (right) right[index] = this.outputView[16384 + index];
    }

    this.telemetryCountdown += 1;
    if (this.telemetryCountdown >= 128) {
      this.telemetryCountdown = 0;
      this.port.postMessage({
        type: "telemetry",
        blockSize: frames,
        deadlineRatio: this.lastDeadlineRatio,
        memoryBytes: this.memory.buffer.byteLength,
        underruns: this.underruns,
        lateEvents: this.lateEvents,
        overflowEvents: this.overflowEvents,
        activeVoices: this.eventView.getUint32(this.activeVoicePtr, true),
      });
    }
    return true;
  }

  fail(message) {
    if (this.failed) return;
    this.failed = true;
    this.ready = false;
    this.port.postMessage({ type: "error", message });
  }
}

registerProcessor("moonlight-physical-c4", MoonlightPhysicalC4Processor);
registerProcessor("moonlight-basic-piano", MoonlightPhysicalC4Processor);
