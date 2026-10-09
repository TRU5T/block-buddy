"""Hand-built redstone contraptions.

These skip the model: the wiring is fixed, then compile_plan rotates it to
face the player. A request only matches when it is basically one of these
and not a larger build ("a castle with a piston door" still goes to Claude).
"""
import re

_STOP = {
    "a", "an", "the", "me", "my", "please", "build", "make", "with", "and",
    "some", "cool", "fun", "little", "small", "redstone", "circuit", "thing",
    "things", "that", "works", "working", "can", "you", "i", "want",
}
_BIG = (
    "castle", "house", "cabin", "ship", "tower", "village", "city", "treehouse",
    "mansion", "shop", "bridge", "igloo", "lighthouse", "rocket", "pyramid",
    "statue", "base", "hotel", "barn", "farm",
)


def _floor(x0, x1, z0, z1, block="stone"):
    return {"op": "box", "block": block, "from": [x0, -1, z0], "to": [x1, -1, z1]}


def lever_lamp():
    return {
        "title": "Lever lamp",
        "message": "Flip the lever and the lamp turns on. Flip it again and it goes out.",
        "ops": [
            _floor(-1, 1, 1, 6),
            {"op": "block", "block": "lever", "pos": [0, 0, 2], "face": "up"},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 3]},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 4]},
            {"op": "block", "block": "redstone_lamp", "pos": [0, 0, 5]},
        ],
    }


def piston_pop():
    return {
        "title": "Piston pop",
        "message": "Press the button and the gold block pops up. Let go and it comes back down.",
        "ops": [
            _floor(-1, 1, 1, 6),
            {"op": "block", "block": "stone", "pos": [0, 0, 2]},
            {"op": "block", "block": "stone_button", "pos": [0, 1, 2], "face": "up"},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 3]},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 4]},
            {"op": "block", "block": "sticky_piston", "pos": [0, 0, 5], "face": "up"},
            {"op": "block", "block": "gold_block", "pos": [0, 1, 5]},
        ],
    }


def piston_door():
    # Two stacked sticky pistons on the child's left, pushing the door to the right.
    # Dust runs into a stone block; the dust on top of that block powers both pistons.
    return {
        "title": "Piston door",
        "message": "Press the button and the door slides open. Let go and it shuts.",
        "ops": [
            _floor(-3, 2, 1, 8),
            {"op": "box", "block": "stone_bricks", "from": [-1, -1, 2], "to": [0, -1, 8]},
            {"op": "box", "block": "stone_bricks", "from": [2, 0, 6], "to": [2, 3, 6]},
            {"op": "box", "block": "stone_bricks", "from": [0, 2, 6], "to": [1, 3, 6]},
            {"op": "block", "block": "glowstone", "pos": [2, 2, 5]},
            {"op": "block", "block": "stone", "pos": [-2, 0, 6]},
            {"op": "block", "block": "redstone_wire", "pos": [-2, 1, 6]},
            {"op": "block", "block": "sticky_piston", "pos": [-1, 0, 6], "face": "right"},
            {"op": "block", "block": "sticky_piston", "pos": [-1, 1, 6], "face": "right"},
            {"op": "block", "block": "oak_planks", "pos": [0, 0, 6]},
            {"op": "block", "block": "oak_planks", "pos": [0, 1, 6]},
            {"op": "block", "block": "stone", "pos": [-2, 0, 2]},
            {"op": "block", "block": "stone_button", "pos": [-2, 1, 2], "face": "up"},
            {"op": "block", "block": "redstone_wire", "pos": [-2, 0, 3]},
            {"op": "block", "block": "redstone_wire", "pos": [-2, 0, 4]},
            {"op": "block", "block": "redstone_wire", "pos": [-2, 0, 5]},
        ],
    }


def doorbell():
    return {
        "title": "Doorbell",
        "message": "Press the button. The note block rings, as long as nothing is sitting on top of it.",
        "ops": [
            _floor(-1, 1, 1, 5),
            {"op": "block", "block": "stone", "pos": [0, 0, 2]},
            {"op": "block", "block": "stone_button", "pos": [0, 1, 2], "face": "up"},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 3]},
            {"op": "block", "block": "noteblock", "pos": [0, 0, 4]},
        ],
    }


def pressure_plate():
    return {
        "title": "Pressure plate light",
        "message": "Step on the plate and the lamp turns on. Step off and it goes out.",
        "ops": [
            _floor(-1, 1, 1, 6),
            {"op": "block", "block": "stone_pressure_plate", "pos": [0, 0, 2]},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 3]},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 4]},
            {"op": "block", "block": "redstone_lamp", "pos": [0, 0, 5]},
        ],
    }


def motion_alarm():
    return {
        "title": "Motion alarm",
        "message": "Walk in front of the observer. The lamp flashes.",
        "ops": [
            _floor(-1, 1, 1, 7),
            {"op": "block", "block": "observer", "pos": [0, 0, 3], "face": "back"},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 4]},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 5]},
            {"op": "block", "block": "redstone_lamp", "pos": [0, 0, 6]},
        ],
    }


def runway():
    return {
        "title": "Runway lights",
        "message": "Flip the lever. The lamps turn on one after another, then all go out together.",
        "ops": [
            _floor(-1, 2, 1, 12),
            {"op": "block", "block": "lever", "pos": [0, 0, 2], "face": "up"},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 3]},
            {"op": "block", "block": "unpowered_repeater", "pos": [0, 0, 4], "face": "forward", "delay": 1},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 5]},
            {"op": "block", "block": "redstone_lamp", "pos": [1, 0, 5]},
            {"op": "block", "block": "unpowered_repeater", "pos": [0, 0, 6], "face": "forward", "delay": 2},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 7]},
            {"op": "block", "block": "redstone_lamp", "pos": [1, 0, 7]},
            {"op": "block", "block": "unpowered_repeater", "pos": [0, 0, 8], "face": "forward", "delay": 4},
            {"op": "block", "block": "redstone_wire", "pos": [0, 0, 9]},
            {"op": "block", "block": "redstone_lamp", "pos": [1, 0, 9]},
        ],
    }


# Longest phrase first so "piston door" wins over "piston".
_RECIPES = (
    ("piston door", piston_door),
    ("secret door", piston_door),
    ("runway lights", runway),
    ("runway", runway),
    ("motion alarm", motion_alarm),
    ("pressure plate", pressure_plate),
    ("note block", doorbell),
    ("doorbell", doorbell),
    ("redstone lamp", lever_lamp),
    ("lever lamp", lever_lamp),
    ("lever and a lamp", lever_lamp),
    ("button and a piston", piston_pop),
    ("sticky piston", piston_pop),
    ("piston", piston_pop),
    ("observer", motion_alarm),
    ("lamp", lever_lamp),
)


def _norm(prompt):
    return re.sub(r"[^a-z0-9]+", " ", prompt.lower()).strip()


def _focused(text, phrase):
    if not re.search(rf"\b{re.escape(phrase)}\b", text):
        return False
    rest = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    rest = re.sub(r"\b(" + "|".join(_STOP) + r")\b", " ", rest)
    return rest.split() == []


def match_redstone(prompt):
    text = _norm(prompt)
    if any(re.search(rf"\b{word}\b", text) for word in _BIG):
        return None
    for phrase, build in _RECIPES:
        if _focused(text, phrase):
            plan = build()
            plan["recipe"] = True
            return plan
    return None
