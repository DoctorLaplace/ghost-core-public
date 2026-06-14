# In agent/tools/terminal.py

import subprocess
import logging
import platform
import shlex

import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def execute_command(command: str, timeout: int = None, sandbox: bool = False) -> str:
    """
    Executes a shell command in the underlying operating system.

    IMPORTANT SECURITY WARNING: This function allows the agent to execute arbitrary
    code on the machine. It should only be used in a secure, sandboxed environment.

    The function captures and returns both the standard output and standard error
    of the command.

    Args:
        command (str): The shell command to execute. For example, 'ls -l' or 'dir'.
        timeout (int, optional): Maximum seconds to let the command run before killing it. If not provided, falls back to config.TERMINAL_TIMEOUT_SECONDS.
        sandbox (bool, optional): Whether to run the command inside the sandbox.

    Returns:
        str: A formatted string containing the command's stdout and stderr,
             or an error message if the command fails to execute.
    """
    if not command:
        return "Error: Received an empty command."

    if sandbox:
        from agent.effectors.sandbox import run_sandboxed
        active_timeout = timeout if timeout is not None else config.TERMINAL_TIMEOUT_SECONDS
        res = run_sandboxed(command, timeout=active_timeout)
        output = f"--- Terminal Output (Sandboxed) for '{command}' ---\n"
        if res["stdout"]:
            output += f"STDOUT:\n{res['stdout']}\n"
        if res["stderr"]:
            output += f"STDERR:\n{res['stderr']}\n"
        if not res["stdout"] and not res["stderr"]:
            output += "Command executed successfully with no output.\n"
        output += f"Return Code: {res['returncode']}"
        return output

    logger.info(f"Executing terminal command: '{command}'")

    try:
        # shlex.split helps to safely parse the command string,
        # which is safer than using shell=True, especially on Unix-like systems.
        # For Windows, some commands (like 'dir') are shell built-ins
        # and might require shell=True. We'll handle this based on OS.
        
        is_windows = platform.system() == "Windows"
        
        active_timeout = timeout if timeout is not None else config.TERMINAL_TIMEOUT_SECONDS
        
        # We'll use shell=True on Windows to allow for built-in commands like 'dir'
        # On other systems, we avoid it for better security by default.
        result = subprocess.run(
            command if is_windows else shlex.split(command),
            capture_output=True,
            text=True,
            timeout=active_timeout,  # Configurable or dynamic timeout to prevent hangs
            shell=is_windows, # Use shell=True only on Windows
            check=False # Do not raise exception on non-zero exit codes
        )

        output = f"--- Terminal Output for '{command}' ---\n"
        
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        
        if not result.stdout and not result.stderr:
            output += "Command executed successfully with no output.\n"
            
        output += f"Return Code: {result.returncode}"
        
        return output

    except FileNotFoundError:
        error_msg = f"Error: The command '{command.split()[0]}' was not found on the system's PATH."
        logger.error(error_msg)
        return error_msg
    except subprocess.TimeoutExpired:
        error_msg = f"Error: Command '{command}' timed out after {active_timeout} seconds."
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error: An unexpected error occurred while executing command '{command}': {e}"
        logger.error(error_msg)
        return error_msg

# Example usage for direct testing:
if __name__ == '__main__':
    print("Running terminal standalone test...")
    
    # Determine the appropriate command based on the OS
    list_files_command = "dir" if platform.system() == "Windows" else "ls -l"
    
    print(f"\n--- Testing command: '{list_files_command}' ---")
    output1 = execute_command(list_files_command)
    print(output1)
    
    print("\n--- Testing a command that produces an error ---")
    error_command = "non_existent_command_12345"
    output2 = execute_command(error_command)
    print(output2)

    print("\n--- Testing an empty command ---")
    output3 = execute_command("")
    print(output3)
    
    print("\n--- Testing a command with arguments ---")
    ping_command = "ping -c 1 google.com" if platform.system() != "Windows" else "ping -n 1 google.com"
    output4 = execute_command(ping_command)
    print(output4)
    
    print("\nStandalone test completed.")