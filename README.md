# Discord Voice Assistant mit Sprachsteuerung & Ollama-Integration

Dieses Projekt implementiert einen **Discord-Bot**, der:
- Sprachbefehle aus Voice-Channels erkennt (Google Speech Recognition)
- Mit **Trigger-Wörtern** wie `Okay Garmin` oder einem frei definierbaren Aktivierungswort arbeitet  
- Antworten über **Text-to-Speech (gTTS)** wiedergibt  
- Sprachkonversationen mit einem **lokalen Ollama-LLM** (z. B. `qwen3:1.7b`) führt  
- Auf Befehle reagieren kann, z. B.:
  - "Video speichern" → speichert die letzten 30 Sekunden Audio und sendet die Datei in einen Discord-Channel  
  - "Lied" → spielt eine Audiodatei ab  
- Automatisch einem Voice-Channel beitritt, sobald der **Zielnutzer** online ist  

---

## ⚙️ Voraussetzungen

- **Python 3.10+**
- Installierte Pakete (siehe `requirements.txt`):
    - `logging`
    - `dotenv`
    - `pyttsx3==2.99`
    - `gtts==2.5.4`
    - `playsound==1.2.2`
    - `pygame==2.6.1`
    - `python-dotenv==1.1.1`
    - `speechrecognition==3.14.3`
    - `sounddevice==0.5.2`
    - `vosk==0.3.45`
    - `langchain_core==0.3.72`
    - `langchain_ollama==0.3.6`
    - `langchain==0.3.27`
    - `pyaudio`
    - `discord`
    - `PyNaCl`
    - `ffmpeg-python`
    - **FFmpeg** installiert und über Umgebungsvariable `FFMPEG_PATH` erreichbar - siehe `https://ffmpeg.org/`
    - **Ollama** installiert und lauffähig mit `qwen3:1.7b` - siehe `https://ollama.com/`

---

## 🔑 .env Konfiguration

Lege im Projektordner eine `.env` Datei mit folgendem Inhalt an:

```env
TRIGGER_WORD=
CONVERSATION_TIMEOUT=30
GUILD_ID=
BOT_TOKEN=""
FFMPEG_PATH=/usr/bin/ffmpeg
TARGET_USER_ID=
DISCORD_TARGET_CHANNEL_ID=
OLLAMA_MODEL="qwen3:1.7b"
SYSTEM_PROMPT=""
DISCORD_AUDIO_LOOP_SECONDS=1.7
```

---

## ▶️ Starten

```bash
python main.py
```

Der Bot:
1. Wartet, bis der Zielnutzer einem Voice-Channel beitritt  
2. Tritt automatisch bei und startet die Spracherkennung  
3. Reagiert auf **Trigger-Wort** oder den Befehl **„Okay Garmin“**  
4. Führt eine Unterhaltung über das konfigurierte Ollama-Modell  

---

## 🎙️ Sprachbefehle

- **Triggerwort (frei wählbar)** → startet Gesprächsmodus  
- **„Okay Garmin“** → Garmin-Modus aktivieren  
- **„Video speichern“ (nur Garmin-Modus)** → speichert letzte 30 Sekunden und postet Datei  
- **„Lied“ (nur Garmin-Modus)** → spielt eine Musikdatei  

---

## 📝 Logging & Error Codes

Das Skript nutzt ein eigenes **Logging-Format** mit Fehlercodes.  
Beispiel:

```
2025-08-19 18:45:12 [INFO] [Code: 210] Trigger erkannt: okay
```

### Liste der Codes

#### ✅ Allgemeine Codes (100–199)
- **100** → Ordner `saves/` wurde erstellt  

#### 🔐 Login & Initialisierung (200–209)
- **200** → Bot erfolgreich eingeloggt  
- **201** → Voice-Monitor gestartet  

#### 🎙️ Sprachverarbeitung / Trigger (210–229)
- **210** → Triggerwort erkannt  
- **211** → Transkript im Wartemodus erkannt (noch kein aktiver Gesprächsmodus)  
- **220** → Befehl „Video speichern“ erkannt  
- **221** → Befehl „Okay Garmin“ erkannt  
- **222** → Letzte 30 Sekunden erfolgreich gespeichert  
- **223** → Befehl „Lied“ erkannt  

#### 💬 Konversation (230–239)
- **230** → Eingabe im Gesprächsmodus  
- **231** → Antwort vom LLM erhalten  
- **240** → Timeout erreicht, Gespräch/Modus beendet  

#### 🔎 Voice-Channel Monitoring (250–259)
- **250** → Bot ist bereits beigetreten, Monitoring wird gestoppt  
- **251** → Guild nicht gefunden  
- **252** → Monitoring gestartet für eine bestimmte Guild  
- **253** → Zielnutzer in Voice-Channel gefunden  
- **254** → Voice-Channel erfolgreich beigetreten  

#### ⚠️ Fehler & Warnungen (300–399)
- **301** → Fehler beim Abspielen von Audio (TTS oder Datei)  
- **304** → Keine Sprache erkannt / API-Fehler bei Speech Recognition  
- **305** → Fehler beim Abspielen von Trigger-Audio  
- **306** → Fehler beim Abspielen von Garmin- oder Bestätigungs-Audio  
- **307** → Fehler beim Beitritt in Voice-Channel  
- **309** → Fehler beim Speichern der letzten 30 Sekunden  
- **313** → Fehler beim automatischen Senden einer Audiodatei an Discord-Channel  

---

## 🚧 Bekannte Einschränkungen

- Spracherkennung basiert auf **Google Speech Recognition API** (Internet nötig).  
- Antworten werden mit **gTTS** erzeugt (langsamer als lokale TTS).  
- Nur **ein Nutzer** wird aktuell überwacht (`TARGET_USER_ID`) zum Joinen.  

