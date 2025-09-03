
import os
from .mcp_trivial_server import mcp  

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    transport = os.getenv("TRANSPORT", "sse") 
    mcp.run(transport=transport, host=host, port=port)
