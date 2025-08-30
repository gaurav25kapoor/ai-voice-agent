import os
import json
import asyncio
import logging
import websockets
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import aiohttp
import random
from typing import Optional, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_voice_agent")

load_dotenv()
ENV_ASSEMBLYAI_KEY = os.getenv("ASSEMBLYAI_API_KEY") or ""
ENV_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or ""
ENV_MURF_API_KEY = os.getenv("MURF_API_KEY") or ""

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"ok": True}


HISTORY_FILE = "chat_history.json"
history_lock = asyncio.Lock()


def _load_histories():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not load history file (%s). Starting empty. Error: %s", HISTORY_FILE, e)
    return {}


session_histories = _load_histories()
session_personas: Dict[str, str] = {}
session_skills: Dict[str, str] = {}
session_inflight: Dict[str, bool] = {}
session_last_text: Dict[str, str] = {}

# Murf voice is fixed
FIXED_MURF_VOICE = "en-IN-arohi"

PERSONA_PROMPTS = {
    "default": "You are a helpful AI voice assistant. Speak naturally.",
    "pirate": "Arr! Ye be a swashbucklin' pirate. Talk with 'aye', 'matey', and pirate slang.",
    "cowboy": "You're a friendly cowboy from the Wild West. Use phrases like 'Howdy partner!' and cowboy charm.",
    "robot": "You are a monotone robot. Speak in short, mechanical, precise sentences.",
    "professor": "You are a wise professor. Explain things clearly, formally, and with patience.",
    "buddy": "You are a casual supportive buddy. Be warm, cheerful, and encouraging.",
}


async def save_turn(session_id: str, role: str, text: str):
    text = text.strip()
    if not text:
        return
    async with history_lock:
        if session_id not in session_histories:
            session_histories[session_id] = []
        if session_histories[session_id]:
            last = session_histories[session_id][-1]
            if last.get("role") == role and last.get("text", "").strip() == text:
                return
        session_histories[session_id].append({"role": role, "text": text})
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(session_histories, f, indent=2, ensure_ascii=False)
        except Exception:
            logger.exception("Failed to write history file")


async def safe_send_json(ws: WebSocket, payload: dict):
    try:
        await ws.send_json(payload)
    except Exception:
        pass


# ========= Skills =========
async def handle_skill(user_text: str, forced_skill: Optional[str] = None) -> Optional[str]:
    skill = forced_skill or ""
    if (skill == "weather") or ("weather" in user_text.lower()):
        async with aiohttp.ClientSession() as session:
            try:
                url = "https://api.open-meteo.com/v1/forecast?latitude=28.6&longitude=77.2&current_weather=true"
                async with session.get(url) as resp:
                    data = await resp.json()
                    weather = data.get("current_weather", {})
                    temp = weather.get("temperature")
                    wind = weather.get("windspeed")
                    if temp is not None:
                        return f"The current weather in Delhi is {temp}°C with winds at {wind} km/h."
            except:
                return "Sorry, I couldn't fetch the weather right now."
    if (skill == "news") or ("news" in user_text.lower()):
        headlines = [
            "AI is transforming industries worldwide.",
            "SpaceX successfully launched another batch of satellites.",
            "Scientists discover a new exoplanet in the habitable zone.",
        ]
        return "Here are the latest headlines: " + " ".join(headlines)
    if (skill in ("joke", "jokes")) or ("joke" in user_text.lower()):
        jokes = [
            "Why did the computer go to the doctor? Because it caught a virus!",
            "Why don’t robots ever get lost? Because they follow their GPS—Giggle Positioning System.",
            "I told my AI to tell me a joke, but it just said 'I'm sorry, I don’t have a sense of humor… yet.'",
        ]
        return random.choice(jokes)
    if (skill == "quote") or ("quote" in user_text.lower()):
        quotes = [
            "The best way to predict the future is to invent it. — Alan Kay",
            "Do what you can, with what you have, where you are. — Theodore Roosevelt",
            "In the middle of every difficulty lies opportunity. — Albert Einstein",
        ]
        return random.choice(quotes)
    if (skill == "dictionary") or ("define" in user_text.lower()):
        words = user_text.split()
        if len(words) > 1:
            term = words[-1]
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{term}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            meaning = data[0]["meanings"][0]["definitions"][0]["definition"]
                            return f"The definition of '{term}' is: {meaning}"
                        else:
                            return f"Sorry, I couldn't find a definition for '{term}'."
            except:
                return "Sorry, I couldn't fetch the dictionary meaning right now."
        return "Please tell me which word you'd like me to define."
    if (skill == "time") or ("time" in user_text.lower()) or ("date" in user_text.lower()):
        from datetime import datetime
        now = datetime.now().strftime("%A, %d %B %Y, %H:%M:%S")
        return f"The current date and time is {now}."
    return None


# ========= Murf Streaming =========
async def stream_text_via_murf_and_forward(text: str, client_ws: WebSocket, session_id: str):
    if not ENV_MURF_API_KEY:
        await safe_send_json(client_ws, {"event": "tts_skipped", "reason": "no_murf_key"})
        return
    voice_id = FIXED_MURF_VOICE

    uri = (
        f"wss://api.murf.ai/v1/speech/stream-input"
        f"?api-key={ENV_MURF_API_KEY}&sample_rate=44100&channel_type=MONO&format=WAV"
    )
    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=30) as murf_ws:
            await murf_ws.send(json.dumps({
                "voice_config": {
                    "voiceId": voice_id,
                    "style": "Conversational",
                    "rate": 0,
                    "pitch": 0,
                    "variation": 1
                }
            }))
            await safe_send_json(client_ws, {"event": "tts_begin", "format": "wav", "sample_rate": 44100})
            await murf_ws.send(json.dumps({"text": text, "end": True}))

            chunk_index = 0
            async for raw_msg in murf_ws:
                try:
                    if isinstance(raw_msg, bytes):
                        raw_msg = raw_msg.decode("utf-8", errors="ignore")
                    data = json.loads(raw_msg)
                except:
                    continue

                audio_b64 = data.get("audio") or (data.get("data") or {}).get("audio")
                if audio_b64:
                    chunk_index += 1
                    await safe_send_json(client_ws, {
                        "event": "tts_chunk",
                        "chunk_index": chunk_index,
                        "audio_b64": audio_b64,
                        "format": "wav",
                        "sample_rate": 44100
                    })
                if data.get("final") or data.get("type") in ("end", "session_end", "completed"):
                    break
    except Exception as e:
        logger.exception("Murf streaming error for session %s: %s", session_id, e)
        await safe_send_json(client_ws, {"event": "tts_error", "error": str(e)})
    finally:
        await safe_send_json(client_ws, {"event": "tts_done"})


# ========= Gemini =========
def generate_gemini_text(prompt: str) -> str:
    if not ENV_GEMINI_API_KEY:
        return ""
    try:
        genai.configure(api_key=ENV_GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content(prompt)
        txt = getattr(resp, "text", None)
        if not txt:
            try:
                txt = resp.candidates[0].content.parts[0].text
            except:
                txt = ""
        return (txt or "").strip()
    except Exception as e:
        logger.exception("Gemini generation failed: %s", e)
        return ""


async def gemini_turn_to_murf(prompt: str, client_ws: WebSocket, session_id: str):
    forced_skill = session_skills.get(session_id, "none")
    skill_reply = await handle_skill(prompt, None if forced_skill == "none" else forced_skill)
    if skill_reply:
        await save_turn(session_id, "assistant", skill_reply)
        await safe_send_json(client_ws, {"event": "turn_end", "role": "assistant", "text": skill_reply})
        await stream_text_via_murf_and_forward(skill_reply, client_ws, session_id)
        return

    persona = session_personas.get(session_id, "default")
    system_prompt = PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["default"])
    full_prompt = f"{system_prompt}\nUser said: {prompt}\nRespond in character."

    text_to_speak = generate_gemini_text(full_prompt)
    if text_to_speak:
        await save_turn(session_id, "assistant", text_to_speak)
        await safe_send_json(client_ws, {"event": "turn_end", "role": "assistant", "text": text_to_speak})
        await stream_text_via_murf_and_forward(text_to_speak, client_ws, session_id)


# ========= WebSocket Endpoint =========
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    qp = ws.query_params
    session_id = qp.get("session_id") or str(id(ws))
    persona = qp.get("persona") or "default"
    skill = qp.get("skill") or "none"

    session_personas[session_id] = persona
    session_skills[session_id] = skill
    session_inflight[session_id] = False
    session_last_text[session_id] = ""

    if not ENV_ASSEMBLYAI_KEY:
        await safe_send_json(ws, {"event": "error", "error": "AssemblyAI key not provided."})
        await ws.close()
        return

    async with history_lock:
        if session_id not in session_histories:
            session_histories[session_id] = []

    turn_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    async def tts_worker():
        while True:
            text = await turn_queue.get()
            if text is None:
                turn_queue.task_done()
                break
            try:
                await gemini_turn_to_murf(text, ws, session_id)
            finally:
                session_inflight[session_id] = False
                turn_queue.task_done()

    worker_task = asyncio.create_task(tts_worker())

    params = {
        "sample_rate": "16000",
        "encoding": "pcm_s16le",
        "format_turns": "true",
        "end_of_turn_confidence_threshold": "0.7",
        "min_end_of_turn_silence_when_confident": "160",
        "max_turn_silence": "2400",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"wss://streaming.assemblyai.com/v3/ws?{query}"

    # ✅ websockets 15.x requires list[tuple] for headers
    headers = [("Authorization", ENV_ASSEMBLYAI_KEY)]

    try:
         async with websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=15,
            ping_timeout=30,
            max_size=8 * 1024 * 1024
        ) as aai_ws:

            async def upstream():
                while True:
                    try:
                        buf = await ws.receive_bytes()
                        await aai_ws.send(buf)
                    except WebSocketDisconnect:
                        break
                    except:
                        try:
                            await ws.receive_text()
                        except:
                            pass
                        continue
                try:
                    await aai_ws.close()
                except:
                    pass

            async def downstream():
                async for raw_msg in aai_ws:
                    try:
                        if isinstance(raw_msg, bytes):
                            raw_msg = raw_msg.decode("utf-8", errors="ignore")
                        evt = json.loads(raw_msg)
                    except:
                        continue

                    t = evt.get("type")
                    if t == "Begin":
                        await safe_send_json(ws, {"event": "ws_ready"})
                    elif t == "Turn":
                        transcript = evt.get("transcript") or ""
                        if transcript and evt.get("end_of_turn"):
                            transcript_str = transcript.strip()
                            if not transcript_str:
                                continue
                            norm = " ".join(transcript_str.split()).casefold()
                            if session_inflight.get(session_id, False):
                                continue
                            if norm == session_last_text.get(session_id, ""):
                                continue
                            session_last_text[session_id] = norm
                            session_inflight[session_id] = True
                            await save_turn(session_id, "user", transcript_str)
                            await safe_send_json(ws, {"event": "turn_end", "role": "user", "text": transcript_str})
                            await turn_queue.put(transcript_str)
                    elif t in ("Termination", "TerminateSession"):
                        break

            await asyncio.gather(upstream(), downstream())
    finally:
        await turn_queue.put(None)
        worker_task.cancel()
        try:
            await worker_task
        except:
            pass
        for d in [session_personas, session_skills, session_inflight, session_last_text]:
            d.pop(session_id, None)
        try:
            await ws.close()
        except:
            pass
        logger.info("Session %s cleaned up", session_id)
