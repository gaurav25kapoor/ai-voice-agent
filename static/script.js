let mediaRecorder;
let audioChunks = [];
let uploadQueue = [];
let isUploading = false;
let isRecording = false;

const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const audioPlayer = document.getElementById("audioPlayer");
const audioContainer = document.getElementById("audioContainer");
const errorMsg = document.getElementById("errorMsg");

// Session ID
const urlParams = new URLSearchParams(window.location.search);
let sessionId = urlParams.get("session_id");
if (!sessionId) {
    sessionId = crypto.randomUUID();
    urlParams.set("session_id", sessionId);
    window.history.replaceState({}, "", `${location.pathname}?${urlParams}`);
}

async function startRecording() {
    if (isRecording) return; // prevent double start
    isRecording = true;
    errorMsg.innerText = "";
    audioChunks = [];

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
        mediaRecorder.start();

        mediaRecorder.addEventListener("dataavailable", event => {
            if (event.data.size > 0) audioChunks.push(event.data);
        });

        mediaRecorder.addEventListener("error", e => {
            console.error("Recorder error:", e);
            stopRecording();
            errorMsg.innerText = "⚠ Recording error occurred.";
            playFallbackAudio();
        });

        startBtn.disabled = true;
        stopBtn.disabled = false;
    } catch (err) {
        console.error("Mic access error:", err);
        errorMsg.innerText = "⚠ Microphone access denied.";
        playFallbackAudio();
        isRecording = false;
    }
}

function playFallbackAudio() {
    const fallback = new SpeechSynthesisUtterance("I'm having trouble connecting right now.");
    speechSynthesis.speak(fallback);
}

function stopRecording() {
    if (!mediaRecorder || mediaRecorder.state === "inactive") return;
    mediaRecorder.stop();

    mediaRecorder.addEventListener("stop", () => {
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        const filename = `recording_${Date.now()}.webm`;
        uploadQueue.push({ blob: audioBlob, filename });
        processUploadQueue();

        startBtn.disabled = false;
        stopBtn.disabled = true;
        isRecording = false;
    });
}

async function processUploadQueue() {
    if (isUploading || uploadQueue.length === 0) return;

    isUploading = true;
    const { blob, filename } = uploadQueue.shift();

    const formData = new FormData();
    formData.append("file", blob, filename);

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout

        const response = await fetch(`/agent/chat/${sessionId}`, {
            method: "POST",
            body: formData,
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const data = await response.json();
        if (data.audio_file) {
            audioPlayer.src = `${data.audio_file}?t=${Date.now()}`;
            audioContainer.classList.remove("hidden");
            await audioPlayer.play();

            audioPlayer.onended = () => {
                startRecording(); // auto-continue recording
            };
        } else {
            throw new Error(data.error || "Unexpected server error");
        }
    } catch (err) {
        console.error("Upload error:", err);
        errorMsg.innerText = "⚠ " + (err.message || "Network error, please try again.");
        playFallbackAudio();
    }

    isUploading = false;
    processUploadQueue(); // continue next in queue
}

// Stop recording if user leaves the page
window.addEventListener("beforeunload", () => {
    if (isRecording) stopRecording();
});

startBtn.addEventListener("click", startRecording);
stopBtn.addEventListener("click", stopRecording);
