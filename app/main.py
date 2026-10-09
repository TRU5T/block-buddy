import asyncio
import json
import math
import os
import re
import time
from pathlib import Path

import anthropic
import docker
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from builder import BuildError, compile_plan

# ---------- config ----------
# SERVERS="Lily's World=mc-lily,Jack's World=mc-jack"   (display name = container name)
SERVERS = {}
for pair in filter(None, (p.strip() for p in os.environ.get("SERVERS", "").split(","))):
    name, _, container = pair.partition("=")
    SERVERS[name.strip()] = (container or name).strip()

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
PIN = os.environ.get("PIN", "")
BATCH = 60
CMDS_PER_SEC = 20  # BDS runs about one console command per game tick
EYE_HEIGHT = 1.62  # querytarget's y is the player's eyes, 1.62 above their feet

# Writes its arguments, one per line, to the bedrock_server process's stdin.
# The image's own send-command can't be used: it searches /proc/*/exe, which root
# in the container isn't allowed to read when the server runs as another UID.
WRITE_SH = r"""
p=
for d in /proc/[0-9]*; do
  case "$(cat "$d/comm" 2>/dev/null)" in bedrock_server*) p=$d; break;; esac
done
[ -n "$p" ] || { echo "bedrock_server process not found"; exit 2; }
[ "$(readlink "$p/fd/0")" = /dev/null ] && { echo "the server has no console input: recreate the container with -it"; exit 3; }
printf '%s\n' "$@" > "$p/fd/0"
"""

app = FastAPI()
dk = docker.from_env()
llm = anthropic.Anthropic()
locks = {name: asyncio.Lock() for name in SERVERS}
undo_info = {}  # server -> (structure_name, (x, y, z))
busy_until = {name: 0.0 for name in SERVERS}  # when the server will finish the last build's commands

PLAYER_RE = re.compile(r"^[A-Za-z0-9 _\-]{1,32}$")
LOG_PREFIX = re.compile(r"^\[[^\]]*\]\s*")

SYSTEM_PROMPT = Path(__file__).with_name("prompt.md").read_text()

BUILD_TOOL = {
    "name": "submit_build",
    "description": "Submit the build plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short name for the build"},
            "message": {"type": "string", "description": "One or two cheerful sentences to the kid about what you built"},
            "ops": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": ["box", "clear", "block", "cylinder", "sphere", "pyramid"]},
                        "block": {"type": "string"},
                        "from": {"type": "array", "items": {"type": "integer"}},
                        "to": {"type": "array", "items": {"type": "integer"}},
                        "pos": {"type": "array", "items": {"type": "integer"}},
                        "center": {"type": "array", "items": {"type": "integer"}},
                        "radius": {"type": "number"},
                        "height": {"type": "integer"},
                        "mode": {"type": "string", "enum": ["solid", "hollow", "outline", "walls"]},
                        "hollow": {"type": "boolean"},
                        "dome": {"type": "boolean"},
                    },
                    "required": ["op"],
                },
            },
        },
        "required": ["title", "message", "ops"],
    },
}


# ---------- docker / console helpers ----------
def _container(server):
    if server not in SERVERS:
        raise HTTPException(404, "Unknown world")
    try:
        return dk.containers.get(SERVERS[server])
    except docker.errors.NotFound:
        raise HTTPException(503, f"Container '{SERVERS[server]}' isn't running")


def _server_user(container):
    """'uid:gid' the bedrock_server process runs as (itzg drops to $UID:$GID, e.g. 99:100 on Unraid).
    Both must match for us to write to its /proc/<pid>/fd/0."""
    for pid, uid, gid, args in container.top(ps_args="-o pid,uid,gid,args")["Processes"]:  # Docker needs the pid column
        if "bedrock_server" in args:
            return f"{uid}:{gid}"
    raise HTTPException(503, "The Minecraft server isn't running in that container")


def _send(container, commands):
    user = _server_user(container)
    for i in range(0, len(commands), BATCH):
        res = container.exec_run(["sh", "-c", WRITE_SH, "sh", *commands[i:i + BATCH]], user=user)
        if res.exit_code != 0:
            raise HTTPException(500, f"Couldn't send commands to the server: {res.output.decode(errors='ignore')[:300]}")


def _ask(container, command, done, timeout=3.0):
    """Run a console command and return the raw log text it produced, once done(text) or timeout."""
    since = time.time() - 0.5
    _send(container, [command])
    deadline = time.time() + timeout
    while True:
        time.sleep(0.25)
        out = container.logs(since=since, stdout=True, stderr=True).decode(errors="ignore")
        if done(out) or time.time() > deadline:
            return out


def _wait_for_queue(server):
    """Seconds a new console command will sit behind an earlier build's commands."""
    return max(0.0, busy_until[server] - time.time())


def _players(container, server):
    out = _ask(container, "list", lambda o: "players online" in o, 3 + _wait_for_queue(server))
    # "[... INFO] There are 1/10 players online:" then the names on the next line
    lines = [LOG_PREFIX.sub("", line).strip() for line in out.splitlines()]
    for i in range(len(lines) - 1, -1, -1):
        if "players online" in lines[i]:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            return [p.strip() for p in nxt.split(",") if p.strip()]
    return []


def _target_data(out):
    """querytarget prints 'Target data: [' then pretty-printed JSON over many lines."""
    i = out.rfind("Target data:")
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(out[out.index("[", i):])[0]
    except ValueError:
        return None  # not all lines logged yet


def _locate(container, player):
    out = _ask(container, f'querytarget @a[name="{player}"]',
               lambda o: _target_data(o) is not None or "No targets matched" in o)
    data = _target_data(out)
    if data:
        p = data[0]["position"]
        # querytarget reports eye height; the builder wants the feet
        return (p["x"], round(p["y"] - EYE_HEIGHT, 2), p["z"]), float(data[0].get("yRot", 0))
    raise HTTPException(404, f"Couldn't find {player} in that world. Are they online?")


def _tell(player, text):
    return "tellraw @a[name=\"%s\"] %s" % (player, json.dumps({"rawtext": [{"text": text}]}))


def _check_pin(pin):
    if PIN and pin != PIN:
        raise HTTPException(401, "Wrong PIN")


# ---------- API ----------
class BuildReq(BaseModel):
    server: str
    player: str
    prompt: str
    pin: str = ""


class UndoReq(BaseModel):
    server: str
    pin: str = ""


_STATIC = Path(__file__).with_name("static")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/icon.png")
def icon():
    return FileResponse(_STATIC / "icon.png", media_type="image/png")


@app.get("/api/config")
def config():
    return {"servers": list(SERVERS), "pin_required": bool(PIN)}


@app.get("/api/players")
async def players(server: str):
    c = _container(server)
    async with locks[server]:
        return {"players": await asyncio.to_thread(_players, c, server)}


@app.post("/api/build")
async def build(req: BuildReq):
    _check_pin(req.pin)
    prompt = req.prompt.strip()[:500]
    if not prompt:
        raise HTTPException(400, "Tell me what to build first")
    if not PLAYER_RE.match(req.player):
        raise HTTPException(400, "That player name looks wrong")
    c = _container(req.server)

    async with locks[req.server]:
        left = _wait_for_queue(req.server)
        if left > 1:
            raise HTTPException(409, f"Still building the last thing! Try again in about {math.ceil(left)} seconds.")
        pos, yaw = await asyncio.to_thread(_locate, c, req.player)
        await asyncio.to_thread(_send, c, [_tell(req.player, f"Block Buddy is thinking about: {prompt}")])

        resp = await asyncio.to_thread(
            llm.messages.create,
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=[BUILD_TOOL],
            tool_choice={"type": "tool", "name": "submit_build"},
            messages=[{"role": "user", "content": prompt}],
        )
        plan = next((b.input for b in resp.content if b.type == "tool_use"), None)
        if not plan:
            raise HTTPException(502, "The builder didn't come back with a plan. Try again.")

        try:
            cmds, bb = compile_plan(plan, pos, yaw)
        except BuildError as e:
            raise HTTPException(400, str(e))

        slot = "bb_undo_" + re.sub(r"[^a-z0-9]", "", req.server.lower())[:20]
        save = f"structure save {slot} {bb[0]} {bb[1]} {bb[2]} {bb[3]} {bb[4]} {bb[5]} false memory true"
        done = _tell(req.player, f"Ta-da! {plan.get('title', 'Your build')} is ready.")
        await asyncio.to_thread(_send, c, [save, *cmds, done])
        seconds = math.ceil((len(cmds) + 2) / CMDS_PER_SEC)
        busy_until[req.server] = time.time() + seconds
        undo_info[req.server] = (slot, bb[:3])

    return {"title": plan.get("title"), "message": plan.get("message"), "commands": len(cmds), "seconds": seconds}


@app.post("/api/undo")
async def undo(req: UndoReq):
    _check_pin(req.pin)
    c = _container(req.server)
    if req.server not in undo_info:
        raise HTTPException(404, "Nothing to undo in this world yet")
    async with locks[req.server]:
        slot, (x, y, z) = undo_info.pop(req.server)
        await asyncio.to_thread(_send, c, [f"structure load {slot} {x} {y} {z}"])
    return {"ok": True}
