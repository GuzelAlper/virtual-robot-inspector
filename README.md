# Симуляционный прототип инспекционного робота Unitree Go2 EDU

Проектный практикум, УрФУ ИРИТ-РТФ.
Авторы: **Четин Хюсейн Озгюр**, **Гюзель Алпер**.

Четвероногий робот Unitree Go2 в Gazebo **автономно, через Nav2** проходит маршрут по
производственному помещению: стартовая зона → коридор с препятствием → цех со стойкой
стрелочных приборов. У каждого прибора робот точно встаёт напротив, 2–3 с смотрит на него
камерой (кадр сохраняется), боком переходит к следующему, затем возвращается на старт и
формирует отчёт «посещено / не доехал». Оператор ничего не делает руками.

![Схема сцены](inspector_world/docs/scene_map.png)

## Стек

| Компонент | Версия / решение |
|---|---|
| ОС | Ubuntu 24.04 (WSL2 на Windows 11) |
| Middleware | ROS 2 Jazzy |
| Симулятор | Gazebo Sim 8 (Harmonic) |
| Модель робота | Unitree Go2 — [khaledgabr77/unitree_go2_ros2](https://github.com/khaledgabr77/unitree_go2_ros2), контроллер ходьбы CHAMP |
| Навигация | Nav2: map_server, NavFn, Regulated Pure Pursuit, behavior server, BT navigator |
| Миссия | собственный узел `route_runner` (nav2_simple_commander) |

## Структура репозитория

```
inspector_world/          ROS 2-пакет: сцена, карта, Nav2, миссия (подробно — inspector_world/README.md)
  config/scene.yaml       описание сцены: помещения, препятствия, станции, приборы
  scripts/                генератор мира, карты, текстур и маршрута из scene.yaml
  launch/                 inspection_mission (всё сразу), inspection_world, navigation
  tools/                  route_runner (миссия), gt_localizer (локализация), stop_all.sh
docs/SETUP.md             установка окружения с нуля (WSL, ROS 2, Gazebo, Go2, ускорение графики)
tools/wasd_teleop.py      ручное управление с клавиатуры (для отладки)
```

## Быстрый старт

Окружение (Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, пакет Go2) — по [docs/SETUP.md](docs/SETUP.md). Затем:

```bash
sudo apt install -y ros-jazzy-navigation2
cd ~/ros2_ws/src
git clone https://github.com/GuzelAlper/virtual-robot-inspector.git
cd ~/ros2_ws && colcon build --packages-select inspector_world && source install/setup.bash

ros2 run inspector_world stop_all.sh                    # убрать остатки прошлых запусков
ros2 launch inspector_world inspection_mission.launch.py software_render:=true
```

Через ~30 с Go2 встаёт, через ~40 с стартует Nav2 и миссия. Откроются окна Gazebo и камеры
робота. Ход миссии — в терминале (`[1/4] еду к CP-01 …`, `встал напротив прибора …`),
отчёт — в `~/inspection_reports/<дата_время>/report.md`.

## Текущее состояние

* [x] окружение ROS 2 + Gazebo, модель Go2, ручное управление
* [x] сцена: помещения, препятствия, станция с 4 стрелочными приборами (генерируется из YAML)
* [x] карта для Nav2 из той же сцены, локализация в симуляции
* [x] автономный обход маршрута через Nav2, точная постановка напротив приборов, возврат на старт
* [x] отчёт по миссии (Markdown / JSON / CSV + кадры камеры), обработка «не доехал / застрял / упал»
* [ ] распознавание показаний приборов (нейросеть)
* [ ] 16 станций × 4 прибора по ТЗ (добавляются в `scene.yaml`)
* [ ] база данных результатов и пульт оператора
