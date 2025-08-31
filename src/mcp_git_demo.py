import asyncio, os
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Any, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .log import jdump

def content_text(resp: Any) -> str:
    out: List[str] = []
    parts = getattr(resp, "content", []) or []
    for p in parts:
        if isinstance(p, dict):
            if p.get("type") == "text":
                out.append(p.get("text", ""))
        else:
            if getattr(p, "type", None) == "text":
                out.append(getattr(p, "text", ""))
    return "\n".join(out).strip()

async def main():
    
    demo_dir = Path("sandbox/git_demo")
    demo_dir.mkdir(parents=True, exist_ok=True)
    (demo_dir / "README.md").write_text("# git_demo via MCP\n\nHola Git MCP 👋\n", encoding="utf-8")

    
    server = StdioServerParameters(
        command="npx",
        args=["-y", "@mseep/git-mcp-server"],
        env={"MCP_LOG_LEVEL": "info"},
    )

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

       
        tools = await session.list_tools()
        print("TOOLS:", [t.name for t in tools.tools])

        
        r = await session.call_tool("git_set_working_dir", {"path": str(demo_dir.resolve())})
        print("SET WD =>", content_text(r))

        
        if not (demo_dir / ".git").exists():
            r = await session.call_tool("git_init", {"path": str(demo_dir.resolve())})
            print("INIT =>", content_text(r))

        
        r = await session.call_tool("git_status", {})
        print("STATUS (before add) =>\n", content_text(r))
        jdump({"type":"mcp_call","server":"git","tool":"git_status","args":{}, "result_preview": content_text(r)[:160]})

        
        r = await session.call_tool("git_add", {"files": ["README.md"]})
        print("ADD =>", content_text(r))
        jdump({"type":"mcp_call","server":"git","tool":"git_add","args":{"files":["README.md"]}, "result_preview": content_text(r)[:160]})

        
        msg = "feat(mcp): init git_demo with README via MCP"
        r = await session.call_tool("git_commit", {"message": msg})
        print("COMMIT =>", content_text(r))
        jdump({"type":"mcp_call","server":"git","tool":"git_commit","args":{"message": msg}, "result_preview": content_text(r)[:160]})

       
        r = await session.call_tool("git_log", {"maxCount": 1})
        print("LOG (last 1) =>\n", content_text(r))

if __name__ == "__main__":

    asyncio.run(main())
