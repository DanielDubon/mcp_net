import os, sys, unicodedata as ud
from dotenv import load_dotenv
from typing import List, Dict
from anthropic import Anthropic
from .log import jdump

import asyncio
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    print("ERROR: Falta ANTHROPIC_API_KEY en .env"); sys.exit(1)
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")

client = Anthropic(api_key=API_KEY)

def sanitize(s: str) -> str:

    if not isinstance(s, str):
        s = str(s)
    s = ud.normalize("NFC", s)
   
    return s.encode("utf-8", "ignore").decode("utf-8")

def push(hist: List[Dict[str, str]], role: str, content: str):
    hist.append({"role": role, "content": sanitize(content)})
    
    if len(hist) > 8:
        del hist[:-8]

def run_chat():
    history: List[Dict[str, str]] = []
    print("Chat MCP-Proy1 (escribe 'exit' para salir)")
    while True:
        try:
            user = input("> ")
            if user.startswith("/f1"):
                out = handle_f1_command(user)
                print(out)
                continue
        except EOFError:
            break
        if user is None:
            continue
        user = user.strip()
        if user.lower() in ("exit", "quit"):
            break

        push(history, "user", user)

        msg = client.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=history
        )
        reply = msg.content[0].text if msg.content else ""
        reply = sanitize(reply)
        print(reply)

        jdump({"type": "llm_exchange", "request": sanitize(user), "response": reply})
        push(history, "assistant", reply)
        
def _mcp_text(resp):
    parts = getattr(resp, "content", []) or []
    out = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text":
            out.append(p.get("text", ""))
        elif getattr(p, "type", None) == "text":
            out.append(getattr(p, "text", ""))
    return "\n".join(out).strip()

def f1_call(tool: str, args: dict) -> str:
    async def _run():
        server = StdioServerParameters(command="python3", args=["-m", "src.mcp_f1_server"])
        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(stdio_client(server))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            if tool == "__list__":
                tools = await session.list_tools()
                return "TOOLS: " + ", ".join(t.name for t in tools.tools)
            resp = await session.call_tool(tool, args)
            return _mcp_text(resp)
    return asyncio.run(_run())


def handle_f1_command(line: str) -> str:
    # Formatos soportados:
    # /f1 tools
    # /f1 calendar 2024
    # /f1 race demo_mexico_2024
    # /f1 plan demo_mexico_2024 80 0.12 0.08 0.05 10 30 2
    parts = line.strip().split()
    if len(parts) < 2:
        return "Uso: /f1 [tools|calendar|race|plan] ..."

    cmd = parts[1].lower()
    if cmd == "tools":
        return f1_call("__list__", {})
    if cmd == "calendar":
        if len(parts) != 3: return "Uso: /f1 calendar <season>"
        return f1_call("get_calendar", {"season": int(parts[2])})
    if cmd == "race":
        if len(parts) != 3: return "Uso: /f1 race <race_id>"
        return f1_call("get_race", {"race_id": parts[2]})
    if cmd == "plan":
        if len(parts) != 10:
            return "Uso: /f1 plan <race_id> <base> <degS> <degM> <degH> <minStint> <maxStint> <maxStops>"
        _, _, race_id, base, dS, dM, dH, minL, maxL, maxStops = parts
        args = {
            "race_id": race_id,
            "base_laptime_s": float(base),
            "deg_soft_s": float(dS),
            "deg_medium_s": float(dM),
            "deg_hard_s": float(dH),
            "min_stint_laps": int(minL),
            "max_stint_laps": int(maxL),
            "max_stops": int(maxStops),
        }
        return f1_call("recommend_strategy", args)

    return "Comando /f1 desconocido."


if __name__ == "__main__":
    try:
        run_chat()
    except KeyboardInterrupt:
        sys.exit(0)
