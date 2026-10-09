"""
Turns a build plan (a list of simple shape operations in a local coordinate
frame) into Bedrock console commands, rotated so the build sits in front of
the player and faces them.

Local frame used by the LLM:
  x = left/right (negative = player's left, positive = player's right)
  y = up (0 = ground level where the player's feet are, -1 = the ground itself)
  z = forward (0 = edge closest to the player, larger = further away)
"""
import math
import re

# Build volume limits in the local frame
LIM_X = 24
LIM_Z_MIN, LIM_Z_MAX = 0, 48
LIM_Y_MIN, LIM_Y_MAX = -8, 48
WORLD_Y_MIN, WORLD_Y_MAX = -64, 319

FILL_MAX = 32768          # Bedrock /fill limit per command
MAX_VOLUME = 400_000      # total blocks touched by one build
MAX_COMMANDS = 2500
GAP = 3                   # blocks between the player and the near edge of the build

BLOCK_RE = re.compile(r"^[a-z0-9_]+$")
DENY = {
    "tnt", "lava", "flowing_lava", "fire", "soul_fire", "bedrock", "barrier",
    "command_block", "chain_command_block", "repeating_command_block",
    "structure_block", "structure_void", "jigsaw", "allow", "deny", "border_block",
    "respawn_anchor", "end_portal", "end_gateway", "portal", "light_block",
}
# Java-style names the model may still use -> Bedrock IDs (checked on BDS 1.26.52)
ALIASES = {"bricks": "brick_block"}

# Facing index -> forward vector (x, z). Minecraft yaw: 0=south(+Z), 90=west, 180=north, 270=east
FORWARD = [(0, 1), (-1, 0), (0, -1), (1, 0)]


class BuildError(Exception):
    pass


def facing_from_yaw(yaw: float) -> int:
    return int(round((yaw % 360) / 90.0)) % 4


def clean_block(name) -> str:
    if not isinstance(name, str):
        raise BuildError("Missing block name")
    b = name.strip().lower()
    if b.startswith("minecraft:"):
        b = b[len("minecraft:"):]
    if not BLOCK_RE.match(b):
        raise BuildError(f"Invalid block name: {name!r}")
    if b in DENY:
        return "stone"
    return ALIASES.get(b, b)


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(round(v))))


def _pt(p):
    if not isinstance(p, (list, tuple)) or len(p) != 3:
        raise BuildError(f"Expected [x, y, z], got {p!r}")
    x, y, z = (float(n) for n in p)
    return (_clamp(x, -LIM_X, LIM_X), _clamp(y, LIM_Y_MIN, LIM_Y_MAX), _clamp(z, LIM_Z_MIN, LIM_Z_MAX))


def _box(a, b, block, mode="replace"):
    (x1, y1, z1), (x2, y2, z2) = a, b
    return (min(x1, x2), min(y1, y2), min(z1, z2), max(x1, x2), max(y1, y2), max(z1, z2), block, mode)


def _runs(values):
    """[1,2,3,7,8] -> [(1,3),(7,8)]"""
    out = []
    for v in sorted(values):
        if out and v == out[-1][1] + 1:
            out[-1][1] = v
        else:
            out.append([v, v])
    return [tuple(r) for r in out]


def _walls(x1, y1, z1, x2, y2, z2, block):
    if x2 - x1 < 2 or z2 - z1 < 2:
        return [(x1, y1, z1, x2, y2, z2, block, "replace")]
    return [
        (x1, y1, z1, x2, y2, z1, block, "replace"),
        (x1, y1, z2, x2, y2, z2, block, "replace"),
        (x1, y1, z1 + 1, x1, y2, z2 - 1, block, "replace"),
        (x2, y1, z1 + 1, x2, y2, z2 - 1, block, "replace"),
    ]


def op_to_boxes(op: dict):
    kind = op.get("op")

    if kind == "clear":
        return [_box(_pt(op["from"]), _pt(op["to"]), "air")]

    block = clean_block(op.get("block"))

    if kind == "block":
        p = _pt(op["pos"])
        return [_box(p, p, block)]

    if kind == "box":
        b = _box(_pt(op["from"]), _pt(op["to"]), block)
        mode = op.get("mode", "solid")
        if mode == "walls":
            return _walls(*b[:6], block)
        if mode in ("hollow", "outline"):
            return [b[:7] + (mode,)]
        return [b]

    if kind == "cylinder":
        cx, cy, cz = _pt(op["center"])
        r = max(0.5, min(float(op.get("radius", 3)), 24))
        h = max(1, min(int(op.get("height", 5)), 56))
        hollow = bool(op.get("hollow", False))
        out = []
        R = math.ceil(r)
        for dx in range(-R, R + 1):
            zs = []
            for dz in range(-R, R + 1):
                d2 = dx * dx + dz * dz
                if d2 <= (r + 0.5) ** 2 and not (hollow and d2 <= (r - 0.5) ** 2):
                    zs.append(dz)
            for z0, z1 in _runs(zs):
                a = _pt((cx + dx, cy, cz + z0))
                b = _pt((cx + dx, cy + h - 1, cz + z1))
                out.append(_box(a, b, block))
        return out

    if kind == "sphere":
        cx, cy, cz = _pt(op["center"])
        r = max(0.5, min(float(op.get("radius", 3)), 24))
        hollow = bool(op.get("hollow", False))
        dome = bool(op.get("dome", False))
        out = []
        R = math.ceil(r)
        for dy in range(0 if dome else -R, R + 1):
            for dx in range(-R, R + 1):
                zs = []
                for dz in range(-R, R + 1):
                    d2 = dx * dx + dy * dy + dz * dz
                    if d2 <= (r + 0.5) ** 2 and not (hollow and d2 <= (r - 0.5) ** 2):
                        zs.append(dz)
                for z0, z1 in _runs(zs):
                    a = _pt((cx + dx, cy + dy, cz + z0))
                    b = _pt((cx + dx, cy + dy, cz + z1))
                    out.append(_box(a, b, block))
        return out

    if kind == "pyramid":
        x1, y, z1, x2, _, z2 = _box(_pt(op["from"]), _pt(op["to"]), block)[:6]
        hollow = bool(op.get("hollow", False))
        out, k = [], 0
        while x1 + k <= x2 - k and z1 + k <= z2 - k and y + k <= LIM_Y_MAX:
            layer = (x1 + k, y + k, z1 + k, x2 - k, y + k, z2 - k)
            out.extend(_walls(*layer, block) if hollow else [layer + (block, "replace")])
            k += 1
        return out

    raise BuildError(f"Unknown op: {kind!r}")


def _vol(b):
    return (b[3] - b[0] + 1) * (b[4] - b[1] + 1) * (b[5] - b[2] + 1)


def _split(b):
    """Split a box so every piece fits under the /fill limit."""
    if _vol(b) <= FILL_MAX:
        return [b]
    x1, y1, z1, x2, y2, z2, block, mode = b
    if mode in ("hollow", "outline"):
        # Decompose a big shell into faces (plus an air interior for 'hollow')
        faces = [
            (x1, y1, z1, x2, y1, z2), (x1, y2, z1, x2, y2, z2),            # floor, ceiling
            *[(f[0], y1 + 1, f[2], f[3], y2 - 1, f[5]) for f in [t[:6] for t in _walls(x1, 0, z1, x2, 0, z2, block)]],
        ]
        parts = [f + (block, "replace") for f in faces if f[1] <= f[4]]
        if mode == "hollow" and x2 - x1 >= 2 and y2 - y1 >= 2 and z2 - z1 >= 2:
            parts.append((x1 + 1, y1 + 1, z1 + 1, x2 - 1, y2 - 1, z2 - 1, "air", "replace"))
        return [p for part in parts for p in _split(part)]
    layer = (x2 - x1 + 1) * (z2 - z1 + 1)
    step = max(1, FILL_MAX // layer)
    return [(x1, y, z1, x2, min(y + step - 1, y2), z2, block, mode) for y in range(y1, y2 + 1, step)]


def compile_plan(plan: dict, player_pos, yaw: float):
    """
    Returns (commands, world_bbox) where world_bbox = (minx, miny, minz, maxx, maxy, maxz).
    player_pos: (x, y, z) floats from querytarget (y = feet).
    """
    ops = plan.get("ops") or []
    if not ops:
        raise BuildError("The plan had no building steps")

    boxes = []
    for op in ops:
        boxes.extend(op_to_boxes(op))

    total = sum(_vol(b) for b in boxes)
    if total > MAX_VOLUME:
        raise BuildError(f"That build is too big ({total:,} blocks). Try something smaller.")

    f = facing_from_yaw(yaw)
    fx, fz = FORWARD[f]
    rx, rz = -fz, fx  # player's right-hand direction
    px, py, pz = (math.floor(v) for v in player_pos)
    ox, oy, oz = px + fx * GAP, py, pz + fz * GAP

    def to_world(lx, ly, lz):
        return (ox + rx * lx + fx * lz, oy + ly, oz + rz * lx + fz * lz)

    cmds = []
    bb = [10**9, 10**9, 10**9, -10**9, -10**9, -10**9]
    for b in boxes:
        a = to_world(b[0], b[1], b[2])
        c = to_world(b[3], b[4], b[5])
        wb = (min(a[0], c[0]), max(WORLD_Y_MIN, min(a[1], c[1])), min(a[2], c[2]),
              max(a[0], c[0]), min(WORLD_Y_MAX, max(a[1], c[1])), max(a[2], c[2]), b[6], b[7])
        if wb[1] > wb[4]:
            continue
        for i in range(3):
            bb[i] = min(bb[i], wb[i])
            bb[i + 3] = max(bb[i + 3], wb[i + 3])
        for p in _split(wb):
            x1, y1, z1, x2, y2, z2, block, mode = p
            if (x1, y1, z1) == (x2, y2, z2) and mode == "replace":
                cmds.append(f"setblock {x1} {y1} {z1} {block}")
            else:
                m = "" if mode == "replace" else f" {mode}"
                cmds.append(f"fill {x1} {y1} {z1} {x2} {y2} {z2} {block}{m}")

    if len(cmds) > MAX_COMMANDS:
        raise BuildError(f"That build needs too many steps ({len(cmds)}). Try something simpler.")
    return cmds, tuple(bb)
