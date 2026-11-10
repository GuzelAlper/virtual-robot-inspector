# Установка среды симуляции

## Зафиксированное окружение

- Ubuntu 24.04 (WSL)
- ROS 2 Jazzy
- Gazebo Sim Harmonic
- RViz
- модель Unitree Go2: [khaledgabr77/unitree_go2_ros2](https://github.com/khaledgabr77/unitree_go2_ros2)

Выбранный внешний пакет предоставляет модель Unitree Go2, контроллер CHAMP, поддержку Gazebo Harmonic, RViz и виртуальных датчиков. Пакет используется как внешняя зависимость и не копируется в основной репозиторий проекта.

## Подготовка рабочего пространства

После установки ROS 2 Jazzy и Gazebo Harmonic необходимо создать рабочее пространство:

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone https://github.com/khaledgabr77/unitree_go2_ros2
```

## Установка зависимостей

```bash
sudo apt update
sudo apt install ros-jazzy-gazebo-ros2-control
sudo apt install ros-jazzy-xacro
sudo apt install ros-jazzy-robot-localization
sudo apt install ros-jazzy-ros2-controllers
sudo apt install ros-jazzy-ros2-control
sudo apt install ros-jazzy-velodyne
sudo apt install ros-jazzy-velodyne-description

cd ~/ros2_ws
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

## Сборка

```bash
cd ~/ros2_ws
colcon build
source install/setup.bash
```

## Запуск Gazebo

```bash
ros2 launch unitree_go2_sim unitree_go2_launch.py
```

Запуск Gazebo вместе с RViz:

```bash
ros2 launch unitree_go2_sim unitree_go2_launch.py rviz:=true
```

Управление роботом с клавиатуры:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

## Проверка результата

Установка считается успешной, если:

1. Gazebo и RViz запускаются без критических ошибок.
2. Модель Unitree Go2 отображается в Gazebo и RViz.
3. Робот принимает команды движения.
4. Данные камеры и LiDAR доступны через ROS 2.

После подтверждения стабильной версии необходимо записать точный commit внешнего репозитория, чтобы оба участника команды использовали одинаковую версию модели.
