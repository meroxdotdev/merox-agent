"""Kubernetes / Talos / Flux tools."""
from tools.shell import run


DEFINITIONS = [
    {
        "name": "run_kubectl",
        "description": "Run a kubectl command against the K8s cluster. Prefix 'kubectl' is optional.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "e.g. 'get pods -A' or 'describe node talos-1'"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_flux",
        "description": "Run a flux CLI command. Prefix 'flux' is optional.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "e.g. 'get kustomizations -A' or 'reconcile ks flux-system'"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_talosctl",
        "description": "Run a talosctl command. Prefix 'talosctl' is optional.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "e.g. 'version' or 'get members'"},
            },
            "required": ["command"],
        },
    },
]


def handle(name: str, inp: dict) -> str:
    cmd = inp["command"]
    if name == "run_kubectl":
        cmd = cmd if cmd.startswith("kubectl") else f"kubectl {cmd}"
    elif name == "run_flux":
        cmd = cmd if cmd.startswith("flux") else f"flux {cmd}"
    elif name == "run_talosctl":
        cmd = cmd if cmd.startswith("talosctl") else f"talosctl {cmd}"
    return run(cmd)
