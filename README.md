# Block Buddy

A kid-friendly web page where you type "build me a castle with a moat" and it appears
in front of you in your Minecraft Bedrock world. Claude designs the build, and the app
turns it into vanilla /fill and /setblock commands, sent through the server console.
There are no mods or addons, and cheats can stay off.

## How it works
1. The page asks the server `list` to find who's online.
2. On Build, it runs `querytarget` to get the player's position and which way they face.
3. Claude returns a plan made of simple shapes (box, cylinder, sphere, pyramid, clear, block).
4. builder.py rotates the plan to face the player, places it 3 blocks in front of them,
   and turns it into commands, split to stay under Bedrock's 32,768-block /fill limit.
5. Before building, it saves the area with `structure save`, so Undo can restore it.

## Setup on Unraid

Copy this folder to `/mnt/user/appdata/block-buddy`, then in the Unraid terminal:

    cd /mnt/user/appdata/block-buddy
    docker build -t block-buddy .

    docker run -d --name block-buddy --restart unless-stopped \
      -p 8090:8080 \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -e ANTHROPIC_API_KEY=sk-ant-... \
      -e SERVERS="Lily's World=mc-lily,Jack's World=mc-jack" \
      -e PIN=1234 \
      block-buddy

Open http://<unraid-ip>:8090 on a phone or tablet.

Environment variables:
- `SERVERS`: comma-separated `Display name=container name` pairs. Container names must match
  your itzg/minecraft-bedrock-server containers exactly.
- `ANTHROPIC_API_KEY`: from console.anthropic.com.
- `MODEL`: optional, defaults to claude-sonnet-5-5. An Opus model gives fancier builds but
  is slower and costs more.
- `PIN`: optional. If set, the page asks for it once and remembers it on that device.

After editing any code, rebuild the image and recreate the container.

## Notes
- The Docker socket gives this container control of Docker on the host. Keep it on your
  LAN only. Don't port-forward it.
- The Minecraft containers can be on br0 with their own IPs. Block Buddy talks to them
  through Docker, not the network.
- The Bedrock containers must be created with an interactive console. In Unraid, add `-it`
  to Extra Parameters. Without it, builds fail with "the server has no console input".
- Block Buddy writes commands straight to the server's console as the server's own user
  (e.g. UID 99:100 on Unraid). It doesn't use the image's `send-command`, which fails when the
  server isn't running as root.
- The server runs about 20 commands a second, so a big build takes up to ~2 minutes to
  finish appearing. A new build in the same world is refused until the last one is done.
- If one block type never appears, Bedrock probably uses a different ID for it. Fix the name
  in app/prompt.md. Invalid blocks only skip that command, and the rest of the build still runs.
- Undo restores only the most recent build per world, and only until the app restarts.
- The build needs to be near the player so its chunks are loaded. It always is, because it's
  placed right in front of them.
- Cost is roughly a few cents per build with Sonnet.
