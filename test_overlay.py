"""
Overlay Test Script — cycle through all states without booting FRIDAY.

Usage:
    python test_overlay.py

Controls (press keys in the terminal):
    b = BOOTING        (breathing tint + scanning pulse)
    w = WAKING         (ripple animation)
    l = LISTENING      (steady tint + breathing glow)
    t = THINKING       (breathing tint + scanning pulse)
    s = SPEAKING       (steady tint + breathing glow)
    h = HIDE           (fade out → sleep)
    d = DEMO           (auto-cycle through all states)
    q = QUIT
"""

import time
import threading
import sys
from friday_overlay import FridayOverlay


def demo_cycle(overlay):
    """Automatically cycle through all states with pauses."""
    print("\n--- DEMO: Starting full state cycle ---\n")

    print("  BOOTING...")
    overlay.show_loading("Booting up...")
    time.sleep(3)

    print("  → HIDE (boot done)")
    overlay.hide()
    time.sleep(1.5)

    print("  WAKING (ripple)...")
    overlay.show_loading("Waking up...")
    time.sleep(1.5)

    print("  LISTENING...")
    overlay.show()
    time.sleep(3)

    print("  THINKING...")
    overlay.show_loading("Thinking...")
    time.sleep(3)

    print("  SPEAKING...")
    overlay.hide_loading()
    time.sleep(3)

    print("  DISMISSING...")
    overlay.hide()
    time.sleep(1)

    print("\n--- DEMO: Complete ---\n")


def main():
    overlay = FridayOverlay()
    overlay.start()

    # Give Tk a moment to initialize
    time.sleep(0.5)

    print("=" * 50)
    print("  FRIDAY Overlay Test")
    print("=" * 50)
    print()
    print("  b = BOOTING     (breathing tint + scanning pulse)")
    print("  w = WAKING      (ripple animation)")
    print("  l = LISTENING   (steady tint + breathing glow)")
    print("  t = THINKING    (breathing tint + scanning pulse)")
    print("  s = SPEAKING    (steady tint + breathing glow)")
    print("  h = HIDE        (fade out)")
    print("  d = DEMO        (auto-cycle all states)")
    print("  q = QUIT")
    print()

    try:
        while True:
            key = input("> ").strip().lower()

            if key == "b":
                print("  → BOOTING")
                overlay.show_loading("Booting up...")
            elif key == "w":
                print("  → WAKING (ripple)")
                overlay.show_loading("Waking up...")
            elif key == "l":
                print("  → LISTENING")
                overlay.show()
            elif key == "t":
                print("  → THINKING")
                overlay.show_loading("Thinking...")
            elif key == "s":
                print("  → SPEAKING")
                overlay.hide_loading()
            elif key == "h":
                print("  → HIDE")
                overlay.hide()
            elif key == "d":
                threading.Thread(target=demo_cycle, args=(overlay,), daemon=True).start()
            elif key == "q":
                print("  Shutting down...")
                break
            else:
                print("  Unknown key. Use b/w/l/t/s/h/d/q")

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        overlay.stop()
        print("  Done.")


if __name__ == "__main__":
    main()
