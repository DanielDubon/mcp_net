
import os
from .mcp_f1_server import mcp  

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    mcp.run(transport="http", host=host, port=port)
    
