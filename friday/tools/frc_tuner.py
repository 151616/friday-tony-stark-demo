"""
FRC AI Auto-Tuner - Analyzes NetworkTables step responses and plots graphs.
"""

import threading
import time
import logging
from datetime import datetime
from uuid import uuid4
import os
from pathlib import Path
from friday.tasking.models import TaskRecord
from friday.tasking.store import create_task, update_task

logger = logging.getLogger("friday-agent")

_REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = _REPO_ROOT / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

def _tuner_logging_loop(task_id: str, ip: str, p_key: str, target_key: str, actual_key: str, target_val: float, duration: float):
    """Logs NT data for `duration` seconds, generates a graph, and marks the task complete."""
    try:
        import ntcore
        import matplotlib.pyplot as plt
    except ImportError:
        logger.error("pyntcore or matplotlib not installed")
        from friday.tasking.store import load_task
        task = load_task(task_id)
        if task:
            task.status = "failed"
            task.final_summary = "Dependencies pyntcore and matplotlib are not installed."
            update_task(task)
        return

    # Initialize NetworkTables client
    inst = ntcore.NetworkTableInstance.getDefault()
    inst.setServer(ip)
    inst.startClient4("FridayAutoTuner")

    # Give it a second to connect
    time.sleep(1.0)
    
    if not inst.isConnected():
        logger.warning(f"Could not connect to NT server at {ip}")

    # Set up publishers and subscribers
    p_pub = inst.getDoubleTopic(p_key).publish()
    target_pub = inst.getDoubleTopic(target_key).publish()
    actual_sub = inst.getDoubleTopic(actual_key).subscribe(0.0)

    # We don't overwrite P value here, we just set the target to trigger the step response
    target_pub.set(target_val)

    # Logging loop
    start_time = time.time()
    times = []
    actuals = []
    targets = []

    logger.info(f"Started NT logging loop for {duration} seconds...")
    network_dropped = False
    
    while (time.time() - start_time) < duration:
        if not inst.isConnected():
            logger.error("NT connection dropped mid-test!")
            network_dropped = True
            break
            
        t = time.time() - start_time
        actual = actual_sub.get()
        
        times.append(t)
        actuals.append(actual)
        targets.append(target_val)
        
        time.sleep(0.02) # 50Hz polling

    # Stop client
    inst.stopClient()

    # Math Analysis
    max_overshoot = max(actuals) - target_val if actuals else 0
    overshoot_pct = (max_overshoot / target_val * 100) if target_val != 0 else 0
    steady_state_error = target_val - actuals[-1] if actuals else 0

    # Generate Graph
    plt.figure(figsize=(8, 5))
    plt.plot(times, actuals, label='Actual RPM', color='blue')
    plt.plot(times, targets, label='Target RPM', color='red', linestyle='--')
    plt.title(f"Step Response (Target: {target_val})")
    plt.xlabel("Time (s)")
    plt.ylabel("Value")
    plt.legend()
    plt.grid(True)
    
    graph_path = RUNTIME_DIR / f"step_response_{task_id}.png"
    plt.savefig(graph_path)
    plt.close()

    # Final Summary for Friday
    status_msg = "Step Response Complete."
    if network_dropped:
        status_msg = "NETWORK DISCONNECT ERROR: The test was aborted early because the connection to the RoboRIO dropped. Please check the radio and battery!"
        
    summary = (
        f"{status_msg} Graph saved to {graph_path}.\n"
        f"Mathematical Analysis (based on {len(actuals)} successful samples):\n"
        f"- Target Value: {target_val}\n"
        f"- Max Value Reached: {max(actuals) if actuals else 0:.2f}\n"
        f"- Max Overshoot: {max_overshoot:.2f} ({overshoot_pct:.1f}%)\n"
        f"- Final Steady-State Error: {steady_state_error:.2f}\n\n"
        f"You can now read this image file using a file reading tool if you wish, or just use the math above to suggest the next PID values."
    )

    from friday.tasking.store import load_task
    task = load_task(task_id)
    if task:
        task.status = "completed"
        task.final_summary = summary
        update_task(task)


def register(mcp):
    @mcp.tool()
    def run_pid_tuner(robot_ip: str, p_key: str, target_key: str, actual_key: str, target_val: float, duration: float = 3.0) -> str:
        """
        Run a step-response test to auto-tune a PID loop via NetworkTables.
        This spawns a background task that sets the target value, logs the actual sensor value at 50Hz for the given duration, and generates a graph.
        
        Args:
            robot_ip: The IP address of the RoboRIO (e.g. '10.94.77.2').
            p_key: The NetworkTables key for the P-value (e.g. '/SmartDashboard/Shooter/kP').
            target_key: The NetworkTables key for the target setpoint (e.g. '/SmartDashboard/Shooter/TargetRPM').
            actual_key: The NetworkTables key to read the actual sensor value (e.g. '/SmartDashboard/Shooter/ActualRPM').
            target_val: The numerical value to set the target to for the test.
            duration: How many seconds to log the data for (default 3.0). Increase for heavy mechanisms like flywheels.
        """
        task_id = f"tune_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:6]}"
        task = TaskRecord(
            task_id=task_id,
            goal=f"PID Auto-Tune step response test for {target_key}",
            status="pending",
            mode="planner",
            source="voice",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            steps=[]
        )
        create_task(task)

        thread = threading.Thread(
            target=_tuner_logging_loop,
            args=(task_id, robot_ip, p_key, target_key, actual_key, target_val, duration),
            daemon=True
        )
        thread.start()

        return f"I have started the {duration}-second step response test in the background. I will let you know when the graph is ready."

    @mcp.tool()
    def push_pid_values(robot_ip: str, p_key: str, p_val: float, i_key: str = "", i_val: float = 0.0, d_key: str = "", d_val: float = 0.0) -> str:
        """
        Push new PID values to NetworkTables. Use this after analyzing a step-response graph to adjust the tuning.
        
        Args:
            robot_ip: The IP address of the RoboRIO.
            p_key: NetworkTables key for kP.
            p_val: New kP value. Must be a safe, small float.
            i_key: (Optional) NetworkTables key for kI.
            i_val: (Optional) New kI value.
            d_key: (Optional) NetworkTables key for kD.
            d_val: (Optional) New kD value.
        """
        # Safety limit
        if p_val > 10.0 or p_val < 0.0:
            return "SAFETY ERROR: Refusing to push kP value outside of safe bounds (0.0 to 10.0)."
            
        try:
            import ntcore
        except ImportError:
            return "Error: pyntcore not installed."
            
        inst = ntcore.NetworkTableInstance.getDefault()
        inst.setServer(robot_ip)
        inst.startClient4("FridayAutoTunerPush")
        
        time.sleep(0.5) # Wait for connection
        
        inst.getDoubleTopic(p_key).publish().set(p_val)
        if i_key:
            inst.getDoubleTopic(i_key).publish().set(i_val)
        if d_key:
            inst.getDoubleTopic(d_key).publish().set(d_val)
            
        inst.stopClient()
        return f"Successfully pushed new PID values: kP={p_val}, kI={i_val}, kD={d_val}."
