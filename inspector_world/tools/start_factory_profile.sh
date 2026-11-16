#!/usr/bin/env bash
set -Eeuo pipefail

PROFILE="${1:-$HOME/factory_scene}"
WORLD="$PROFILE/factory_hall.sdf"
MAP="$PROFILE/factory_map.yaml"
ROUTE="$PROFILE/factory_route.yaml"

for file in "$WORLD" "$MAP" "$ROUTE"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing factory profile file: $file" >&2
    echo "See deployment/factory_integration/README_TR.md in the GitHub repository." >&2
    exit 2
  fi
done

read -r SPAWN_X SPAWN_Y SPAWN_YAW < <(
  python3 -c 'import sys,yaml; d=yaml.safe_load(open(sys.argv[1], encoding="utf-8")); s=d["start"]; print(s["x"],s["y"],s["yaw"])' "$ROUTE"
)

if [[ -d "$PROFILE/models" ]]; then
  export GZ_SIM_RESOURCE_PATH="$PROFILE/models:${GZ_SIM_RESOURCE_PATH:-}"
fi

exec ros2 launch inspector_world inspection_mission.launch.py \
  world:="$WORLD" map:="$MAP" route:="$ROUTE" \
  spawn_x:="$SPAWN_X" spawn_y:="$SPAWN_Y" spawn_yaw:="$SPAWN_YAW" \
  software_render:=false camera_view:=true ai:=true ai_view:=true
