import os
import logging
import time
import tempfile
import wave
from collections import deque

from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks, voice_recv
import speech_recognition as sr
from gtts import gTTS
from playsound import playsound
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

# Load environment variables
load_dotenv()

# Environment/config variables
TRIGGER_WORD = os.getenv("TRIGGER_WORD")
CONVERSATION_TIMEOUT = int(os.getenv("CONVERSATION_TIMEOUT"))
DISCORD_GUILD_ID = int(os.getenv("GUILD_ID"))
DISCORD_BOT_TOKEN = os.getenv("BOT_TOKEN")
FFMPEG_PATH = os.getenv("FFMPEG_PATH")
TARGET_USER_ID = int(os.getenv("TARGET_USER_ID"))
DISCORD_TARGET_CHANNEL_ID = int(os.getenv("DISCORD_TARGET_CHANNEL_ID"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")
DISCORD_AUDIO_LOOP_SECONDS = float(os.getenv("DISCORD_AUDIO_LOOP_SECONDS"))

AUDIO_FILE = "source/dup.mp3"
LANGUAGE = "de-DE"

recognizer = sr.Recognizer()
voice_client = None
no_speech = False

# Logging setup
class CodeFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'code'):
            record.code = '---'
        return super().format(record)

handler = logging.StreamHandler()
formatter = CodeFormatter("%(asctime)s [%(levelname)s] [Code: %(code)s] %(message)s")
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Langchain setup
tools = []
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}")
])
llm = ChatOllama(model=OLLAMA_MODEL, reasoning=False)
agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

def speak_text(text: str):
    global voice_client
    try:
        tts = gTTS(text=text, lang='de', slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            temp_filename = fp.name
        tts.save(temp_filename)
        if not (voice_client and voice_client.is_connected()):
            playsound(temp_filename)
            os.remove(temp_filename)
            return
        audio_source = discord.FFmpegPCMAudio(temp_filename, executable=FFMPEG_PATH)
        voice_client.play(
            audio_source,
            after=lambda e: os.remove(temp_filename) if e is None else logging.error("Fehler beim Abspielen.", extra={'code': 301})
        )
    except Exception as e:
        logging.error(f"{e}", extra={'code': 301})

class VoiceRecorder(voice_recv.AudioSink):
    def __init__(self, saves_dir: str):
        super().__init__()
        self.audio_data = []
        self.audio_buffer = deque()
        self.buffer_duration = 30
        self.sample_rate = 48000
        self.bytes_per_sample = 2
        self.channels = 2
        self.max_buffer_size = self.buffer_duration * self.sample_rate * self.bytes_per_sample * self.channels
        self.saves_dir = saves_dir
        self._current_buffer_size = 0

    def wants_opus(self) -> bool:
        return False

    def write(self, user, data):
        self.audio_data.append(data.pcm)
        self.audio_buffer.append(data.pcm)
        self._current_buffer_size += len(data.pcm)
        while self._current_buffer_size > self.max_buffer_size:
            removed_chunk = self.audio_buffer.popleft()
            self._current_buffer_size -= len(removed_chunk)

    async def save(self):
        combined_audio = b"".join(self.audio_data)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp:
            temp_filename = fp.name
            with wave.open(temp_filename, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.bytes_per_sample)
                wf.setframerate(self.sample_rate)
                wf.writeframes(combined_audio)
        return temp_filename

    async def save_last_30_seconds(self):
        combined_audio = b"".join(self.audio_buffer)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.saves_dir, f"audio_{timestamp}.wav")
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.bytes_per_sample)
            wf.setframerate(self.sample_rate)
            wf.writeframes(combined_audio)
        return filename

    def cleanup(self):
        self.audio_data.clear()
        self.audio_buffer.clear()

async def transcribe_discord_audio(recognizer_obj, audio_file):
    global no_speech
    with sr.AudioFile(audio_file) as source:
        audio = recognizer_obj.record(source)
    try:
        return recognizer_obj.recognize_google(audio, language=LANGUAGE)
    except sr.UnknownValueError:
        if no_speech:
            return None
        logging.warning("Keine Sprache erkannt.", extra={'code': 304})
        no_speech = True
        return None
    except sr.RequestError as e:
        logging.error(f"API-Fehler: {e}", extra={'code': 304})
        return None

def disc():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    saves_dir = os.path.join(base_dir, "saves")
    if not os.path.exists(saves_dir):
        os.makedirs(saves_dir)
        logging.info(f"Ordner '{saves_dir}' erstellt.", extra={'code': 100})

    class CustomClient(commands.Bot):
        def __init__(self):
            intents = discord.Intents.default()
            intents.members = True
            intents.voice_states = True
            intents.message_content = True
            super().__init__(intents=intents, command_prefix=commands.when_mentioned)
            self.guild_id = DISCORD_GUILD_ID
            self.voice_recorder = None
            self.synced = False
            self.last_discord_interaction_time = None
            self.discord_conversation_mode = False
            self.garmin_conversation_mode = False
            self.joined_voice_channel_once = False
            self.saves_dir = saves_dir
            self.last_saved_audio_path = None

        async def on_ready(self):
            await self.wait_until_ready()
            if not self.synced:
                await self.tree.sync(guild=discord.Object(id=self.guild_id))
                self.synced = True
            await self.change_presence(status=discord.Status.invisible)
            logging.info(f"Eingeloggt als {self.user}", extra={'code': 200})
            self.monitor_voice_channels.start()
            logging.info("Voice-Monitor gestartet.", extra={'code': 201})

        @tasks.loop(seconds=DISCORD_AUDIO_LOOP_SECONDS)
        async def process_discord_audio(self):
            global voice_client, no_speech

            if not (self.voice_recorder and self.voice_recorder.audio_data):
                return

            audio_file = await self.voice_recorder.save()
            transcript = await transcribe_discord_audio(recognizer, audio_file)
            os.remove(audio_file)
            self.voice_recorder.audio_data.clear()

            if not transcript:
                return

            no_speech = False

            if self.discord_conversation_mode:
                logging.info(f"Eingabe: {transcript}", extra={'code': 230})
                response = executor.invoke({"input": transcript})
                content = response.get("output", str(response))
                logging.info(f"Antwort: {content}", extra={'code': 231})
                speak_text(content)
                self.discord_conversation_mode = True
                return

            lower_transcript = transcript.lower()
            lower_trigger_word = TRIGGER_WORD.lower()

            if lower_trigger_word in lower_transcript:
                logging.info(f"Trigger erkannt: {transcript}", extra={'code': 210})
                if voice_client and voice_client.is_connected():
                    audio_source = discord.FFmpegPCMAudio(AUDIO_FILE, executable=FFMPEG_PATH)
                    voice_client.play(audio_source, after=lambda e: logging.error(f"{e}", extra={'code': 305}) if e else None)
                self.garmin_conversation_mode = False
                self.discord_conversation_mode = True
                self.last_discord_interaction_time = time.time()
                return

            if "garmin" in lower_transcript:
                logging.info("Befehl erkannt: Okay Garmin", extra={'code': 221})
                audio_source = discord.FFmpegPCMAudio("source/dup.mp3", executable=FFMPEG_PATH)
                voice_client.play(audio_source, after=lambda e: logging.error(f"{e}", extra={'code': 306}) if e else None)
                self.last_discord_interaction_time = time.time()
                self.discord_conversation_mode = False
                self.garmin_conversation_mode = True
                return

            if "video speichern" in lower_transcript and self.garmin_conversation_mode:
                logging.info("Befehl erkannt: Video speichern", extra={'code': 220})
                try:
                    saved_file = await self.voice_recorder.save_last_30_seconds()
                    self.last_saved_audio_path = saved_file
                    logging.info(f"Letzte 30 Sekunden als '{saved_file}' gespeichert.", extra={'code': 222})
                    audio_source = discord.FFmpegPCMAudio("source/dupdup.mp3", executable=FFMPEG_PATH)
                    voice_client.play(audio_source, after=lambda e: logging.error(f"{e}", extra={'code': 306}) if e else None)
                    try:
                        target_channel = self.get_channel(DISCORD_TARGET_CHANNEL_ID)
                        if not (target_channel and isinstance(target_channel, discord.TextChannel)):
                            logging.warning(f"Zielkanal {target_channel} nicht gefunden oder ist kein Textkanal.", extra={'code': 274})
                            speak_text("Der Zielkanal für das Speichern der Audiodatei konnte nicht gefunden werden.")
                            return
                        audio_file = discord.File(saved_file)
                        await target_channel.send(file=audio_file)
                        logging.info(f"Audiodatei '{saved_file}' automatisch an Kanal {target_channel} gesendet.", extra={'code': 273})
                    except Exception as e:
                        logging.error(f"Fehler beim automatischen Senden der Datei an Kanal {target_channel}: {e}", extra={'code': 313})
                        speak_text("Es gab einen Fehler beim automatischen Senden der Audiodatei.")
                except Exception as e:
                    logging.error(f"Fehler beim Speichern der letzten 30 Sekunden: {e}", extra={'code': 309})
                    speak_text("Es gab einen Fehler beim Speichern der letzten 30 Sekunden.")
                self.last_discord_interaction_time = time.time()
                self.discord_conversation_mode = False
                self.garmin_conversation_mode = False
                return

            if "lied" in lower_transcript and self.garmin_conversation_mode:
                logging.info("Befehl erkannt: Lied", extra={'code': 223})
                audio_source = discord.FFmpegPCMAudio("source/ssong.mp3", executable=FFMPEG_PATH)
                voice_client.play(audio_source, after=lambda e: logging.error(f"{e}", extra={'code': 306}) if e else None)
                self.last_discord_interaction_time = time.time()
                self.discord_conversation_mode = False
                self.garmin_conversation_mode = False
                return

            logging.info(f"Transkript (wartend): {transcript}", extra={'code': 211})

            timeout_reached = (
                self.last_discord_interaction_time
                and (time.time() - self.last_discord_interaction_time > CONVERSATION_TIMEOUT)
            )

            if not timeout_reached:
                return

            if self.discord_conversation_mode:
                logging.info("Timeout erreicht, Gespräch beendet.", extra={'code': 240})
                self.discord_conversation_mode = False
            if self.garmin_conversation_mode:
                logging.info("Timeout erreicht, Garmin beendet.", extra={'code': 240})
                self.garmin_conversation_mode = False

        @tasks.loop(seconds=1.5)
        async def monitor_voice_channels(self):
            global voice_client
            if self.joined_voice_channel_once:
                logging.info("Bereits beigetreten, Monitoring gestoppt.", extra={'code': 250})
                self.monitor_voice_channels.cancel()
                return
            guild = self.get_guild(self.guild_id)
            if not guild:
                logging.warning(f"Guild {self.guild_id} nicht gefunden.", extra={'code': 251})
                return
            logging.info(f"Monitoring Guild: {guild.name} ({guild.id})", extra={'code': 252})
            target_channel = None
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.id == TARGET_USER_ID:
                        target_channel = channel
                        logging.info(f"Zielnutzer in: {channel.name}", extra={'code': 253})
                        break
                if target_channel:
                    break
            if not target_channel:
                return
            try:
                voice_client = await target_channel.connect(cls=voice_recv.VoiceRecvClient)
                self.voice_recorder = VoiceRecorder(self.saves_dir)
                voice_client.listen(self.voice_recorder)
                if not self.process_discord_audio.is_running():
                    self.process_discord_audio.start()
                logging.info(f"Voice-Channel beigetreten: {target_channel.name}", extra={'code': 254})
                self.joined_voice_channel_once = True
                self.monitor_voice_channels.cancel()
            except Exception as e:
                logging.error(f"{e}", extra={'code': 307})

    client = CustomClient()
    client.run(DISCORD_BOT_TOKEN, log_handler=None)

if __name__ == "__main__":
    disc()
