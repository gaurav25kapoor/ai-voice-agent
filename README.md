# 🎤 AI Voice Agent

A conversational AI voice agent built with **FastAPI**, **TailwindCSS**, and **Gemini API**, designed for **real-time voice interactions**.  
This project demonstrates smooth **voice-to-text** and **text-to-speech** integration for building modern AI-driven applications.

---

## 🚀 Features
- 🎙 **Voice Recording & Transcription** — Capture audio from the browser and transcribe in real time using AssemblyAI.
- 🤖 **Intelligent Conversations** — Gemini API generates context-aware, persona-based responses.
- 🔊 **Text-to-Speech** — Murf AI converts AI-generated responses into natural, high-quality voice.
- 🖌 **Clean & Responsive UI** — Built with TailwindCSS, optimized for desktop and mobile.
- ⚡ **Fast Backend** — FastAPI ensures efficient WebSocket streaming and request handling.
- 🎯 **Single-Click Recording** — Start/stop sessions with a single button for seamless UX.
- 💬 **Multiple Personas & Skills** — Customize your AI agent with personas (Pirate, Cowboy, Robot, Professor, Buddy) and skills (Weather, News, Jokes, Quotes, Dictionary, Time & Date).
- 🔄 **Auto-play Responses** — AI voice output is streamed and played automatically in the browser.

---

## 🏗 Architecture

Browser (UI + Web Audio API)
⬇
WebSocket → FastAPI Backend
⬇
AssemblyAI → Transcribe Voice → Text
⬇
Gemini API → Generate AI Response
⬇
Murf AI → Text-to-Speech Streaming
⬇
Audio Playback in Browser


---

## 🛠️ Tech Stack

**Frontend:**  
- HTML + Tailwind CSS  
- JavaScript (Web Audio API, WebSocket streaming)

**Backend:**  
- FastAPI (Python)  
- WebSockets for real-time voice streaming  
- Murf AI (Text-to-Speech)  
- Gemini API (LLM responses)  
- AssemblyAI (Voice-to-Text)

**Others:**  
- Environment variable-based configuration  
- JSON-based chat history persistence  

---

## ⚙️ Installation & Local Setup

Follow these steps to run **AI Voice Agent** locally:

1. **Clone the Repository**
git clone https://github.com/gaurav25kapoor/ai-voice-agent.git
cd ai-voice-agent

2. **Create a Virtual Environment**
python -m venv venv

3. **Activate the Virtual Environment**
venv\Scripts\Activate

4. **Install Dependencies**
pip install -r requirements.txt

5. **Set Environment Variables**
Create a .env file in the project root and add your API keys:
GEMINI_API_KEY=your_gemini_api_key
ASSEMBLYAI_API_KEY=your_assemblyai_api_key
MURF_API_KEY=your_murf_api_key

6. **Run the FastAPI Server**
uvicorn main:app --reload

7. **Access the Application**
Open your browser and go to: http://127.0.0.1:8000
