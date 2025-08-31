import asyncio
from contextlib import AsyncExitStack
from typing import Any, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .log import jdump

def content_text(parts: Any) -> str:
   
    out: List[str] = []
    for p in getattr(parts, "content", []) or []:
        t = getattr(p, "type", None)
        if t == "text":
            out.append(getattr(p, "text", ""))
        elif isinstance(p, dict) and p.get("type") == "text":
            out.append(p.get("text", ""))
    return "\n".join(out).strip()

async def main():
    
    server = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "sandbox"],
        env=None,
    )

    async with AsyncExitStack() as stack:
        (read, write) = await stack.enter_async_context(stdio_client(server))
        session = await stack.enter_async_context(ClientSession(read, write))

        
        await session.initialize()

        
        tools_resp = await session.list_tools()
        tool_names = [t.name for t in tools_resp.tools]
        print("TOOLS:", tool_names)

        
        allowed = await session.call_tool("list_allowed_directories", {})
        print("ALLOWED DIRS:", content_text(allowed))

        
        await session.call_tool("create_directory", {"path": "sandbox/demo"})
        wr = await session.call_tool("write_file", {
            "path": "sandbox/demo/README.txt",
            "content": "Hola MCP Filesystem!\n"
        })
        jdump({"type":"mcp_call","server":"filesystem","tool":"write_file",
               "args":{"path":"sandbox/demo/README.txt"},
               "result_preview": content_text(wr)[:120]})

       
        rd = await session.call_tool("read_text_file", {
            "path": "sandbox/demo/README.txt"
        })
        txt = content_text(rd)
        print("READ README.txt =>")
        print(txt)
        jdump({"type":"mcp_call","server":"filesystem","tool":"read_text_file",
               "args":{"path":"sandbox/demo/README.txt"},
               "result_preview": txt[:120]})

        #
        ls = await session.call_tool("list_directory", {"path": "sandbox/demo"})
        print("LIST demo =>")
        print(content_text(ls))
        jdump({"type":"mcp_call","server":"filesystem","tool":"list_directory",
               "args":{"path":"sandbox/demo"},
               "result_preview": content_text(ls)[:120]})

if __name__ == "__main__":
    asyncio.run(main())
