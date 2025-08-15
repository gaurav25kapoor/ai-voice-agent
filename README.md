# 🎤 AI Voice Agent

A conversational AI voice agent built with **FastAPI**, **TailwindCSS**, and **Gemini API**, designed for smooth, real-time interaction.  
This project showcases the power of **voice-to-text** and **text-to-speech** integration for building modern AI-driven applications.

---

## 🚀 Features
- 🎙 **Record & Transcribe** — Capture audio from the browser and send it for transcription.
- 🤖 **Conversational AI** — Uses Gemini API for intelligent, context-aware responses.
- 🔊 **Text-to-Speech** — Converts AI-generated responses into natural voice using Murf AI.
- 🖌 **Clean & Professional UI** — Styled with TailwindCSS, responsive and recruiter-friendly.
- ⚡ **Fast Backend** — Powered by FastAPI for efficient request handling.
- 📦 **Single Button Recording** — Intuitive UX for starting and stopping recordings.
- 🎯 **Auto-play Responses** — No need to manually play the AI's voice output.

---

## 🏗 Architecture
Frontend (Next.js + Tailwind)
       ⬇
Voice Recording (Web Audio API)
       ⬇
FastAPI Backend
       ⬇
OpenAI GPT (Generate Response)
       ⬇
Murf AI TTS (Generate Speech)
       ⬇
Audio Playback in Browser


## 🛠️ Tech Stack  

**Frontend:**  
- HTML
- Tailwind CSS  
- Javascript 

**Backend:**  
- FastAPI (Python) for API processing  
- Murf AI API for Text-to-Speech  
- OpenAI API for LLM responses  

**Others:**  
- Web Audio API for voice recording  
- Environment variable-based configuration  


## ⚙️ Installation & Setup

Follow these steps to get your **AI Voice Agent** running locally:

1. **Clone the Repository**
   git clone https://github.com/your-username/ai-voice-agent.git
   cd ai-voice-agent

2. **Create a Virtual Environment**

python -m venv venv

3. **Activate the Virtual Environment**

Windows (PowerShell)
venv\Scripts\Activate

Mac/Linux
source venv/bin/activate

4. **Install Dependencies**
pip install -r requirements.txt

5. **Set Environment Variables**
Create a .env file in the project root and add the following:


GEMINI_API_KEY=your_gemini_api_key_here
CLERK_API_KEY=your_clerk_api_key_here
ASSEMBLYAI_API_KEY=your_assemblyai_api_key_here

6. **Run the FastAPI Server**
uvicorn main:app --reload

7. **Access the Application**
Open your browser and go to:http://127.0.0.1:8000
