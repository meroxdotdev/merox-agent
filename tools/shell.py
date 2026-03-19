"""Low-level shell execution used by all other tools."""
import os
import subprocess
from config import KUBECONFIG, TALOSCONFIG, INFRA_REPO


def run(cmd: str, cwd: str | None = None, timeout: int = 30) -> str:
    """Run a shell command, return combined stdout+stderr."""
    env = os.environ.copy()
    env["KUBECONFIG"] = KUBECONFIG
    env["TALOSCONFIG"] = TALOSCONFIG
    env["SOPS_AGE_KEY_FILE"] = f"{INFRA_REPO}/age.key"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd, env=env, timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if out and err:
            return f"{out}\n{err}"
        return out or err or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
