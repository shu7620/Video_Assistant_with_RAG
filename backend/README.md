# 🎥 TranscribeX

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-Backend-green" />
  <img src="https://img.shields.io/badge/React-Frontend-blue" />
  <img src="https://img.shields.io/badge/MongoDB-Atlas-success" />
  <img src="https://img.shields.io/badge/RAG-LangChain-orange" />
  <img src="https://img.shields.io/badge/Deployment-DigitalOcean-blueviolet" />
</p>

<p align="center">
  <a href="https://transcribex-nine.vercel.app/">🌐 Live Demo</a> •
  <a href="https://api.transcribex.me/docs">📚 API Docs</a>
</p>

# 🎥 TranscribeX – AI-Powered Media Intelligence Platform

Transform uploaded media into searchable knowledge using AI-powered transcription, summarization, semantic search, and conversational RAG.

🌐 **Live Application:** https://transcribex.me  
🚀 **Backend API:** https://api.transcribex.me/docs

---

## 📌 Overview

TranscribeX is an end-to-end AI Media Assistant that enables users to upload videos/audio files, instantly interact with the content through an intelligent chatbot.

The platform automatically:

- Extracts audio
- Generates transcripts using Whisper
- Produces structured AI summaries
- Creates vector embeddings
- Stores knowledge in MongoDB Atlas
- Enables Retrieval-Augmented Generation (RAG)
- Allows conversational querying of processed content

Instead of manually watching lengthy videos, users can simply ask questions and receive context-aware answers grounded in the video's content.

---
## 🚀 Highlights

- 🎙️ Audio/Video Transcription using Whisper
- 📑 AI-Powered Summarization using Mistral AI
- 🔍 Semantic Search with MongoDB Atlas Vector Search
- 🎯 FlashRank Reranking for highly relevant retrieval
- 🔄 Query Normalization Pipeline
- 💬 Conversational Retrieval-Augmented Generation (RAG)
- 🔐 JWT Authentication & User-Specific Analysis History
- ☁️ Production Deployment on DigitalOcean with Docker & Nginx
- 🌐 HTTPS-enabled custom domain deployment

# ✨ Key Features

## 🎬 Multi-Source Video Processing

Supports:

- MP4 Videos
- MP3 Audio
- WAV Audio
- M4A Audio
- Other common media formats

---

## 🎙️ AI-Powered Transcription

Uses OpenAI Whisper to generate highly accurate transcripts from audio content.

### Features

- Automatic speech-to-text conversion
- Long-video support
- Chunk-based processing
- Language-aware transcription pipeline

---

## 🧠 Intelligent Summarization

Generates structured summaries including:

- Executive Summary
- Key Insights
- Important Concepts
- Action Items
- Main Takeaways

Powered by:

- Mistral AI LLM

---

## 🔍 Retrieval-Augmented Generation (RAG)

Instead of relying on the LLM's memory, TranscribeX answers questions directly from processed content.

### Benefits

- Reduced hallucinations
- Context-aware answers
- Accurate retrieval
- Source-grounded responses

---

## 💬 Conversational AI Chat

After processing a media, users can interact with it using natural language.

### Example Questions

```text
What are the key points discussed?
Explain Graph Neural Networks in simple terms.
Summarize the training process.
What datasets were used?
List all advantages mentioned.
```

---

## 🗂️ Persistent Analysis History

Every processed analysis is stored.

Users can:

- View previous analyses
- Reopen old sessions
- Continue conversations
- Access generated summaries

---

## 🔐 Secure Authentication

Features:

- User Registration
- User Login
- JWT Authentication
- Password Hashing
- Protected APIs

---

## ☁️ Production Deployment

### Frontend

- Vercel

### Backend

- Dockerized FastAPI Application
- DigitalOcean Droplet
- Nginx Reverse Proxy
- SSL via Let's Encrypt

### Database

- MongoDB Atlas

---

# 🏗️ System Architecture

```text
                   ┌─────────────────────┐
                   │      Frontend       │
                   │      React.js       │
                   │      Vite           │
                   └─────────┬───────────┘
                             │
                             ▼
                   ┌─────────────────────┐
                   │   FastAPI Backend   │
                   │     Dockerized      │
                   └─────────┬───────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼

┌────────────────┐ ┌────────────────┐ ┌────────────────┐
│  Whisper AI    │ │   Mistral AI   │ │ MongoDB Atlas  │
│ Transcription  │ │ Summarization  │ │ Vector Storage │
└────────────────┘ └────────────────┘ └────────────────┘
                             │
                             ▼
                   ┌─────────────────────┐
                   │   LangChain RAG     │
                   │ Semantic Retrieval  │
                   └─────────────────────┘
```

---

# 🔄 Complete Workflow

## Step 1 — User Input

User provides:


Upload Media File

```text
.mp4
.mp3
.wav
.m4a
```

---

## Step 2 — Audio Processing

The system:

- Converts media into optimized WAV format
- Standardizes:
  - Mono Channel
  - 16kHz Sample Rate

---

## Step 3 — Intelligent Chunking

Large audio files are split into overlapping chunks.

### Benefits

- Memory-efficient processing
- Better transcription quality
- Preserves context boundaries

---

## Step 4 — Speech-to-Text

Whisper processes each chunk and generates transcripts.

```text
Audio Chunks
      ↓
Whisper
      ↓
Transcript
```

---

## Step 5 — AI Summarization

The transcript is summarized using Mistral AI.

Generated outputs include:

- Executive Summary
- Detailed Notes
- Key Takeaways
- Important Topics

---

## Step 6 — Vector Embedding Generation

Transcript content is converted into semantic embeddings.

Used Models:

- HuggingFace Embeddings
- Sentence Transformers (all-MiniLM-L6-v2)

---

## Step 7 — Vector Database Storage

Embeddings are stored in:

### MongoDB Atlas

Collections:

- Users
- Tasks
- Analyses
- Chat History
- Vector Store

---

## Step 8 — Conversational Retrieval

When a user asks a question:

```text
Question
    ↓
Query Normalization
    ↓
Vector Retrieval
    ↓
FlashRank Reranking
    ↓
Top Context Chunks
    ↓
Mistral LLM
    ↓
Final Response
```

The chatbot retrieves only relevant transcript sections before generating an answer.

---

# 🧠 RAG Pipeline

```text
Transcript
     ↓
Chunking
     ↓
Embeddings
     ↓
MongoDB Atlas Vector Search
     ↓
Retriever
     ↓
Candidate Chunks
     ↓
FlashRank Reranker
     ↓
Top Ranked Context
     ↓
Mistral AI
     ↓
Grounded Response
```

---

# 🛠️ Tech Stack

## Frontend

- React.js
- Vite
- JavaScript
- Tailwind CSS

---

## Backend

- FastAPI
- Python
- Uvicorn

---

## AI & LLM Stack

- OpenAI Whisper
- Mistral AI
- LangChain
- HuggingFace Embeddings
- Sentence Transformers (all-MiniLM-L6-v2)

---

## Database

- MongoDB Atlas

---

## DevOps

- Docker
- Docker Compose
- Nginx
- DigitalOcean
- Let's Encrypt SSL

---

# 📂 Project Structure

```text
backend/
│
├── app/
│   ├── core/
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── rag_engine.py
│   │   ├── summarize.py
│   │   ├── transcriber.py
│   │   └── vector_store.py
│   │
│   ├── utils/
│   │   └── audio_processor.py
│   │
│   └── main.py
│
├── downloads/
├── temp_uploads/
├── Dockerfile
├── docker-compose.yaml
├── Requirements.txt
└── pyproject.toml
```

---

# 🔒 Security Features

- JWT Authentication
- Password Hashing
- HTTPS Enabled
- Secure API Access
- Environment Variable Configuration
- MongoDB Credential Isolation

---

# 🚀 Future Enhancements

- Multi-language transcription
- PDF export
- Speaker diarization
- Timestamped citations
- Video chapter generation
- Meeting intelligence workflows
- Team collaboration features
- Semantic search across multiple videos

---

# 📸 Live Demo

🌐 **Frontend:** https://transcribex.me

📚 **API Documentation:** https://api.transcribex.me/docs

---

# 👨‍💻 Author

**Shubham Mandal**

MCA Student At NIT Raipur| AI & Full Stack Developer

Passionate about building production-grade AI applications using FastAPI, LangChain, RAG, LLMs, Vector Databases, and Cloud Infrastructure.

---

## ⭐ If you found this project useful, consider giving it a star!
