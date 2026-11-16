#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROS_DISTRO=jazzy
ROS_WS="$HOME/ros2_ws"
GO2_SRC="$ROS_WS/src/unitree_go2_ros2"
INSPECTOR_SRC="$ROS_WS/src/inspector_world"
VENV="$HOME/inspection_venv"
MODEL_DIR="$HOME/inspection_models"
FACTORY_DIR="$HOME/factory_scene"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

source /etc/os-release
[[ "${VERSION_ID:-}" == "24.04" ]] || die "Ubuntu 24.04 is required; found ${VERSION_ID:-unknown}."

say "Installing ROS 2 Jazzy and system dependencies"
sudo apt-get update
sudo apt-get install -y software-properties-common curl git rsync python3-venv python3-pip
sudo add-apt-repository -y universe

if [[ ! -f /etc/apt/sources.list.d/ros2.sources && ! -f /etc/apt/sources.list.d/ros2.list ]]; then
  ROS_APT_SOURCE_VERSION="$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | sed -n 's/.*"tag_name": "\([^"]*\)".*/\1/p')"
  [[ -n "$ROS_APT_SOURCE_VERSION" ]] || die "Could not determine ros-apt-source version."
  curl -fL -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${VERSION_CODENAME}_all.deb"
  sudo dpkg -i /tmp/ros2-apt-source.deb
fi

sudo apt-get update
sudo apt-get install -y \
  ros-jazzy-desktop ros-dev-tools ros-jazzy-ros-gz ros-jazzy-navigation2 \
  ros-jazzy-gz-ros2-control ros-jazzy-xacro ros-jazzy-robot-localization \
  ros-jazzy-ros2-controllers ros-jazzy-ros2-control ros-jazzy-velodyne \
  ros-jazzy-velodyne-description ros-jazzy-teleop-twist-keyboard \
  ros-jazzy-rqt-image-view python3-opencv python3-yaml python3-pil

source /opt/ros/jazzy/setup.bash
mkdir -p "$ROS_WS/src"

say "Installing the Unitree Go2 simulation model"
if [[ ! -d "$GO2_SRC/.git" ]]; then
  git clone https://github.com/khaledgabr77/unitree_go2_ros2.git "$GO2_SRC"
fi

CAMERA_PATCH="$REPO_ROOT/patches/unitree_camera_bridge.patch"
if git -C "$GO2_SRC" apply --check "$CAMERA_PATCH" 2>/dev/null; then
  git -C "$GO2_SRC" apply "$CAMERA_PATCH"
elif git -C "$GO2_SRC" apply --reverse --check "$CAMERA_PATCH" 2>/dev/null; then
  say "Camera bridge patch is already applied"
else
  die "The Unitree camera bridge patch does not match the downloaded repository."
fi

sed -i \
  's/max_linear_velocity_x : 0.3/max_linear_velocity_x : 0.5/; s/max_angular_velocity_z : 0.5/max_angular_velocity_z : 0.8/' \
  "$GO2_SRC/unitree_go2_sim/config/gait/gait.yaml"

if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  sudo rosdep init
fi
rosdep update
rosdep install --from-paths "$ROS_WS/src" --ignore-src -r -y

say "Installing the inspector ROS 2 package"
mkdir -p "$INSPECTOR_SRC"
rsync -a --delete --exclude '__pycache__' "$REPO_ROOT/inspector_world/" "$INSPECTOR_SRC/"
chmod +x "$INSPECTOR_SRC"/tools/*.py "$INSPECTOR_SRC"/tools/*.sh

say "Creating the Python environment and installing PyTorch"
python3 -m venv --system-site-packages "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu \
  torch==2.12.0 torchvision==0.27.0

say "Installing the two final neural-network models"
mkdir -p "$MODEL_DIR"
install -m 0644 "$SCRIPT_DIR/models/best_gauge_locator.pt" "$MODEL_DIR/best_gauge_locator.pt"
install -m 0644 "$SCRIPT_DIR/models/best_gauge_distribution_reader.pt" \
  "$MODEL_DIR/best_gauge_distribution_reader.pt"
mkdir -p "$FACTORY_DIR"

say "Building the ROS 2 workspace"
cd "$ROS_WS"
colcon build --symlink-install

grep -qxF 'source /opt/ros/jazzy/setup.bash' "$HOME/.bashrc" || \
  echo 'source /opt/ros/jazzy/setup.bash' >> "$HOME/.bashrc"
grep -qxF 'source "$HOME/ros2_ws/install/setup.bash"' "$HOME/.bashrc" || \
  echo 'source "$HOME/ros2_ws/install/setup.bash"' >> "$HOME/.bashrc"

source "$ROS_WS/install/setup.bash"
python -c "import torch, torchvision; print('PyTorch:', torch.__version__)"
ros2 pkg executables inspector_world | grep -E 'route_runner|gauge_reader|inspection_db'

say "Installation complete"
printf '%s\n' \
  "Models: $MODEL_DIR" \
  "Database: $HOME/inspection_data/inspection.db" \
  "Reports: $HOME/inspection_reports/<date_time>/report.md" \
  "Custom factory files: $FACTORY_DIR" \
  "Start: double-click START_ROBOT_INSPECTOR.cmd on the Windows Desktop"
