"""
Network tools for monitoring and connecting to Wi-Fi networks.
"""

import subprocess
import threading
import time
import logging
from datetime import datetime
from uuid import uuid4
from friday.tasking.models import TaskRecord
from friday.tasking.store import create_task, update_task

logger = logging.getLogger("friday-agent")

def _wifi_monitor_loop(ssid: str, task_id: str):
    """Background loop to monitor for a Wi-Fi SSID and connect when visible."""
    timeout_mins = 10
    start_time = time.time()
    
    while True:
        # Check if we've timed out
        if time.time() - start_time > timeout_mins * 60:
            # Mark task as failed
            from friday.tasking.store import load_task
            task = load_task(task_id)
            if task:
                task.status = "failed"
                task.final_summary = f"TIMEOUT: Stopped monitoring for '{ssid}' after {timeout_mins} minutes."
                update_task(task)
            return

        try:
            # Scan for networks
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if ssid in result.stdout:
                logger.info(f"Wi-Fi SSID '{ssid}' detected. Connecting...")
                # Attempt to connect
                conn_result = subprocess.run(
                    ["netsh", "wlan", "connect", f"name={ssid}"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Verify if the connection command succeeded
                if "completed successfully" in conn_result.stdout.lower() or conn_result.returncode == 0:
                    from friday.tasking.store import load_task
                    task = load_task(task_id)
                    if task:
                        task.status = "completed"
                        task.final_summary = f"Successfully connected to the {ssid} network."
                        update_task(task)
                    return
        except Exception as e:
            logger.error(f"Error in Wi-Fi monitor loop: {e}")
            
        # Wait 3 seconds before polling again
        time.sleep(3)


def register(mcp):

    @mcp.tool()
    def monitor_wifi_connection(ssid: str) -> str:
        """
        Monitor for a specific Wi-Fi network to appear and automatically connect to it.
        Use this when the user asks to connect to an FRC robot radio, a hotspot, or any Wi-Fi 
        network as soon as it boots up or comes online.
        
        Args:
            ssid: The exact name (SSID) of the Wi-Fi network to look for.
        """
        # Create a TaskRecord so the system can announce completion
        task_id = f"task_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:6]}"
        task = TaskRecord(
            task_id=task_id,
            goal=f"Monitor and connect to Wi-Fi: {ssid}",
            status="pending",
            mode="planner",
            source="voice",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            steps=[]
        )
        create_task(task)

        # Spawn the detached background thread
        thread = threading.Thread(
            target=_wifi_monitor_loop,
            args=(ssid, task_id),
            daemon=True
        )
        thread.start()

        return f"I have started monitoring for the '{ssid}' network in the background. I will let you know as soon as it connects."

