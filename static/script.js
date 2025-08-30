document.addEventListener("DOMContentLoaded", () => {
  let ws = null;
  let audioContext = null;
  let source = null;
  let processor = null;
  let mediaStream = null;

  let playQueue = [];
  let playheadTime = 0;
  let wavHeaderSeen = false;
  let userBubble = null;

  const OUTPUT_RATE = 44100;
  const AAI_SEND_RATE = 16000;

  // --- DOM Elements ---
  const chatBox = document.getElementById("chatBox");
  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const audioEl = document.getElementById("audioPlayer");
  const personaSelect = document.getElementById("personaSelect");
  const skillSelect = document.getElementById("skillSelect");

  // --- Reset session on refresh ---
  const sessionId = `session_${Date.now()}`;

  // --- Utils ---
  function downsampleBuffer(buffer, inRate, outRate) {
    if (outRate === inRate) return buffer;
    const ratio = inRate / outRate;
    const newLen = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLen);
    let offsetResult = 0, offsetBuffer = 0;
    while (offsetResult < newLen) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
      let accum = 0, count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i]; count++;
      }
      result[offsetResult++] = count ? accum / count : 0;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }

  function floatTo16BitPCM(float32) {
    const buffer = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32.length; i++) {
      let s = Math.max(-1, Math.min(1, float32[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buffer;
  }

  function base64ToUint8Array(b64) {
    try {
      const bin = atob(b64);
      const out = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
      return out;
    } catch {
      return new Uint8Array(0);
    }
  }

  // --- UI ---
  function addMessage(role, text) {
    if (!text) return;
    const wrapper = document.createElement("div");
    wrapper.classList.add("flex", "w-full", "mb-2");
    if (role === "user") {
      wrapper.innerHTML = `
        <div class="ml-auto max-w-[70%] bg-blue-600 text-white rounded-2xl px-4 py-2 shadow user-bubble">
          ${text}
        </div>
      `;
      userBubble = wrapper.querySelector(".user-bubble");
    } else {
      wrapper.innerHTML = `
        <div class="mr-auto max-w-[70%] bg-gray-200 text-gray-800 rounded-2xl px-4 py-2 shadow">
          ${text}
        </div>
      `;
    }
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
  function updateUserBubble(text) { if (userBubble) userBubble.textContent = text; }

  function wavChunkToFloat32(b64) {
    const bytes = base64ToUint8Array(b64);
    if (!bytes.length) return new Float32Array(0);
    let pcmU8;
    if (!wavHeaderSeen && bytes.length >= 44) {
      wavHeaderSeen = true; pcmU8 = bytes.subarray(44);
    } else if (wavHeaderSeen) pcmU8 = bytes;
    else return new Float32Array(0);
    const view = new DataView(pcmU8.buffer, pcmU8.byteOffset, pcmU8.byteLength);
    const samples = pcmU8.byteLength >> 1;
    const f32 = new Float32Array(samples);
    for (let i = 0; i < samples; i++) f32[i] = view.getInt16(i * 2, true) / 32768;
    return f32;
  }

  function schedulePlayback() {
    if (!audioContext) return;
    if (audioContext.state === "suspended") audioContext.resume();
    const now = audioContext.currentTime, LOOKAHEAD = 0.05;
    while (playQueue.length > 0) {
      const chunk = playQueue.shift();
      if (!chunk.length) continue;
      const buf = audioContext.createBuffer(1, chunk.length, OUTPUT_RATE);
      buf.copyToChannel(chunk, 0);
      const src = audioContext.createBufferSource();
      src.buffer = buf; src.connect(audioContext.destination);
      if (playheadTime < now + LOOKAHEAD) playheadTime = now + LOOKAHEAD;
      src.start(playheadTime);
      playheadTime += chunk.length / OUTPUT_RATE;
    }
  }

  async function startSession() {
    playQueue = []; wavHeaderSeen = false; playheadTime = 0; userBubble = null;
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: OUTPUT_RATE });
    await audioContext.resume();

    const persona = personaSelect.value;
    const skill = skillSelect.value;

    const wsProto = window.location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(
      `${wsProto}://${window.location.host}/ws?session_id=${encodeURIComponent(sessionId)}&persona=${encodeURIComponent(persona)}&skill=${encodeURIComponent(skill)}`
    );
    ws.binaryType = "arraybuffer";

    ws.onopen = () => { startBtn.disabled = true; stopBtn.disabled = false; addMessage("user", "🎙️ Listening..."); };
    ws.onclose = () => { startBtn.disabled = false; stopBtn.disabled = true; };

    let lastAssistant = "";

    ws.onmessage = async (evt) => {
      if (typeof evt.data !== "string") return;
      try {
        const msg = JSON.parse(evt.data);
        if (msg.role === "assistant" && msg.text) {
          const t = (msg.text || "").trim();
          if (t && t !== lastAssistant) {
            addMessage("assistant", t);
            lastAssistant = t;
          }
          return;
        }
        switch (msg.event) {
          case "turn_end": updateUserBubble(msg.text || ""); break;
          case "tts_begin": playQueue = []; wavHeaderSeen = false; playheadTime = audioContext.currentTime + 0.05; break;
          case "tts_chunk": { const f32 = wavChunkToFloat32(msg.audio_b64 || ""); if (f32.length) { playQueue.push(f32); schedulePlayback(); } break; }
          case "tts_done": audioEl.play().catch(() => {}); break;
        }
      } catch (e) { console.warn("WS parse error", e); }
    };

    try { mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { console.error("Mic access denied"); return; }

    source = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const input = e.inputBuffer.getChannelData(0);
      const downsampled = downsampleBuffer(input, audioContext.sampleRate, AAI_SEND_RATE);
      if (!downsampled.length) return;
      ws.send(floatTo16BitPCM(downsampled));
    };
    source.connect(processor); processor.connect(audioContext.destination);
  }

  function stopSession() {
    try { processor?.disconnect(); } catch {}
    try { source?.disconnect(); } catch {}
    try { ws?.close(); } catch {}
    try { mediaStream?.getTracks().forEach((t) => t.stop()); } catch {}
    try { audioContext?.close(); } catch {}
    startBtn.disabled = false; stopBtn.disabled = true; userBubble = null;
  }

  startBtn.addEventListener("click", startSession);
  stopBtn.addEventListener("click", stopSession);
  stopBtn.disabled = true;
  chatBox.innerHTML = "";
});
