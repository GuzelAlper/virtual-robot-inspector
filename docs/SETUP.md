# Установка рабочего окружения

Проверено 03.11.2026 на Windows 11 + WSL2, 8 ядер, 8 ГБ ОЗУ в WSL.

| Компонент | Версия |
|---|---|
| ОС | Ubuntu 24.04 LTS (WSL2) |
| ROS 2 | Jazzy Jalisco |
| Симулятор | Gazebo Sim 8 (Harmonic) |
| Модель робота | Unitree Go2 EDU — [khaledgabr77/unitree_go2_ros2](https://github.com/khaledgabr77/unitree_go2_ros2) (контроллер ходьбы CHAMP) |

> Почему не Ubuntu 26.04 / ROS 2 Lyrical: готовые пакеты Go2 для Gazebo пока есть только под Jazzy + Harmonic. Ubuntu 24.04 ставится в WSL отдельным дистрибутивом и не мешает другим.

## 1. Ubuntu 24.04 в WSL

В PowerShell (Windows):

```powershell
wsl --install -d Ubuntu-24.04
```

Дальше все команды выполняются внутри Ubuntu 24.04. Открывать её: `wsl -d Ubuntu-24.04` (просто `wsl` может открыть другой дистрибутив).

## 2. ROS 2 Jazzy и Gazebo Harmonic

```bash
cd ~
sudo apt update && sudo apt install -y software-properties-common curl
sudo add-apt-repository -y universe
export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F\" '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo $VERSION_CODENAME)_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
sudo apt update && sudo apt upgrade -y
sudo apt install -y ros-jazzy-desktop ros-dev-tools ros-jazzy-ros-gz
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc && source ~/.bashrc
```

Проверка:

```bash
ros2 --help | head -3
gz sim --version        # Gazebo Sim, version 8.x
```

## 3. Модель Unitree Go2

```bash
sudo apt install -y ros-jazzy-gz-ros2-control ros-jazzy-xacro ros-jazzy-robot-localization \
  ros-jazzy-ros2-controllers ros-jazzy-ros2-control ros-jazzy-velodyne ros-jazzy-velodyne-description \
  ros-jazzy-teleop-twist-keyboard

mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src
git clone https://github.com/khaledgabr77/unitree_go2_ros2
cd ~/ros2_ws
sudo rosdep init; rosdep update
rosdep install --from-paths src --ignore-src -r -y
colcon build
echo "source ~/ros2_ws/install/setup.bash" >> ~/.bashrc && source ~/.bashrc
```

Поднять пределы скорости контроллера ходьбы CHAMP (по умолчанию 0.3 м/с и 0.5 рад/с —
маршрут проходится заметно медленнее):

```bash
sed -i 's/max_linear_velocity_x : 0.3/max_linear_velocity_x : 0.5/; s/max_angular_velocity_z : 0.5/max_angular_velocity_z : 0.8/' \
  ~/ros2_ws/src/unitree_go2_ros2/unitree_go2_sim/config/gait/gait.yaml
cd ~/ros2_ws && colcon build --packages-select unitree_go2_sim
```

## 3а. Nav2 и пакет миссии (этот репозиторий)

```bash
sudo apt install -y ros-jazzy-navigation2
cd ~/ros2_ws/src
git clone https://github.com/GuzelAlper/virtual-robot-inspector.git
cd ~/ros2_ws                        # собирать только из корня рабочего пространства!
colcon build --packages-select inspector_world
source install/setup.bash
```

## 4. Ускорение графики (обязательно в WSL)

По умолчанию WSL рисует OpenGL на процессоре (`llvmpipe`), и симуляция идёт в ~20 % от реального времени. Включаем видеокарту:

```bash
ls -l /dev/dxg                       # должен существовать
sudo apt install -y mesa-utils
echo 'export GALLIUM_DRIVER=d3d12' >> ~/.bashrc && source ~/.bashrc
glxinfo -B | grep "renderer string"  # должно быть D3D12 (...), а не llvmpipe
```

Если видеокарт две и выбрана встроенная: `export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA` (или AMD).
Если `/dev/dxg` нет — обновить драйвер видеокарты в Windows и перезагрузиться.

Результат у нас: real-time factor вырос с ~20 % до ~57 %.

**Важно:** с GPU-рендером (d3d12) в WSL камера робота (`/rgb_image`) отдаёт чёрные кадры.
Если нужна камера — запускать симуляцию с `software_render:=true` (рендер на CPU, медленнее).

## 5. Запуск симуляции

```bash
# быстрый режим: без RViz и тяжёлых сенсоров
ros2 launch unitree_go2_sim unitree_go2_launch.py rviz:=false disable_velodyne_lidar:=true disable_d455:=true

# полный режим: RViz, лидар и камера D455
ros2 launch unitree_go2_sim unitree_go2_launch.py rviz:=true
```

RViz отдельно (если Gazebo уже запущен):

```bash
ros2 run rviz2 rviz2 -d ~/ros2_ws/install/unitree_go2_sim/share/unitree_go2_sim/rviz/rviz.rviz --ros-args -p use_sim_time:=true
```

## 6. Ручное управление (WASD)

Во втором терминале:

```bash
python3 ~/ros2_ws/src/virtual-robot-inspector/tools/wasd_teleop.py   # топик /cmd_vel
```

Не запускать одновременно с автоматической миссией (две программы будут слать команды в `/cmd_vel`).

| Клавиша | Действие |
|---|---|
| W / S | скорость вперёд / назад (шаг 0.2 м/с, максимум 1.0 м/с) |
| A / D | поворот влево / вправо |
| Q / E | движение боком |
| Пробел | стоп |
| X | выход |

Клавиши работают, только когда активно окно терминала со скриптом (не RViz — у RViz свои горячие клавиши).

## Частые проблемы

| Симптом | Причина и решение |
|---|---|
| Робот крутится на месте, в логе `no map received` | Остались узлы прошлого запуска — `ros2 run inspector_world stop_all.sh` |
| `Package '...' not found` | `colcon build` запущен не из `~/ros2_ws` или не выполнен `source ~/ros2_ws/install/setup.bash` |
| Робот сам едет назад/вперёд | Открыта вторая программа управления (`teleop_twist_keyboard` и т. п.), CHAMP выполняет её последнюю команду. Закрыть всё: `pkill -f teleop_twist_keyboard; pkill -f wasd_teleop.py; ros2 topic pub --times 5 /cmd_vel geometry_msgs/msg/Twist "{}"`. Держать открытой только одну программу управления. |
| Симуляция медленная (RTF внизу справа в Gazebo < 30 %) | Не включена видеокарта (раздел 4), выключить RViz и сенсоры. |
| `source: command not found` | Команда введена в PowerShell, а не в Ubuntu. Сначала `wsl -d Ubuntu-24.04`. |
| В RViz нет препятствий | RViz показывает только данные сенсоров; при `disable_d455`/`disable_velodyne_lidar` их нет. Объекты видны в окне Gazebo. |
| Робот реагирует с задержкой | Нормально при RTF < 100 %: 1 с симуляции идёт дольше 1 с реального времени. |
