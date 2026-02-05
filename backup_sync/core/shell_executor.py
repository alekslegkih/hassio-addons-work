#!/usr/bin/env python3
"""
Safe shell command execution utilities.
Used for running system commands like mount, lsblk, etc.
"""

import subprocess
import logging
from typing import Tuple, Optional, List

# Получаем логгер через get_logger для согласованности
from .logger import get_logger  # ✅ ДОБАВЛЕНО для согласованности

logger = get_logger(__name__)  # ✅ ИСПРАВЛЕНО для согласованности

def run_command(
    command: List[str],
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 30
) -> Tuple[bool, str, str]:
    """
    Safely execute a shell command.
    
    Args:
        command: Command and arguments as list
        check: If True, raise exception on non-zero exit code
        capture_output: If True, capture stdout/stderr
        timeout: Command timeout in seconds
    
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        logger.debug(f"Running command: {' '.join(command)}")
        
        result = subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )
        
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""
        
        if stdout:
            logger.debug(f"Command stdout: {stdout}")
        if stderr:
            logger.debug(f"Command stderr: {stderr}")
        
        return True, stdout, stderr
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed with code {e.returncode}: {e.stderr}"
        logger.error(error_msg)
        return False, e.stdout.strip() if e.stdout else "", e.stderr.strip() if e.stderr else ""
        
    except subprocess.TimeoutExpired as e:
        error_msg = f"Command timed out after {timeout}s"
        logger.error(error_msg)
        return False, "", error_msg
        
    except Exception as e:
        error_msg = f"Command execution error: {e}"
        logger.error(error_msg)
        return False, "", str(e)

def check_command_available(command: str) -> bool:
    """
    Check if a command is available in the system.
    
    Args:
        command: Command name to check
    
    Returns:
        True if command exists
    """
    try:
        subprocess.run(
            ["which", command],
            check=True,
            capture_output=True,
            timeout=5
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except Exception:
        return False

# Example usage:
# success, stdout, stderr = run_command(["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT"])