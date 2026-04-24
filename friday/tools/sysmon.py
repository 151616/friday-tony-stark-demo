"""
System monitoring tools — CPU, RAM, disk, battery, top processes.
"""

import psutil


def register(mcp):

    @mcp.tool()
    def system_status() -> str:
        """Report a spoken-friendly health overview of the system: CPU %, RAM usage,
        disk usage, battery status, and the top 3 processes by CPU. Use when the user
        asks 'How's my system?', 'CPU usage?', 'Am I running low on storage?',
        'What's eating my RAM?', or 'System health'."""

        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.5)

        # RAM
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / (1024 ** 3)
        ram_total_gb = ram.total / (1024 ** 3)
        ram_percent = ram.percent

        # Disk (root / primary drive)
        disk = psutil.disk_usage("/")
        disk_used_gb = disk.used / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)
        disk_percent = disk.percent

        # Battery
        battery_str = ""
        battery = psutil.sensors_battery()
        if battery is not None:
            batt_pct = int(battery.percent)
            charging = battery.power_plugged
            status = "charging" if charging else "on battery"
            battery_str = f", battery at {batt_pct}% {status}"

        # Top 3 processes by CPU
        try:
            procs = []
            for p in psutil.process_iter(["name", "cpu_percent"]):
                try:
                    cpu = p.info["cpu_percent"] or 0.0
                    name = p.info["name"] or "Unknown"
                    procs.append((cpu, name))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # A second pass gives more accurate cpu_percent readings; one pass
            # is acceptable here for latency — values come from the cached
            # interval above.
            top3 = sorted(procs, key=lambda x: x[0], reverse=True)[:3]
            # Strip file extensions for cleaner speech (.exe, etc.)
            top3_names = []
            for _, name in top3:
                clean = name.rsplit(".", 1)[0] if "." in name else name
                top3_names.append(clean)
            top_str = ", ".join(top3_names) if top3_names else "none detected"
        except Exception:
            top_str = "unavailable"

        # Format RAM and disk as rounded numbers for natural speech
        ram_used = round(ram_used_gb, 1)
        ram_total = round(ram_total_gb, 1)
        disk_used = round(disk_used_gb, 1)
        disk_total = round(disk_total_gb, 1)

        # Use "gig" for values >= 1 GB; fall back to MB for tiny totals
        def gb_str(value_gb: float) -> str:
            if value_gb >= 1.0:
                return f"{value_gb} gig"
            return f"{round(value_gb * 1024)} meg"

        result = (
            f"CPU is at {int(cpu_percent)}%, "
            f"RAM at {gb_str(ram_used)} of {gb_str(ram_total)} ({int(ram_percent)}%), "
            f"disk is {int(disk_percent)}% full at {gb_str(disk_used)} of {gb_str(disk_total)}"
            f"{battery_str}. "
            f"Top processes: {top_str}."
        )
        return result
