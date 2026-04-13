"""
FRIDAY Overlay — Fullscreen click-through ambient overlay.

Replaces the old floating pill widget with a subtle, screen-wide experience:
  - Accelerating ripple that reveals a blue tint on activation
  - Breathing glow strip at the top of the screen
  - Scanning pulse for thinking / booting states
  - All fully click-through — nothing blocks mouse or keyboard

See OVERLAY_REWRITE.md for the full design spec.
"""

import ctypes
import math
import threading
import time
import tkinter as tk
from enum import Enum

# ---------------------------------------------------------------------------
# Win32 constants (avoid importing win32con just for these)
# ---------------------------------------------------------------------------

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
GA_ROOT = 2

# ---------------------------------------------------------------------------
# DPI awareness (call before any Tk window creation)
# ---------------------------------------------------------------------------

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor DPI aware
except Exception:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FPS = 20
TICK_MS = 1000 // FPS

# Tint
TINT_COLOR = "#0a1428"
TINT_ALPHA_TARGET = 0.10        # steady-state tint alpha
TINT_ALPHA_THINKING_LO = 0.10   # breathing range for thinking
TINT_ALPHA_THINKING_HI = 0.14
TINT_FADE_IN_DURATION = 0.3     # seconds
TINT_FADE_OUT_DURATION = 0.3

# Ripple
RIPPLE_DURATION = 0.6           # seconds
RIPPLE_ACCEL = 2.5              # ease-in exponent
RIPPLE_GLOW_BANDS = 5           # concentric glow rings
RIPPLE_GLOW_WIDTH = 8           # px between each glow band
RIPPLE_EDGE_COLOR = "#4a9eff"

# Top bar (breathing glow)
BAR_HEIGHT = 6
BAR_COLOR = "#1a5aff"
BAR_ALPHA_LO = 0.10
BAR_ALPHA_HI = 0.30
BAR_BREATHE_HZ = 1.0           # cycles per second

# Scanning pulse (thinking / booting)
PULSE_HZ = 0.8                  # sweeps per second
PULSE_WIDTH_FRAC = 0.12         # fraction of screen width for the bright region
PULSE_COLOR_BRIGHT = "#4a9eff"
PULSE_COLOR_DIM = "#0a1a3a"
PULSE_BANDS = 40                # number of vertical strips for the gradient sweep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

class OverlayState(Enum):
    SLEEPING = "sleeping"
    BOOTING = "booting"
    WAKING = "waking"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    DISMISSING = "dismissing"


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------

class FridayOverlay:
    """Fullscreen click-through overlay with ripple, tint, and breathing glow.

    Public API is identical to the old pill overlay so the launcher needs
    no changes.  State flags are set from any thread; _tick() on the Tk
    thread does all the actual rendering.
    """

    def __init__(self):
        self._thread = None
        self._running = False

        # Tk windows (created on Tk thread)
        self._root = None
        self._tint_win = None
        self._tint_canvas = None
        self._bar_win = None
        self._bar_canvas = None
        self._bar_rect = None         # the single glow rectangle
        self._pulse_rects = []        # pulse band rectangles

        # Screen dimensions (set during _setup_window)
        self._screen_w = 0
        self._screen_h = 0

        # State (set from any thread, consumed by _tick)
        self._want_state = OverlayState.SLEEPING
        self._current_state = OverlayState.SLEEPING
        self._transition_start = 0.0
        self._loading_text = ""       # kept for backward compat with show_loading(text)

        # Current alpha values (animated by _tick)
        self._tint_alpha = 0.0
        self._bar_alpha = 0.0

        # Tk visibility tracking
        self._tint_visible = False
        self._bar_visible = False

    # -- Window setup (Tk thread) ------------------------------------------

    def _setup_window(self):
        self._root = tk.Tk()
        self._root.withdraw()          # hidden root

        self._screen_w = self._root.winfo_screenwidth()
        self._screen_h = self._root.winfo_screenheight()

        # ---- Tint window (fullscreen blue fill) ----
        self._tint_win = tk.Toplevel(self._root)
        self._tint_win.overrideredirect(True)
        self._tint_win.attributes("-topmost", True)
        self._tint_win.geometry(f"{self._screen_w}x{self._screen_h}+0+0")

        # Use transparentcolor for the initial state so the ripple can
        # reveal blue incrementally.  The canvas bg starts as the key color
        # (fully transparent), and drawn items appear on top.
        self._transparent_key = "#010101"
        self._tint_win.configure(bg=self._transparent_key)
        self._tint_win.attributes("-transparentcolor", self._transparent_key)
        self._tint_win.attributes("-alpha", 0.0)

        self._tint_canvas = tk.Canvas(
            self._tint_win,
            width=self._screen_w, height=self._screen_h,
            bg=self._transparent_key, highlightthickness=0,
        )
        self._tint_canvas.pack()

        self._tint_win.withdraw()
        self._make_click_through(self._tint_win)

        # ---- Bar window (thin strip at top) ----
        self._bar_win = tk.Toplevel(self._root)
        self._bar_win.overrideredirect(True)
        self._bar_win.attributes("-topmost", True)
        self._bar_win.geometry(f"{self._screen_w}x{BAR_HEIGHT}+0+0")

        bar_bg_key = "#020202"
        self._bar_win.configure(bg=bar_bg_key)
        self._bar_win.attributes("-transparentcolor", bar_bg_key)
        self._bar_win.attributes("-alpha", 0.0)

        self._bar_canvas = tk.Canvas(
            self._bar_win,
            width=self._screen_w, height=BAR_HEIGHT,
            bg=bar_bg_key, highlightthickness=0,
        )
        self._bar_canvas.pack()

        # Single rectangle for the breathing glow
        self._bar_rect = self._bar_canvas.create_rectangle(
            0, 0, self._screen_w, BAR_HEIGHT,
            fill=BAR_COLOR, outline="",
        )

        # Pulse band rectangles (used for thinking/booting shimmer)
        band_w = max(1, self._screen_w // PULSE_BANDS)
        self._pulse_rects = []
        for i in range(PULSE_BANDS):
            x1 = i * band_w
            x2 = x1 + band_w
            rect = self._bar_canvas.create_rectangle(
                x1, 0, x2, BAR_HEIGHT,
                fill=PULSE_COLOR_DIM, outline="", state="hidden",
            )
            self._pulse_rects.append(rect)

        self._bar_win.withdraw()
        self._make_click_through(self._bar_win)

    def _make_click_through(self, tk_window):
        """Apply WS_EX_TRANSPARENT | WS_EX_LAYERED to make a window click-through."""
        tk_window.update_idletasks()
        hwnd = tk_window.winfo_id()
        hwnd = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        # Ensure topmost sticks
        ctypes.windll.user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    # -- Tint helpers (Tk thread) ------------------------------------------

    def _set_tint_alpha(self, alpha: float):
        alpha = max(0.0, min(1.0, alpha))
        if abs(alpha - self._tint_alpha) < 0.001:
            return
        self._tint_alpha = alpha
        if self._tint_win:
            self._tint_win.attributes("-alpha", alpha)

    def _set_bar_alpha(self, alpha: float):
        alpha = max(0.0, min(1.0, alpha))
        if abs(alpha - self._bar_alpha) < 0.001:
            return
        self._bar_alpha = alpha
        if self._bar_win:
            self._bar_win.attributes("-alpha", alpha)

    def _show_tint(self):
        if not self._tint_visible and self._tint_win:
            self._tint_win.deiconify()
            self._tint_visible = True

    def _hide_tint(self):
        if self._tint_visible and self._tint_win:
            self._tint_win.withdraw()
            self._tint_visible = False
            self._tint_alpha = 0.0

    def _show_bar(self):
        if not self._bar_visible and self._bar_win:
            self._bar_win.deiconify()
            self._bar_visible = True

    def _hide_bar(self):
        if self._bar_visible and self._bar_win:
            self._bar_win.withdraw()
            self._bar_visible = False
            self._bar_alpha = 0.0

    # -- Ripple drawing (Tk thread) ----------------------------------------

    def _draw_ripple(self, progress: float):
        """Draw the expanding gradient ring that reveals the tint.

        The ring is a soft gradient both ahead of and behind the leading edge:
          - Outer glow bands (ahead): fade from bright → transparent
          - Inner glow bands (behind): fade from bright → tint color
          - Filled interior behind everything: solid tint
        No hard edge anywhere — the whole ring is a smooth gradient bloom.
        """
        self._tint_canvas.delete("ripple")

        cx = self._screen_w / 2
        cy = self._screen_h / 2
        # Max radius = corner distance so the circle covers the whole screen
        max_radius = math.hypot(cx, cy)
        radius = max_radius * progress

        if radius < 1:
            return

        # 1. Filled interior (the tint reveal)
        inner_radius = max(1, radius - RIPPLE_GLOW_BANDS * RIPPLE_GLOW_WIDTH)
        self._tint_canvas.create_oval(
            cx - inner_radius, cy - inner_radius,
            cx + inner_radius, cy + inner_radius,
            fill=TINT_COLOR, outline="", tags="ripple",
        )

        # 2. Inner glow bands (behind the edge — bright → tint)
        for i in range(RIPPLE_GLOW_BANDS):
            band_radius = radius - i * RIPPLE_GLOW_WIDTH
            if band_radius < 1:
                break
            t = i / max(1, RIPPLE_GLOW_BANDS - 1)
            color = _lerp_color(RIPPLE_EDGE_COLOR, TINT_COLOR, t)
            self._tint_canvas.create_oval(
                cx - band_radius, cy - band_radius,
                cx + band_radius, cy + band_radius,
                fill="", outline=color, width=2, tags="ripple",
            )

        # 3. Outer glow bands (ahead of the edge — bright → transparent key)
        for i in range(RIPPLE_GLOW_BANDS):
            band_radius = radius + (i + 1) * RIPPLE_GLOW_WIDTH
            t = (i + 1) / RIPPLE_GLOW_BANDS
            color = _lerp_color(RIPPLE_EDGE_COLOR, self._transparent_key, t)
            self._tint_canvas.create_oval(
                cx - band_radius, cy - band_radius,
                cx + band_radius, cy + band_radius,
                fill="", outline=color, width=2, tags="ripple",
            )

    def _finalize_ripple(self):
        """Replace the ripple ovals with a solid tint background."""
        self._tint_canvas.delete("ripple")
        self._tint_canvas.configure(bg=TINT_COLOR)
        # Remove the transparent key since the whole canvas is now tinted
        self._tint_win.attributes("-transparentcolor", "")

    def _reset_tint_canvas(self):
        """Reset tint canvas to transparent for next activation."""
        self._tint_canvas.delete("ripple")
        self._tint_canvas.configure(bg=self._transparent_key)
        self._tint_win.attributes("-transparentcolor", self._transparent_key)

    # -- Bar mode switches (Tk thread) -------------------------------------

    def _apply_glow_mode(self):
        """Show the single breathing glow rectangle, hide pulse bands."""
        if not self._bar_canvas:
            return
        self._bar_canvas.itemconfig(self._bar_rect, state="normal")
        for r in self._pulse_rects:
            self._bar_canvas.itemconfig(r, state="hidden")

    def _apply_pulse_mode(self):
        """Show the pulse bands, hide the glow rectangle."""
        if not self._bar_canvas:
            return
        self._bar_canvas.itemconfig(self._bar_rect, state="hidden")
        for r in self._pulse_rects:
            self._bar_canvas.itemconfig(r, state="normal")

    # -- Animations (Tk thread) --------------------------------------------

    def _update_breathing_glow(self):
        """Oscillate bar window alpha with sin(time)."""
        t = time.time() * BAR_BREATHE_HZ * 2 * math.pi
        alpha = BAR_ALPHA_LO + (BAR_ALPHA_HI - BAR_ALPHA_LO) * (0.5 + 0.5 * math.sin(t))
        self._set_bar_alpha(alpha)

    def _update_scanning_pulse(self):
        """Sweep a bright Gaussian region across the pulse bands."""
        if not self._pulse_rects:
            return
        t = (time.time() * PULSE_HZ) % 1.0
        # Bounce: 0→1→0
        pos = t * 2 if t < 0.5 else 2 - t * 2
        center = pos * PULSE_BANDS
        sigma = PULSE_BANDS * PULSE_WIDTH_FRAC

        for i, rect in enumerate(self._pulse_rects):
            dist = abs(i - center) / max(sigma, 0.1)
            brightness = math.exp(-dist * dist)
            color = _lerp_color(PULSE_COLOR_DIM, PULSE_COLOR_BRIGHT, brightness)
            self._bar_canvas.itemconfig(rect, fill=color)

        # Keep bar visible at a moderate alpha during pulse
        self._set_bar_alpha(0.35)

    def _update_breathing_tint(self):
        """Oscillate tint alpha for thinking state."""
        t = time.time() * 1.0 * 2 * math.pi  # 1 Hz
        alpha = TINT_ALPHA_THINKING_LO + (
            (TINT_ALPHA_THINKING_HI - TINT_ALPHA_THINKING_LO) *
            (0.5 + 0.5 * math.sin(t))
        )
        self._set_tint_alpha(alpha)

    # -- Main tick (Tk thread) ---------------------------------------------

    def _tick(self):
        if not self._running:
            return

        now = time.time()
        want = self._want_state
        cur = self._current_state

        # ---- State transitions ----
        if want != cur:
            self._transition_start = now
            prev = cur
            self._current_state = want

            if want == OverlayState.SLEEPING:
                # Immediate hide (DISMISSING handles the fade, this is the fallback)
                self._hide_tint()
                self._hide_bar()
                self._reset_tint_canvas()

            elif want == OverlayState.BOOTING:
                self._reset_tint_canvas()
                # For booting, use solid tint bg immediately (no ripple)
                self._tint_canvas.configure(bg=TINT_COLOR)
                self._tint_win.attributes("-transparentcolor", "")
                self._set_tint_alpha(0.0)
                self._show_tint()
                self._apply_pulse_mode()
                self._show_bar()

            elif want == OverlayState.WAKING:
                self._reset_tint_canvas()
                self._set_tint_alpha(TINT_ALPHA_TARGET)
                self._show_tint()
                # Bar stays hidden during ripple

            elif want == OverlayState.LISTENING:
                if prev == OverlayState.WAKING:
                    self._finalize_ripple()
                self._set_tint_alpha(TINT_ALPHA_TARGET)
                self._show_tint()
                self._apply_glow_mode()
                self._show_bar()

            elif want == OverlayState.THINKING:
                self._apply_pulse_mode()
                self._show_bar()
                self._show_tint()

            elif want == OverlayState.SPEAKING:
                self._apply_glow_mode()
                self._set_tint_alpha(TINT_ALPHA_TARGET)
                self._show_tint()
                self._show_bar()

            elif want == OverlayState.DISMISSING:
                pass  # fade handled below

        # ---- Per-frame animation for current state ----
        elapsed = now - self._transition_start

        if self._current_state == OverlayState.SLEEPING:
            pass  # nothing to do

        elif self._current_state == OverlayState.BOOTING:
            # Slow tint fade-in over 1 second, then breathing
            if elapsed < 1.0:
                self._set_tint_alpha(TINT_ALPHA_TARGET * (elapsed / 1.0))
                self._set_bar_alpha(0.35 * (elapsed / 1.0))
            else:
                self._update_breathing_tint()
            self._update_scanning_pulse()

        elif self._current_state == OverlayState.WAKING:
            # Accelerating ripple
            if elapsed < RIPPLE_DURATION:
                progress = (elapsed / RIPPLE_DURATION) ** RIPPLE_ACCEL
                self._draw_ripple(progress)
            else:
                # Ripple done → auto-transition to LISTENING
                self._want_state = OverlayState.LISTENING

        elif self._current_state == OverlayState.LISTENING:
            self._update_breathing_glow()

        elif self._current_state == OverlayState.THINKING:
            self._update_breathing_tint()
            self._update_scanning_pulse()

        elif self._current_state == OverlayState.SPEAKING:
            self._update_breathing_glow()

        elif self._current_state == OverlayState.DISMISSING:
            if elapsed < TINT_FADE_OUT_DURATION:
                frac = 1.0 - (elapsed / TINT_FADE_OUT_DURATION)
                self._set_tint_alpha(TINT_ALPHA_TARGET * frac)
                self._set_bar_alpha(BAR_ALPHA_HI * frac)
            else:
                # Fade done → sleep
                self._hide_tint()
                self._hide_bar()
                self._reset_tint_canvas()
                self._current_state = OverlayState.SLEEPING
                self._want_state = OverlayState.SLEEPING

        self._root.after(TICK_MS, self._tick)

    # -- Public API (thread-safe, just sets flags) -------------------------

    def show(self):
        """Show the overlay in listening/active mode."""
        self._want_state = OverlayState.LISTENING

    def show_loading(self, text: str = ""):
        """Show a loading/processing state.

        Maps to:
          - 'Waking' or similar → WAKING (ripple)
          - 'Thinking' → THINKING (breathing + pulse)
          - Anything else (boot, reboot) → BOOTING
        """
        self._loading_text = text
        lower = text.lower()
        if "waking" in lower or "wake" in lower:
            self._want_state = OverlayState.WAKING
        elif "thinking" in lower or "processing" in lower:
            self._want_state = OverlayState.THINKING
        else:
            self._want_state = OverlayState.BOOTING

    def hide_loading(self):
        """Transition from loading/thinking to speaking."""
        self._want_state = OverlayState.SPEAKING

    def hide(self):
        """Dismiss the overlay with a fade-out."""
        if self._current_state == OverlayState.SLEEPING:
            return
        self._want_state = OverlayState.DISMISSING

    # -- Lifecycle ---------------------------------------------------------

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
        self._want_state = OverlayState.SLEEPING
        if self._root:
            try:
                self._root.quit()
            except Exception:
                pass
