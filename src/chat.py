import os, sys, unicodedata as ud
from dotenv import load_dotenv
from typing import List, Dict
from anthropic import Anthropic
from .log import jdump

import asyncio, json
import sys
import re
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

LAST_RACE_ID = None              
LAST_PLAN_ARGS = None

RACE_ALIASES = {
    "monza": "demo_monza_2024",
    "italia": "demo_monza_2024",
    "mexico": "demo_mexico_2024",
    "ciudad de mexico": "demo_mexico_2024",
    "cdmx": "demo_mexico_2024",
}

DEFAULT_PLAN = {
    "base_laptime_s": 80.0,
    "deg_soft_s": 0.12,
    "deg_medium_s": 0.08,
    "deg_hard_s": 0.05,
    "min_stint_laps": 10,
    "max_stint_laps": 30,
    "max_stops": 2,
}

PRESETS = {
    "demo_monza_2024": {
        "base_laptime_s": 79.8,
        "deg_soft_s": 0.13,
        "deg_medium_s": 0.09,
        "deg_hard_s": 0.06,
        "min_stint_laps": 9,
        "max_stint_laps": 28,
        "max_stops": 2,
    },
    "demo_mexico_2024": {
        "base_laptime_s": 80.0,
        "deg_soft_s": 0.12,
        "deg_medium_s": 0.08,
        "deg_hard_s": 0.05,
        "min_stint_laps": 10,
        "max_stint_laps": 30,
        "max_stops": 2,
    },
}

def _merge_params(race_id: str, overrides: dict) -> dict:
    # orden: default -> preset pista -> overrides del usuario
    out = DEFAULT_PLAN.copy()
    if race_id in PRESETS:
        out.update(PRESETS[race_id])
    for k, v in overrides.items():
        if v is not None:
            out[k] = v
    return out

def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None

def _find_number_after(t: str, kws: list[str]) -> float | None:
    for kw in kws:
        m = re.search(rf"{kw}\s*[=:]?\s*(-?\d+(?:[.,]\d+)?)", t)
        if m: return _to_float(m.group(1))
    return None

def _find_int_after(t: str, kws: list[str]) -> int | None:
    for kw in kws:
        m = re.search(rf"{kw}\s*[=:]?\s*(\d+)", t)
        if m:
            try: return int(m.group(1))
            except Exception: pass
    return None

def _find_int_before(t: str, kws_pattern: str) -> int | None:
    # captura "3 paradas", "2 stops", etc.
    m = re.search(rf"(\d+)\s+(?:{kws_pattern})\b", t)
    if m:
        try: return int(m.group(1))
        except Exception: return None
    return None

_WORD2NUM = {"una":1, "uno":1, "dos":2, "tres":3, "cuatro":4}
def _find_word_number_paradas(t: str) -> int | None:
    m = re.search(r"\b(una|uno|dos|tres|cuatro)\s+paradas?\b", t)
    if m: return _WORD2NUM.get(m.group(1))
    return None

def _format_strategy_txt(d: dict, used: dict) -> str:
    
    lines = []
    rid = d.get("race_id", "?")
    lines.append(f"Estrategia para {rid}:")
    for stint in d.get("strategy", []):
        lines.append(f"  • {stint}")
    if d.get("stop_laps"):
        laps = ", ".join(map(str, d["stop_laps"]))
        lines.append(f"Paradas en vueltas: {laps}")
    if "predicted_total_s" in d:
        lines.append(f"Tiempo total estimado: {d['predicted_total_s']:.2f} s")
    
    lines.append("")
    lines.append("Parametros usados (auto-relleno si no los diste):")
    lines.append(f"  base_laptime_s: {used['base_laptime_s']}  (tiempo base por vuelta)")
    lines.append(f"  deg_soft_s:     {used['deg_soft_s']}    (degradación s/vuelta)")
    lines.append(f"  deg_medium_s:   {used['deg_medium_s']}")
    lines.append(f"  deg_hard_s:     {used['deg_hard_s']}")
    lines.append(f"  min_stint_laps: {used['min_stint_laps']}")
    lines.append(f"  max_stint_laps: {used['max_stint_laps']}")
    lines.append(f"  max_stops:      {used['max_stops']}")
    return "\n".join(lines)

def explain_last_plan() -> str:
    if not LAST_RACE_ID or not LAST_PLAN_ARGS:
        return "Aun no tengo una estrategia calculada. Pide una (por ejemplo: 'estrategia monza a dos paradas')."
    txt = [
        "Como interpreto los parametros:",
        "• base_laptime_s: ritmo 'limpio' sin desgaste ni tráfico.",
        "• deg_*_s: cuanto se hace más lenta cada vuelta por desgaste (s/vuelta).",
        "• min/max_stint_laps: limites de vueltas por stint.",
        "• max_stops: tope de paradas a optimizar.",
        "",
        "De donde salen:",
        "• Si no escribes numeros, uso presets por circuito (o defaults genericos).",
        "• Si das numeros, tus valores pisan los presets.",
        "",
        "Ultimos usados:"
    ]
    for k, v in LAST_PLAN_ARGS.items():
        txt.append(f"  - {k}: {v}")
    return "\n".join(txt)



load_dotenv()

server = StdioServerParameters(command=sys.executable, args=["-m", "src.mcp_f1_server"])

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    print("ERROR: Falta ANTHROPIC_API_KEY en .env"); sys.exit(1)
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")

client = Anthropic(api_key=API_KEY)


def _mcp_text(resp):
    parts = getattr(resp, "content", []) or []
    out = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text":
            out.append(p.get("text", ""))
        elif getattr(p, "type", None) == "text":
            out.append(getattr(p, "text", ""))
    return "\n".join(out).strip()

def _load_peers():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "peers.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    
def _build_transport(cfg: dict):
    
    t = (cfg.get("type") or "stdio").lower()
    if t == "stdio":
        command = cfg["command"]
        args = cfg.get("args", [])
        cwd = cfg.get("cwd")
        return ("stdio", StdioServerParameters(command=command, args=args, cwd=cwd))
    if t == "sse":
        url = cfg.get("url")
        if not url:
            raise ValueError("Peer 'sse' requiere 'url'")
        return ("sse", url)
    raise ValueError(f"Tipo de peer no soportado: {t}")


def peer_call(alias: str, tool: str | None, args: dict | None) -> str:
    peers = _load_peers()
    if alias not in peers:
        return f"[peer:{alias}] not found in peers.json"

    kind, param = _build_transport(peers[alias])

    async def _run():
        async with AsyncExitStack() as stack:
            if kind == "stdio":
                read, write = await stack.enter_async_context(stdio_client(param))
            else:  # kind == "sse"
                read, write = await stack.enter_async_context(sse_client(url=param))

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            if not tool:
                tools = await session.list_tools()
                return "[TOOLS] " + ", ".join(t.name for t in tools.tools)

            resp = await session.call_tool(tool, args or {})
            return _mcp_text(resp)

    return asyncio.run(_run())


    return asyncio.run(_run())

def sanitize(s: str) -> str:

    if not isinstance(s, str):
        s = str(s)
    s = ud.normalize("NFC", s)
   
    return s.encode("utf-8", "ignore").decode("utf-8")

def push(hist: List[Dict[str, str]], role: str, content: str):
    hist.append({"role": role, "content": sanitize(content)})
    
    if len(hist) > 8:
        del hist[:-8]

def _norm(txt: str) -> str:
    
    t = txt.lower()
    t = ud.normalize("NFD", t)
    t = "".join(c for c in t if ud.category(c) != "Mn")
    return t.strip()

def try_nl_command(user_text: str) -> str | None:
    t = _norm(user_text)

    
    talks_music = (
        "spotify" in t or
        re.search(r"\b(cancion|musica|tema|track|song|rol(a)?)\b", t) is not None
    )

    if talks_music:
       
        if re.search(r"\b((cambia(r)?)\s*(de|la)?\s*(cancion|tema|rola)|pasa(r)?\s*(la)?\s*(cancion|tema|rola)|avanza(r)?\s*(la)?\s*(cancion|tema|rola)|salta(r)?\s*(la)?\s*(cancion|tema|rola)|siguiente|next|skip)\b", t):
            return peer_call("spotify", "next_track", {})

        # anterior
        if re.search(r"\b(anterior|prev(ious)?|regresa(r)?)\b", t):
            return peer_call("spotify", "previous_track", {})

        # pausar / continuar
        if re.search(r"\b(pausa(r)?|pause|deten(er)?)\b", t):
            return peer_call("spotify", "pause_track", {})
        if re.search(r"\b(reanuda(r)?|resume|continua(r)?|play)\b", t):
            return peer_call("spotify", "resume_track", {})

        # que suena / cancion actual
        if re.search(r"(que suena|cancion actual|que estoy escuchando|currently playing)", t):
            return peer_call("spotify", "current_track", {})

        # reproducir algo específico: "pon X", "reproduce X", "play X"
        m = re.search(r"\b(pon|reproduce|play)\s+(.+)", t)
        if m:
            query = m.group(2).strip().strip(".!?")
            if query:
                return peer_call("spotify", "search_and_play", {"query": query})

    # ---------- F1 ----------
    if re.search(r"\b(estrategia|plan|stint(s)?|paradas|pit\s*stops?)\b", t):
        
        race_id = None
        m = re.search(r"(demo_[a-z0-9_\-]+_2024)", t)
        if m:
            race_id = m.group(1)
        else:
            for alias, rid in RACE_ALIASES.items():
                if alias in t:
                    race_id = rid
                    break
        global LAST_RACE_ID
        if not race_id and LAST_RACE_ID:
            race_id = LAST_RACE_ID
        if not race_id:
            
            return f1_call("get_calendar", {"season": 2024})

       
        base = _find_number_after(t, ["vuelta base", "tiempo base", "base", "base time", "base lap"])
        dS   = _find_number_after(t, ["soft", "suave", "blanda", "degradacion soft", "deg soft"])
        dM   = _find_number_after(t, ["medium", "media", "degradacion medium", "deg medium"])
        dH   = _find_number_after(t, ["hard", "dura", "degradacion hard", "deg hard"])
        minL = _find_int_after(t, ["min stint", "stint minimo", "minimo", "min"])
        maxL = _find_int_after(t, ["max stint", "stint maximo", "maximo", "max"])

        # stops: acepta "paradas 3", "3 paradas", "dos paradas", etc.
        stops = _find_int_after(t, ["paradas", "stops", "pit stops"])
        if stops is None:
            stops = _find_int_before(t, r"paradas?|stops?")
        if stops is None:
            stops = _find_word_number_paradas(t)

        overrides = {
            "base_laptime_s": base,
            "deg_soft_s": dS,
            "deg_medium_s": dM,
            "deg_hard_s": dH,
            "min_stint_laps": minL,
            "max_stint_laps": maxL,
            "max_stops": stops,
        }
        used = _merge_params(race_id, overrides)

        
        out = f1_call("recommend_strategy", {"race_id": race_id, **used})
        
        global LAST_PLAN_ARGS
        LAST_RACE_ID = race_id
        LAST_PLAN_ARGS = {"race_id": race_id, **used}

        
        try:
            d = json.loads(out)
            if isinstance(d, dict) and d.get("ok"):
                return _format_strategy_txt(d, used)
        except Exception:
            pass
        return out
      
    if re.search(r"\b(explica|explicame|como calculaste|de donde salen|parametros)\b", t) and LAST_RACE_ID:
        return explain_last_plan()

    return None



def run_chat():
    history: List[Dict[str, str]] = []
    print("Chat MCP-Proy1 (escribe 'exit' para salir)")
    while True:
        try:
            user = input("> ")
            if user.startswith("/peer"):
                out = handle_peer_cmd(user)
                print(out)
                continue
            if user.startswith("/f1"):
                out = handle_f1_command(user)
                print(out)
                continue
            routed = try_nl_command(user)
            if routed is not None:
                print(routed)
                jdump({"type": "nl_dispatch", "input": sanitize(user), "output": sanitize(routed)})
                continue
        except EOFError:
            break
        if user is None:
            continue
        user = user.strip()
        if user.lower() in ("exit", "quit"):
            break

        push(history, "user", user)

        try:
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
        except Exception as e:
            print(f"[LLM no disponible] {e}")
            jdump({"type": "llm_error", "request": sanitize(user), "error": str(e)})
          
            continue


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
            if tool in ("get_race", "recommend_strategy") and "race_id" in args:
                global LAST_RACE_ID
                LAST_RACE_ID = args["race_id"]
            resp = await session.call_tool(tool, args)
            return _mcp_text(resp)
    return asyncio.run(_run())


def handle_peer_cmd(line: str) -> str:
    # Sintaxis:
    # /peer <alias> tools
    # /peer <alias> call <toolName> <jsonArgs>

    parts = line.strip().split(maxsplit=3)
    if len(parts) < 3:
        return "Uso: /peer <alias> [tools|call|calendar|race|plan] ..."
    alias, sub = parts[1], parts[2].lower()

    if sub == "tools":
        return peer_call(alias, None, None)

    if sub == "call":
         # Sintaxis: /peer <alias> call <toolName> <jsonArgs>
        if len(parts) != 4:
            return "Uso: /peer <alias> call <toolName> <jsonArgs>"
        rest = parts[3].strip()
        space_idx = rest.find(" ")
        if space_idx == -1:
            return "Uso: /peer <alias> call <toolName> <jsonArgs>"
        toolName = rest[:space_idx]
        jsonArgs = rest[space_idx+1:].strip()
        try:
            tool_args = json.loads(jsonArgs)
        except Exception as e:
            return f"JSON inválido: {e}"
        return peer_call(alias, toolName, tool_args)


    if sub == "calendar":
        if len(parts) != 4: return "Uso: /peer <alias> calendar <season>"
        return peer_call(alias, "get_calendar", {"season": int(parts[3])})
    if sub == "race":
        if len(parts) != 4: return "Uso: /peer <alias> race <race_id>"
        return peer_call(alias, "get_race", {"race_id": parts[3]})
    if sub == "plan":
        # /peer <alias> plan <race_id> <base> <degS> <degM> <degH> <min> <max> <maxStops>
        toks = parts[3].split()
        if len(toks) != 9:
            return "Uso: /peer <alias> plan <race_id> <base> <degS> <degM> <degH> <min> <max> <maxStops>"
        race_id, base, dS, dM, dH, minL, maxL, maxStops = toks[0], *toks[1:]
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
        return peer_call(alias, "recommend_strategy", args)

    return "Comando /peer desconocido."

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
