"""
FRIDAY Overlay — Floating audio visualizer widget.
Shows a small dark pill at the top-center of the screen with
animated equalizer bars that react to mic input.
"""

import threading
import tkinter as tk
import numpy as np
import pyaudio

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BAR_COUNT = 24
BAR_WIDTH = 4
BAR_GAP = 3
BAR_MAX_HEIGHT = 30
WIDGET_PADDING_X = 20
WIDGET_PADDING_Y = 10
BG_COLOR = "#1a1a2e"
BAR_COLOR = "#00d4ff"
BAR_COLOR_HOT = "#ff6b6b"
OVERLAY_Y_OFFSET = 30  # pixels from top of screen
FPS = 30

AUDIO_RATE = 16000
AUDIO_CHUNK = 1024


class FridayOverlay:
    """Floating audio visualizer overlay."""

    def __init__(self):
        self._root = None
        self._canvas = None
        self._bars = []
        self._audio = None
        self._stream = None
        self._levels = [0.0] * BAR_COUNT
        self._visible = False
        self._thread = None
        self._running = False

    def _setup_window(self):
        self._root = tk.Tk()
        self._root.title("FRIDAY")
        self._root.overrideredirect(True)  # borderless
        self._root.attributes("-topmost", True)  # always on top
        self._root.attributes("-alpha", 0.85)  # slight transparency
        self._root.configure(bg=BG_COLOR)

        # Calculate widget size
        total_width = BAR_COUNT * (BAR_WIDTH + BAR_GAP) - BAR_GAP + WIDGET_PADDING_X * 2
        total_height = BAR_MAX_HEIGHT + WIDGET_PADDING_Y * 2

        # Center at top of screen
        screen_width = self._root.winfo_screenwidth()
        x = (screen_width - total_width) // 2
        y = OVERLAY_Y_OFFSET

        self._root.geometry(f"{total_width}x{total_height}+{x}+{y}")

        # Round corners via a canvas background
        self._canvas = tk.Canvas(
            self._root,
            width=total_width,
            height=total_height,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self._canvas.pack()

        # Create bar rectangles
        self._bars = []
        for i in range(BAR_COUNT):
            bx = WIDGET_PADDING_X + i * (BAR_WIDTH + BAR_GAP)
            by = WIDGET_PADDING_Y + BAR_MAX_HEIGHT
            rect = self._canvas.create_rectangle(
                bx, by, bx + BAR_WIDTH, by,
                fill=BAR_COLOR, outline="",
            )
            self._bars.append(rect)

        # Start hidden
        self._root.withdraw()

    def _start_mic(self):
        self._audio = pyaudio.PyAudio()
        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=AUDIO_RATE,
            input=True,
            frames_per_buffer=AUDIO_CHUNK,
        )

    def _stop_mic(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._audio:
            self._audio.terminate()
            self._audio = None

    def _read_levels(self):
        """Read mic data and compute bar levels via FFT."""
        if not self._stream:
            return

        try:
            raw = self._stream.read(AUDIO_CHUNK, exception_on_overflow=False)
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

            # FFT to get frequency bins
            fft = np.abs(np.fft.rfft(data))
            # Group into BAR_COUNT bins
            bin_size = max(1, len(fft) // BAR_COUNT)
            levels = []
            for i in range(BAR_COUNT):
                start = i * bin_size
                end = min(start + bin_size, len(fft))
                level = np.mean(fft[start:end]) if start < len(fft) else 0
                levels.append(level)

            # Normalize to 0-1
            max_level = max(max(levels), 1.0)
            self._levels = [min(l / max_level, 1.0) for l in levels]
        except Exception:
            pass

    def _update_bars(self):
        """Update bar heights based on current levels."""
        if not self._canvas or not self._visible:
            return

        for i, rect in enumerate(self._bars):
            level = self._levels[i] if i < len(self._levels) else 0
            # Smooth: bars have a minimum height for visual appeal
            height = max(2, int(level * BAR_MAX_HEIGHT))
            bx = WIDGET_PADDING_X + i * (BAR_WIDTH + BAR_GAP)
            by_bottom = WIDGET_PADDING_Y + BAR_MAX_HEIGHT
            by_top = by_bottom - height

            self._canvas.coords(rect, bx, by_top, bx + BAR_WIDTH, by_bottom)

            # Color shift: blue when quiet, reddish when loud
            if level > 0.7:
                self._canvas.itemconfig(rect, fill=BAR_COLOR_HOT)
            else:
                self._canvas.itemconfig(rect, fill=BAR_COLOR)

    def _tick(self):
        """Main animation loop — called on the Tk thread."""
        if not self._running:
            return
        if self._visible:
            self._read_levels()
            self._update_bars()
        self._root.after(1000 // FPS, self._tick)

    def show(self):
        """Show the overlay and start mic capture."""
        if self._root and not self._visible:
            self._visible = True
            self._start_mic()
            self._root.deiconify()

    def hide(self):
        """Hide the overlay and stop mic capture."""
        if self._root and self._visible:
            self._visible = False
            self._stop_mic()
            self._root.withdraw()

    def start(self):
        """Start the overlay in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self._setup_window()
        self._tick()
        self._root.mainloop()

    def stop(self):
        """Stop the overlay."""
        self._running = False
        self._visible = False
        self._stop_mic()
        if self._root:
            try:
                self._root.quit()
            except Exception:
                pass
