bash <<'BBTEST'
# Block Buddy console test. Paste this whole thing into the Unraid web terminal
# (the >_ icon, top right) while you're standing in your world.
# It builds a small test cube next to you, then puts everything back.

CONTAINER=""   # leave blank to auto-detect the Bedrock container
PLAYER=""      # leave blank to use the first player online

OUT=/tmp/bbtest-$(date +%H%M%S).txt
exec > >(tee "$OUT") 2>&1

if [ -z "$CONTAINER" ]; then
  CONTAINER=$(docker ps --filter ancestor=itzg/minecraft-bedrock-server --format '{{.Names}}' | head -1)
  [ -z "$CONTAINER" ] && CONTAINER=$(docker ps --format '{{.Names}} {{.Image}}' | grep -i bedrock | head -1 | cut -d' ' -f1)
fi
echo "=== container: $CONTAINER"
[ -z "$CONTAINER" ] && { echo "No Bedrock container found. Set CONTAINER= at the top."; exit 1; }

# Run one console command and show what the server logged in response.
ask() {
  local since; since=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
  echo; echo ">>> $1"
  docker exec "$CONTAINER" send-command "$1"; echo "(send-command exit=$?)"
  sleep "${2:-1}"
  docker logs --since "$since" "$CONTAINER" 2>&1 | sed 's/^/    /'
}

echo; echo "=== 1. Was the container created with -it?"
docker inspect "$CONTAINER" --format 'Tty={{.Config.Tty}} OpenStdin={{.Config.OpenStdin}} Image={{.Config.Image}}'
docker exec "$CONTAINER" sh -c 'p=$(pgrep -f bedrock_server | head -1); echo "server pid=$p stdin -> $(readlink /proc/$p/fd/0)"'

echo; echo "=== 1b. Can we talk to the server? (look for this in your game chat)"
ask "say Block Buddy test: can you see this?"

echo; echo "=== 2a. list"
ask "list"
if [ -z "$PLAYER" ]; then
  PLAYER=$(docker logs --tail 20 "$CONTAINER" 2>&1 | grep -A1 'players online' | tail -1 \
           | sed -E 's/^\[[^]]*\] *//; s/^ *(INFO\]?)? *//' | cut -d, -f1 | xargs)
fi
echo "=== player: '$PLAYER'"
[ -z "$PLAYER" ] && { echo "Couldn't work out who's online. Set PLAYER= at the top and rerun."; exit 1; }
AT="execute at @a[name=\"$PLAYER\"] run"

echo; echo "=== 2b. querytarget (position + facing)"
ask "querytarget @a[name=\"$PLAYER\"]"

echo; echo "=== 2c. tellraw"
ask "tellraw @a[name=\"$PLAYER\"] {\"rawtext\":[{\"text\":\"Block Buddy test: tellraw works\"}]}"

echo; echo "=== 3. structure save, fill hollow/outline, structure load (undo)"
echo "    A small cube appears 3 blocks east of you, then vanishes after 8 seconds."
ask "$AT structure save bb_test ~3 ~ ~-3 ~9 ~6 ~3 false memory true"
ask "$AT fill ~3 ~ ~-3 ~9 ~6 ~3 stone_bricks hollow"
ask "$AT fill ~4 ~1 ~-2 ~8 ~5 ~2 glass outline"
ask "$AT setblock ~6 ~3 ~ glowstone"
sleep 8
ask "$AT structure load bb_test ~3 ~ ~-3"

echo; echo "=== 4. block IDs from prompt.md (one at a time, 20 blocks above you, then removed)"
COLOURS="white orange magenta light_blue yellow lime pink gray light_gray cyan purple blue brown green red black"
BLOCKS="stone cobblestone mossy_cobblestone stone_bricks mossy_stone_bricks smooth_stone bricks sandstone red_sandstone quartz_block polished_andesite polished_granite polished_diorite deepslate_bricks blackstone obsidian prismarine dark_prismarine oak_planks spruce_planks birch_planks jungle_planks acacia_planks dark_oak_planks cherry_planks oak_log spruce_log birch_log oak_leaves spruce_leaves birch_leaves cherry_leaves glass glass_pane grass_block dirt sand gravel snow ice packed_ice blue_ice water hay_block bookshelf crafting_table pumpkin melon_block iron_block gold_block diamond_block emerald_block lapis_block redstone_block amethyst_block copper_block glowstone sea_lantern lantern shroomlight honeycomb_block slime poppy dandelion cornflower oxeye_daisy"
for c in $COLOURS; do BLOCKS="$BLOCKS ${c}_stained_glass ${c}_wool ${c}_concrete ${c}_terracotta"; done
since=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
for b in $BLOCKS; do
  docker exec "$CONTAINER" send-command "$AT setblock ~ ~20 ~ $b"
done
docker exec "$CONTAINER" send-command "$AT setblock ~ ~20 ~ air"
sleep 2
docker logs --since "$since" "$CONTAINER" 2>&1 | grep -v -i 'block placed' | sed 's/^/    /'
echo "    (anything listed above, other than 'Block placed', is a problem)"

echo; echo "=== done. Output saved to $OUT"
BBTEST
