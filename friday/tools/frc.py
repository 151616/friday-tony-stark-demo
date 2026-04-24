"""
FRC Domain — Tools for building, deploying, and simulating FIRST Robotics Competition code.
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("friday-agent")

def _run_gradle(project_path: str, command: str) -> str:
    path = Path(project_path)
    if not path.exists() or not path.is_dir():
        return f"Error: Project path '{project_path}' does not exist or is not a directory."
        
    gradlew_path = path / "gradlew.bat"
    if not gradlew_path.exists():
        return f"Error: Could not find gradlew.bat in '{project_path}'. Are you sure this is the FRC project root?"

    try:
        result = subprocess.run(
            [str(gradlew_path), command],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # Gradle outputs can be very long. We just want the BUILD SUCCESSFUL/FAILED part 
        # and any immediate errors.
        lines = result.stdout.splitlines()
        summary = "\n".join(lines[-20:]) if len(lines) > 20 else result.stdout
        
        if result.returncode == 0:
            return f"BUILD SUCCESSFUL.\n\nSummary:\n{summary}"
        else:
            errors = result.stderr if result.stderr else summary
            return f"BUILD FAILED.\n\nErrors:\n{errors}"
            
    except subprocess.TimeoutExpired:
        return f"Error: The Gradle command '{command}' timed out after 2 minutes."
    except Exception as e:
        return f"Error running Gradle: {e}"


def register(mcp):

    @mcp.tool()
    def build_frc_code(project_path: str) -> str:
        """
        Run the Gradle build command for an FRC robot project.
        Use this when the user asks to compile or check the robot code for errors.
        If you do not know the project path, you MUST ask the user for the absolute path to their FRC code first.
        """
        logger.info(f"Building FRC code in {project_path}")
        return _run_gradle(project_path, "build")

    @mcp.tool()
    def deploy_frc_code(project_path: str) -> str:
        """
        Run the Gradle deploy command to push code to the RoboRIO.
        Use this when the user asks to deploy the robot code.
        If you do not know the project path, you MUST ask the user for the absolute path to their FRC code first.
        """
        logger.info(f"Deploying FRC code from {project_path}")
        return _run_gradle(project_path, "deploy")

    @mcp.tool()
    def start_frc_simulation(project_path: str) -> str:
        """
        Run the Gradle simulateJava command to launch the local physics simulation.
        Use this when the user asks to simulate the robot code.
        If you do not know the project path, you MUST ask the user for the absolute path to their FRC code first.
        """
        logger.info(f"Simulating FRC code in {project_path}")
        # Note: we use subprocess.Popen here because simulation stays open
        path = Path(project_path)
        if not path.exists():
            return f"Error: Project path '{project_path}' does not exist."
            
        gradlew_path = path / "gradlew.bat"
        try:
            subprocess.Popen(
                [str(gradlew_path), "simulateJava"],
                cwd=str(path),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            return "Successfully launched the FRC simulation in a new window."
        except Exception as e:
            return f"Error launching simulation: {e}"

    @mcp.tool()
    def launch_frc_dashboard(dashboard_name: str) -> str:
        """
        Launch a common FRC utility or dashboard (e.g., 'Driver Station', 'Elastic', 'AdvantageScope', 'Shuffleboard').
        """
        name = dashboard_name.lower()
        if "driver" in name or "station" in name:
            path = r"C:\Program Files (x86)\FRC Driver Station\DriverStation.exe"
        elif "elastic" in name:
            # Typical path if installed via shortcut, otherwise we fallback
            path = r"C:\Users\Public\Desktop\Elastic.lnk" 
        else:
            return f"I don't have a hardcoded path for the {dashboard_name} dashboard yet."
            
        if not Path(path).exists():
            return f"Error: Could not find the executable for {dashboard_name} at {path}."
            
        try:
            # We use os.startfile for Windows to properly handle .exe and .lnk
            import os
            os.startfile(path)
            return f"Successfully launched {dashboard_name}."
        except Exception as e:
            return f"Failed to launch {dashboard_name}: {e}"

