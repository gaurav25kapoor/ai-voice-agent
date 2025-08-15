import os
import time
import logging
import shutil
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from google import genai
import requests

# ------------------------------------------------------------------------------
# Load Environment Variables
# ------------------------------------------------------------------------------
load_dotenv()

MURF_API_KEY = os.getenv("MURF_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

REQUEST_TIMEOUT = 60  # seconds for outbound HTTP requests
ASSEMBLYAI_BASE = "https://api.assemblyai.com/v2"
MURF_TTS_URL = "https://api.murf.ai/v1/speech/generate"

# ------------------------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("voice-agent")

# ------------------------------------------------------------------------------
# FastAPI App & Middleware
# ------------------------------------------------------------------------------
app = FastAPI(title="AI Voice Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Uploads
app.mount("/static", StaticFiles(directory="static"), name="static")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

templates = Jinja2Templates(directory="templates")

# ------------------------------------------------------------------------------
# In-Memory Chat History: {session_id: [{"role": ..., "content": ...}, ...]}
# ------------------------------------------------------------------------------
chat_histories = {}

# ------------------------------------------------------------------------------
# Global Error Handler
# ------------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled error for %s", request.url, exc_info=True)
    return JSONResponse(status_code=500, content={"error": str(exc)})

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.get("/")
def home(request: Request):
    """Serve the main UI."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/llm/query")
async def llm_query(file: UploadFile = File(...)):
    """
    Single-turn conversation:
    1. Audio → STT
    2. LLM → text
    3. TTS → audio file
    """
    logger.info("POST /llm/query | filename=%s", file.filename)
    try:
        file_path = save_uploaded_file(file)
        transcript = transcribe_audio(file_path)
        llm_response = get_gemini_response(transcript)
        murf_audio_path = text_to_speech_murf(llm_response)
        return JSONResponse({"audio_file": f"/uploads/{murf_audio_path.name}"})

    except Exception as e:
        logger.error("Error in /llm/query: %s", e, exc_info=True)
        return fallback_audio(str(e))


@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    """
    Multi-turn conversation with memory:
    1. Audio → STT
    2. Append to session chat history
    3. LLM (with history) → text
    4. Append assistant reply
    5. TTS → audio file
    """
    logger.info("POST /agent/chat/%s | filename=%s", session_id, file.filename)
    try:
        file_path = save_uploaded_file(file)
        transcript = transcribe_audio(file_path)

        chat_histories.setdefault(session_id, [])
        chat_histories[session_id].append({"role": "user", "content": transcript})

        full_prompt = build_full_prompt(chat_histories[session_id])
        llm_response = get_gemini_response(full_prompt)

        chat_histories[session_id].append({"role": "assistant", "content": llm_response})
        murf_audio_path = text_to_speech_murf(llm_response)

        return JSONResponse({
            "audio_file": f"/uploads/{murf_audio_path.name}",
            "history": chat_histories[session_id],
        })

    except Exception as e:
        logger.error("Error in /agent/chat: %s", e, exc_info=True)
        return fallback_audio(str(e), session_id)

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def save_uploaded_file(file: UploadFile) -> Path:
    """Save uploaded file to /uploads."""
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    logger.info("Saved upload to %s", file_path)
    return file_path


def build_full_prompt(history):
    """Convert chat history into a single text prompt."""
    return "\n".join(
        f"{'User' if msg['role']=='user' else 'Assistant'}: {msg['content']}"
        for msg in history
    )


def transcribe_audio(file_path: Path) -> str:
    """Transcribe audio to text using AssemblyAI."""
    if not ASSEMBLYAI_API_KEY:
        raise Exception("Missing AssemblyAI API key")

    headers = {"authorization": ASSEMBLYAI_API_KEY}

    # Upload audio
    with open(file_path, "rb") as f:
        resp = requests.post(f"{ASSEMBLYAI_BASE}/upload", headers=headers, data=f, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    audio_url = resp.json().get("upload_url")
    if not audio_url:
        raise Exception("No upload URL from AssemblyAI")

    # Create transcript
    resp = requests.post(
        f"{ASSEMBLYAI_BASE}/transcript",
        json={"audio_url": audio_url},
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    transcript_id = resp.json().get("id")
    if not transcript_id:
        raise Exception("No transcript ID from AssemblyAI")

    # Poll until complete
    while True:
        polling = requests.get(f"{ASSEMBLYAI_BASE}/transcript/{transcript_id}", headers=headers, timeout=REQUEST_TIMEOUT)
        polling.raise_for_status()
        data = polling.json()
        if data.get("status") == "completed":
            return data.get("text", "")
        if data.get("status") == "error":
            raise Exception("Transcription failed")
        time.sleep(1)


def get_gemini_response(prompt: str) -> str:
    """Send prompt to Google Gemini and return response text."""
    if not GEMINI_API_KEY:
        raise Exception("Missing Gemini API key")

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    text = getattr(response, "text", None)
    if not text:
        raise Exception("Empty response from Gemini")
    return text.strip()


def text_to_speech_murf(text: str) -> Path:
    """Convert text to speech using Murf API and save unique file in /uploads."""
    if not MURF_API_KEY:
        raise Exception("Missing Murf API key")

    if len(text) > 3000:
        text = text[:3000]

    headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
    payload = {"voiceId": "en-IN-arohi", "text": text, "format": "MP3"}

    resp = requests.post(MURF_TTS_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise Exception(f"Murf API Error: {resp.text}")

    audio_url = resp.json().get("audioFile")
    if not audio_url:
        raise Exception("No audio file URL from Murf")

    # Unique filename: response_<timestamp>.mp3
    audio_path = UPLOAD_DIR / f"response_{int(time.time())}.mp3"
    with requests.get(audio_url, stream=True, timeout=REQUEST_TIMEOUT) as r:
        r.raise_for_status()
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)

    return audio_path


def fallback_audio(error_message: str, session_id: str = None):
    """Generate fallback audio message."""
    logger.warning("Fallback audio | session=%s | error=%s", session_id, error_message)
    try:
        fallback_text = "I'm having trouble connecting right now."
        audio_path = text_to_speech_murf(fallback_text)
        if session_id:
            chat_histories.setdefault(session_id, [])
            chat_histories[session_id].append({"role": "assistant", "content": fallback_text})

        return JSONResponse({
            "audio_file": f"/uploads/{audio_path.name}",
            "error": error_message,
            "history": chat_histories.get(session_id),
        }, status_code=500)

    except Exception as inner:
        logger.error("Fallback TTS failed: %s", inner, exc_info=True)
        return JSONResponse({"error": error_message}, status_code=500)
