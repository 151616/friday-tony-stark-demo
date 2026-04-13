# FRIDAY Overlay Rewrite Plan

## Overview
Replace the current floating pill widget (`friday_overlay.py`) with a fullscreen, click-through overlay that feels integrated into the screen itself — not a window sitting on top.

## Visual Design

### Activation Ripple
- Wake word triggers a **single blue ring** expanding from the center of the screen
- Ring **accelerates outward** using an ease-in curve (`progress ^ 2.5`) — starts slow, gets faster
- The ring **reveals the blue tint** as it passes: outside the ring is normal, inside turns blue
- As the ring grows, the blue area fills more of the screen until the entire screen is tinted
- **Gradient ring edge** — not a flat circle:
  - Outer edge: bright crisp blue (`#4a9eff`), thin (~2px) — the "wave front"
  - Just behind: soft gradient glow (~30-40px) blending from bright into the faint tint
  - Interior: steady faint tint color
  - Implemented as 3-5 concentric ovals tightly packed behind the leading edge, each color-lerped closer to the tint background — gives a convincing glow/gradient effect
- Total duration: ~0.6 seconds

### Blue Screen Tint
- Entire screen gets a very faint blue overlay (alpha ~0.08-0.12)
- Visible enough to clearly tell FRIDAY is active
- Subtle enough to read and use everything underneath
- Fades out over ~0.3s on dismissal

### Top Bar — Breathing Glow
- Thin strip across full screen width at the top (~40-50px tall)
- **No audio bars, no FFT, no mic needed** — purely time-based animation
- A soft blue glow that gently pulses (breathes) in opacity
- While LISTENING/SPEAKING: `sin(time)` oscillates alpha between ~0.15 and 0.25 at ~1Hz
- Semi-transparent, no solid background — just a soft blue band that fades in and out
- Implemented as a single filled rectangle with the bar window's alpha animated
- Near-zero CPU cost — one `sin()` call per frame, one alpha update

### Click-Through
- **ALL mouse clicks and keyboard input pass through** to apps underneath
- Uses Windows `WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOPMOST` flags
- Everything behind the overlay remains fully interactive at all times

## States and Transitions

```
SLEEPING --(boot)--> BOOTING --(ready)--> SLEEPING
                                              |
                                         (wake word)
                                              |
                                              v
                                           WAKING --(ripple done)--> LISTENING
                                                                        |
                                                                  (PROCESSING signal)
                                                                        |
                                                                        v
                                                                    THINKING
                                                                        |
                                                                  (SPEAKING signal)
                                                                        |
                                                                        v
                                                                    SPEAKING
                                                                        |
                                                                    (dismissal)
                                                                        |
                                                                        v
                                                                   DISMISSING --(fade done)--> SLEEPING
```

| State | Tint | Top Bar | Mic | Audio |
|---|---|---|---|---|
| SLEEPING | Hidden | Hidden | Off | None |
| BOOTING | Slow fade-in + breathing pulse | Scanning pulse (shimmer) | Off | None |
| WAKING | Ripple expanding (reveals tint) | Hidden | Off | Chime |
| LISTENING | Steady blue tint (~0.10) | Breathing glow (0.15 - 0.25) | Off | None |
| THINKING | Breathing pulse (0.10 - 0.14) | Scanning pulse (shimmer) | Off | None |
| SPEAKING | Steady blue tint (~0.10) | Breathing glow (0.15 - 0.25) | Off | None |
| DISMISSING | Fading out over 0.3s | Fading out | Off | None |

**No text anywhere** — all state communication is purely visual + the existing activation chime.
**No mic/FFT needed** — top bar is purely time-based animation, near-zero CPU cost.

## Technical Architecture

### Two-Window Approach
Both windows are `tk.Toplevel` under a hidden `tk.Tk()` root, sharing one `mainloop()`:

1. **Tint Window** — fullscreen, solid blue canvas fill (`#0a1428`), window alpha animated between 0.0-0.12. Handles the tint effect and ripple animation.

2. **Bar Window** — thin strip at top of screen, `-transparentcolor` set so background is invisible. Alpha animated via `sin(time)` for the breathing glow. Single blue filled rectangle.

Both get Win32 click-through flags applied to their HWNDs.

### Click-Through Implementation
```python
def _make_click_through(tk_window):
    tk_window.update_idletasks()
    hwnd = tk_window.winfo_id()
    hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
```

### Ripple That Reveals Tint
The tint window canvas background starts as the transparent key color. The ripple is a **filled blue oval with a gradient edge** that grows from the center — only the area inside the oval is blue. As the oval expands past screen edges, the entire canvas is blue.

```
progress = (elapsed / RIPPLE_DURATION) ** 2.5   # ease-in acceleration
radius = max_radius * progress
```

**Gradient ring implementation:** Each frame, draw the ripple as:
1. One large filled oval at `radius` — the tint interior
2. 3-5 concentric unfilled ovals just inside the leading edge, each ~8px apart
3. Outermost ring: bright `#4a9eff`, subsequent rings lerp toward tint color `#0a1428`
4. Creates a soft glow band (~30-40px) trailing behind the sharp leading edge

Once the ripple fills the screen, swap the canvas background to solid blue and delete all ovals — avoids drawing enormous shapes every frame during steady state.

### State Machine (Flag-Based)
Same pattern as current implementation — public methods only set flags, `_tick()` syncs everything on the Tk thread:

```python
def show(self):           # -> LISTENING
def show_loading(text):   # -> WAKING or THINKING (based on text)
def hide_loading():       # -> SPEAKING
def hide():               # -> DISMISSING -> auto SLEEPING
def start() / stop():     # lifecycle (unchanged)
```

### Performance Targets
- **20 FPS** tick rate (50ms interval) — smooth enough for subtle animations
- **No mic, no FFT, no PyAudio** — all animations are time-based (`sin()`, `time.time()`)
- **0% CPU while SLEEPING** — both windows withdrawn, tick still runs but does nothing
- **<1% CPU while active** — just alpha updates and one `sin()` call per frame

## Build Phases

### Phase 1 — Window Foundation
- Create two-window setup (tint + bar) with hidden root
- Apply `WS_EX_TRANSPARENT | WS_EX_LAYERED` click-through flags
- Add DPI awareness: `ctypes.windll.shcore.SetProcessDpiAwareness(2)`
- **Test:** overlay visible, all clicks pass through to desktop/apps

### Phase 2 — Ripple + Tint Reveal
- WAKING state draws expanding filled blue oval with gradient edge on tint canvas
- Acceleration curve: `progress ** 2.5`
- Gradient ring: 3-5 concentric ovals behind leading edge, color-lerped
- Inside oval = blue tint, outside = transparent
- When oval fills screen -> transition to LISTENING, solid blue background
- **Test:** ripple expands naturally with gradient edge, tint appears behind it

### Phase 3 — Tint Steady State + Fade Out
- LISTENING/SPEAKING: tint window alpha at ~0.10
- THINKING: tint alpha breathes between 0.10 and 0.14 using `sin(time)`
- DISMISSING: alpha fades from current -> 0.0 over 0.3s, then withdraw
- **Test:** tint visible but subtle, breathing noticeable, fade out smooth

### Phase 4 — Top Bar Breathing Glow
- Single blue filled rectangle spanning full bar window width
- Animate bar window alpha using `sin(time)` between 0.15 and 0.25 at ~1Hz
- No FFT, no mic, no PyAudio — purely time-based
- **Test:** soft blue glow pulses gently at the top of the screen, click-through works

### Phase 5 — Thinking + Booting Animations
- Both THINKING and BOOTING use the same visual style:
  - Top bar: scanning Gaussian pulse sweep (left -> right at 0.8Hz)
  - Tint: breathing alpha oscillation (0.10 - 0.14) using `sin(time)`
- BOOTING: tint fades in slowly first, then starts breathing + pulse
- THINKING: transitions from steady tint to breathing, glow swaps to pulse
- No text — purely visual feedback
- **Test:** smooth animation, clearly different from listening/speaking state

### Phase 6 — Integration
- Verify public API unchanged — no launcher changes needed
- Full flow test: boot -> sleep -> wake -> ripple -> listen -> think -> speak -> dismiss
- Test `on_processing` / `on_speaking` callbacks trigger correct transitions

### Phase 7 — Polish
- Tune alpha values against dark and light app backgrounds
- Tune ripple acceleration feel and gradient ring width
- Tune breathing glow speed and alpha range
- Test with fullscreen apps, games, video playback

## File Changes
- **`friday_overlay.py`** — complete rewrite (single file, same class name, same API)
- **`friday_launcher.py`** — no changes needed
- **`agent_friday.py`** — no changes needed

## Dependencies
```python
import ctypes
import math
import threading
import time
import tkinter as tk
from enum import Enum
import win32con
```

No `numpy`, `pyaudio`, or FFT — all animations are time-based.

## Class Structure
```
FridayOverlay
    __init__()
    _setup_window()              -- creates both windows, canvases, applies WS_EX flags
    _make_click_through()        -- helper for Win32 style flags
    _draw_ripple(progress)       -- expanding gradient ring on tint canvas
    _update_breathing_glow()     -- sin(time) alpha pulse on bar window
    _update_scanning_pulse()     -- shimmer sweep for thinking/booting
    _animate_tint_alpha(target)  -- fade/breathe tint in/out
    _tick()                      -- 20 FPS main loop, state machine dispatcher
    show() / hide() / show_loading() / hide_loading()  -- public API (unchanged)
    start() / stop()             -- lifecycle (unchanged)
```

## Known Limitations
- **Primary monitor only** — `winfo_screenwidth/height` returns primary display dimensions
- **Windows only** — relies on Win32 API for click-through flags
- **Tkinter rendering** — not GPU-accelerated, but 20 FPS is sufficient for subtle animations
- **Gradient ring is approximate** — Tkinter doesn't support real gradients, so the glow is faked with concentric ovals. At animation speed this looks convincing.
