"""
FocusGuard — Voice Reminder Manager (Clear Professional Voice)
Speaks a single clear sentence: "Please come back to study area immediately."
- Non-blocking background worker thread
- Immediately stops when student returns
- No chunking — full sentence spoken at once for clear natural delivery
- Picks the clearest English voice available on Windows
"""
import threading
import queue
import time
import pyttsx3
from voice.messages import ABSENT_REMINDER


class VoiceManager:
    """
    Non-blocking, interruptible voice reminder engine.
    Speaks one clear sentence when student is absent.
    """

    def __init__(self, voice_style: str = "Professional"):
        self.voice_style   = voice_style
        # Queue size 1 — never pile up speech in memory
        self._queue        = queue.Queue(maxsize=1)
        self._lock         = threading.Lock()
        self._is_speaking  = False
        self._stop_requested = False
        self.is_on_break   = False
        self._active_engine = None

        # Single dedicated worker thread
        self._worker = threading.Thread(
            target=self._speech_worker, daemon=True, name="VoiceWorker"
        )
        self._worker.start()

    # ── Public API ─────────────────────────────────────────────────────

    def speak_reminder(self, level: int = 1):
        """Queue the absent reminder. Drops if on break or already queued."""
        if self.is_on_break or self._stop_requested:
            return
        try:
            self._queue.put_nowait(ABSENT_REMINDER)
        except queue.Full:
            pass  # already queued — don't duplicate

    def speak_text(self, text: str):
        """Queue custom text."""
        if self.is_on_break or self._stop_requested:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            pass

    def stop_speaking(self):
        """
        Instantly silence active speech and clear queue.
        Called when student returns to frame.
        """
        self._stop_requested = True
        # Drain queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        # Interrupt active engine
        with self._lock:
            if self._active_engine is not None:
                try:
                    self._active_engine.stop()
                except Exception:
                    pass

    def set_break(self, on_break: bool):
        """Toggle break mode — silences on break, re-enables on resume."""
        self.is_on_break = on_break
        if on_break:
            self.stop_speaking()
        else:
            # Allow reminders to fire again after break
            self._stop_requested = False

    def set_style(self, style: str):
        """Update voice style (no-op in simplified mode — single message only)."""
        self.voice_style = style

    def shutdown(self):
        """Permanently stop the voice worker thread and free resources."""
        self.is_on_break = True
        self.stop_speaking()
        try:
            self._queue.put_nowait(None)  # sentinel to exit worker loop
        except Exception:
            pass

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._is_speaking

    # ── Worker Thread ───────────────────────────────────────────────────

    def _speech_worker(self):
        """Background thread that processes queued messages."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        while True:
            try:
                msg = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue

            if msg is None:
                break  # shutdown sentinel

            if self.is_on_break or self._stop_requested:
                continue

            with self._lock:
                self._is_speaking    = True
                self._stop_requested = False

            try:
                self._speak_clearly(msg)
            except Exception as e:
                print(f"[VoiceManager] Speech error: {e}")
            finally:
                with self._lock:
                    self._is_speaking   = False
                    self._active_engine = None

    def _speak_clearly(self, text: str):
        """
        Speak the full sentence in one go with clear, professional settings.
        No chunking — uninterrupted delivery for natural speech.
        """
        if self.is_on_break or self._stop_requested:
            return

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        engine = None
        try:
            engine = pyttsx3.init()
            with self._lock:
                self._active_engine = engine

            # ── Voice clarity settings ──────────────────────────────────
            # Rate 145 = clear, natural, not too fast or slow
            engine.setProperty("rate",   145)
            engine.setProperty("volume", 1.0)

            # Pick the clearest English voice (prefer Zira/David/Hazel)
            voices = engine.getProperty("voices")
            selected = None
            priority = ["zira", "david", "hazel", "mark", "george", "english"]
            if voices:
                for keyword in priority:
                    for v in voices:
                        if keyword in (v.name or "").lower():
                            selected = v.id
                            break
                    if selected:
                        break
                # Fall back to first English voice
                if not selected:
                    for v in voices:
                        lang = (getattr(v, "languages", [None])[0] or "")
                        if "en" in str(lang).lower() or "english" in (v.name or "").lower():
                            selected = v.id
                            break
                if selected:
                    engine.setProperty("voice", selected)

            # ── Speak the full sentence without chunking ─────────────────
            if not (self._stop_requested or self.is_on_break):
                engine.say(text)
                engine.runAndWait()

        except Exception as e:
            print(f"[VoiceManager] pyttsx3 error: {e}")
        finally:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    pass
            with self._lock:
                self._active_engine = None
