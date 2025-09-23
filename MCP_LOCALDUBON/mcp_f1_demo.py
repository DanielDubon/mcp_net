import asyncio
from contextlib import AsyncExitStack
from typing import Any, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .log import jdump

def content_text(resp: Any) -> str:
    out: List[str] = []
    for p in getattr(resp, "content", []) or []:
        if isinstance(p, dict) and p.get("type") == "text":
            out.append(p.get("text", ""))
        elif getattr(p, "type", None) == "text":
            out.append(getattr(p, "text", ""))
    return "\n".join(out).strip()

async def main():
    server = StdioServerParameters(command="python3", args=["-m", "src.mcp_f1_server"])
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools = await session.list_tools()
        print("TOOLS:", [t.name for t in tools.tools])

        cal = await session.call_tool("get_calendar", {"season": 2024})
        print("CAL 2024 =>"); print(content_text(cal))
        jdump({"type":"mcp_call","server":"f1","tool":"get_calendar","args":{"season":2024},
               "result_preview": content_text(cal)[:160]})

        race_id = "demo_mexico_2024"
        meta = await session.call_tool("get_race", {"race_id": race_id})
        print("RACE META =>"); print(content_text(meta))
        jdump({"type":"mcp_call","server":"f1","tool":"get_race","args":{"race_id":race_id},
               "result_preview": content_text(meta)[:160]})

        rec = await session.call_tool("recommend_strategy", {
            "race_id": race_id,
            "base_laptime_s": 80.0,
            "deg_soft_s": 0.12,
            "deg_medium_s": 0.08,
            "deg_hard_s": 0.05,
            "min_stint_laps": 10,
            "max_stint_laps": 30,
            "max_stops": 2
        })
        print("RECOMMEND =>"); print(content_text(rec))
        jdump({"type":"mcp_call","server":"f1","tool":"recommend_strategy",
               "args":{"race_id":race_id,"base_laptime_s":80.0,"min_stint_laps":10,"max_stint_laps":30,"max_stops":2},
               "result_preview": content_text(rec)[:180]})

if __name__ == "__main__":
    asyncio.run(main())
