# Project #1 – Networks
## Console Chat + MCP Servers (Filesystem/Git) + **F1 Strategy MCP**

This repository implements:
- A **console chat** connected to an LLM (Anthropic) with **interaction logs**.
- Example MCP clients for **Filesystem** and **Git** servers.
- A **custom MCP server** for **F1 strategy planning** (FastMCP) with a demo and chat-integrated commands.

---

## Repository Structure
```
mcp_net/
├─ src/
│  ├─ chat.py                # Console chat with Anthropic + logs
│  ├─ log.py                 # JSONL logging helper
│  ├─ mcp_fs_demo.py         # MCP CLIENT → official Filesystem server
│  ├─ mcp_git_demo.py        # MCP CLIENT → official Git server
│  ├─ mcp_f1_server.py       # Custom MCP SERVER (F1 Strategy) – FastMCP
│  └─ mcp_f1_demo.py         # MCP CLIENT → F1 server stdio demo

```

---

## Requirements
- **Python 3.10+** (virtualenv recommended)
- **Node.js 22+** (use `nvm`)
- Python packages:
  ```bash
  pip install -U "mcp[cli]" anthropic python-dotenv httpx
  ```

### Node via `nvm`
```bash
# Install nvm (if needed)
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"

# Install/use Node 22
nvm install 22
nvm use 22
nvm alias default 22
node -v   # v22.x
npm -v
```

### Environment Variables (Anthropic)
Create a **.env** file at the repository root:
```
ANTHROPIC_API_KEY=your_api_key_here
```


## How to Run the **MCP Demos**
> Make sure your **virtualenv is active**: `source .venv/bin/activate`

### 1) Filesystem MCP (client → official server)
```bash
python3 -m src.mcp_fs_demo
```
- Demonstrates `create_directory`, `write_file`, `read_text_file`, `list_directory` on `sandbox/`.

### 2) Git MCP (client → official server)
```bash
python3 -m src.mcp_git_demo
```
- Scenario: `git_set_working_dir → git_init → git_add → git_commit → git_log` **via MCP**.
- **Note:** `sandbox/git_demo/.git` is not committed (repo is ignored by `.gitignore`).

### 3) F1 MCP (F1 strategy server + demo)
```bash
python3 -m src.mcp_f1_demo
```
- Lists tools: `get_calendar`, `get_race`, `recommend_strategy`.
- `recommend_strategy` computes total race time (sum of stints + **pit loss**) with **linear degradation** per compound.
- **FIA rule (dry):** plans with ≥2 stints must use ≥2 different compounds.

**Key parameters (recommend_strategy):**
- `race_id` e.g., `demo_mexico_2024`
- `base_laptime_s`: clean lap time (without degradation)
- `deg_soft_s`, `deg_medium_s`, `deg_hard_s`: per-lap degradation (seconds)
- `min_stint_laps`, `max_stint_laps`: stint limits
- `max_stops`: maximum number of pit stops (0–3)

**Output:** plan with compounds and laps per stint, `stop_laps`, `predicted_total_s`, and `stint_breakdown_s`.

---

## Console Chat + **/f1** Commands
Start the chat:
```bash
python3 -m src.chat
```
Available commands (they call the **F1 MCP** over stdio):
```
/f1 tools
/f1 calendar 2024
/f1 race demo_mexico_2024
/f1 plan demo_mexico_2024 80 0.12 0.08 0.05 10 30 2
```
> Any input **without** `/f1` is sent to the **LLM** (Anthropic).

---

## Logs
- All interactions (LLM and MCP) are recorded in `logs/interactions.jsonl` as events:
  - `"type": "llm_exchange"`
  - `"type": "mcp_call"`
