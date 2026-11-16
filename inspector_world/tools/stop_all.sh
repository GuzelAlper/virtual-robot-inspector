#!/usr/bin/env bash
# Остановить всё, что осталось от прошлых запусков: Gazebo, launch, узлы Go2/Nav2/инспекции.
# Иначе старые узлы (например, map_server без карты) мешают новому запуску.
PATTERN="ros2 launch|gz sim|/opt/ros/jazzy/lib/|ros2_ws/install/|gauge_reader|route_runner|gt_localizer|wasd"
victims() { pgrep -f "$PATTERN" | grep -vx -e "$$" -e "$PPID"; }
pids=$(victims)
[ -n "$pids" ] && kill $pids 2>/dev/null
sleep 3
pids=$(victims)
if [ -n "$pids" ]; then
  echo "ещё работают, принудительно останавливаю: $(echo $pids)"
  kill -9 $pids 2>/dev/null
  sleep 1
fi
ros2 daemon stop >/dev/null 2>&1
echo "всё остановлено"
