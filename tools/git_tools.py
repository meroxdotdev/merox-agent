"""Git operations for infra and website repos."""
from tools.shell import run

DEFINITIONS = [
    {
        "name": "git_status",
        "description": "Show git status and last 5 commits of a repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Path to git repo, e.g. INFRA_REPO or WEBSITE_REPO"},
            },
            "required": ["repo"],
        },
    },
    {
        "name": "git_diff",
        "description": "Show uncommitted changes in a repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Path to git repo"},
            },
            "required": ["repo"],
        },
    },
    {
        "name": "git_log",
        "description": "Show recent git commit history of a repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Path to git repo"},
                "count": {"type": "integer", "description": "Number of commits (default 10)"},
            },
            "required": ["repo"],
        },
    },
    {
        "name": "git_commit_push",
        "description": "Stage all changes (git add -A), commit with message, and push to origin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Path to git repo"},
                "message": {"type": "string", "description": "Commit message"},
            },
            "required": ["repo", "message"],
        },
    },
]


def handle(name: str, inp: dict) -> str:
    repo = inp.get("repo", "")

    if name == "git_status":
        return run("git status --short && echo '---' && git log --oneline -5", cwd=repo)

    elif name == "git_diff":
        return run("git diff HEAD", cwd=repo)

    elif name == "git_log":
        n = inp.get("count", 10)
        return run(f"git log --oneline -{n}", cwd=repo)

    elif name == "git_commit_push":
        msg = inp["message"].replace('"', '\\"')
        results = []
        for cmd in [
            "git add -A",
            f'git commit -m "{msg}\n\nCo-Authored-By: Merox Agent <agent@merox.dev>"',
            "git push",
        ]:
            out = run(cmd, cwd=repo)
            results.append(f"$ {cmd.split(chr(10))[0]}\n{out}")
            if any(w in out.lower() for w in ["error", "fatal", "rejected"]):
                break
        return "\n\n".join(results)

    return f"Unknown git tool: {name}"
