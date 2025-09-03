
import os, json
from datetime import datetime, timezone
from fastmcp import FastMCP
from starlette.responses import PlainTextResponse
from starlette.requests import Request

mcp = FastMCP("trivial-mcp")

# --- Herramientas simples ---

@mcp.tool()
async def ping() -> str:
    return "pong"

@mcp.tool()
async def echo(text: str) -> str:
    return text

@mcp.tool()
async def sum_numbers(numbers: list[float]) -> str:
    s = float(sum(numbers or []))
    return json.dumps({"sum": s}, ensure_ascii=False)

@mcp.tool()
async def time_now() -> str:
    # ISO-8601 en UTC
    return datetime.now(timezone.utc).isoformat()


@mcp.custom_route("/health", methods=["GET"])
async def health(_req: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

if __name__ == "__main__":
    
    mcp.run()
