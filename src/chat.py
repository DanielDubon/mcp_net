import os, sys, unicodedata as ud
from dotenv import load_dotenv
from typing import List, Dict
from anthropic import Anthropic
from .log import jdump

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

if __name__ == "__main__":
    try:
        run_chat()
    except KeyboardInterrupt:
        sys.exit(0)
