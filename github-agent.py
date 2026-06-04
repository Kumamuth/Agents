"""OpenAI Agents SDK agent wired to the GitHub MCP server.

Requires OPENAI_API_KEY and GitHub credentials in .env (project root).

Run from project root:
    uv run github-agent.py

Or with a custom prompt:
    uv run github-agent.py "List open pull requests and summarize the top 5"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from agents import Agent, Runner, trace
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

GITHUB_DIR = Path(__file__).resolve().parent
REPO_ROOT = GITHUB_DIR

load_dotenv(GITHUB_DIR / ".env", override=True)

GITHUB_SERVER_PARAMS = {
    "command": "uv",
    "args": ["run", str(GITHUB_DIR / "github-server.py")],
    "cwd": str(REPO_ROOT),
}


async def run_github_agent(
    request: str,
    model: str = "gpt-4o-mini",
) -> str:
    async with MCPServerStdio(
        params=GITHUB_SERVER_PARAMS,
        client_session_timeout_seconds=60,
    ) as mcp_server:
        agent = Agent(
            name="github_assistant",
            instructions=(
                "You are a GitHub assistant with MCP tools for repository metadata, "
                "issues, pull requests, comments, and PR creation. Always use the "
                "appropriate tool before answering. Summarize results clearly: number, "
                "title, state, author, and URL when available. If owner/repo are not "
                "provided in the user request, rely on GITHUB_OWNER and GITHUB_REPO from "
                "environment defaults. If a tool returns JSON with error=true, explain "
                "the failure and suggest fixes (token scopes, owner/repo, branch names)."
            ),
            model=model,
            mcp_servers=[mcp_server],
        )
        with trace("github_agent"):
            result = await Runner.run(agent, request)
        return result.final_output


def main() -> None:
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        request = (
            "List open pull requests (limit 5), then summarize title, author, "
            "and updated date for each."
        )
    print(asyncio.run(run_github_agent(request)))


if __name__ == "__main__":
    main()
