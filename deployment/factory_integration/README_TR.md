# Yeni fabrika ortamına kurulum paketi

Bu klasör, Unitree Go2 robotunu, Nav2 rotasını, gösterge okuma modellerini,
SQLite kayıt sistemini ve görev raporunu ikinci bilgisayarda kurmak içindir.

## En kolay kurulum

1. Windows'ta **WSL Ubuntu 24.04** kurulu değilse yönetici PowerShell'de:

   ```powershell
   wsl --install -d Ubuntu-24.04
   ```

2. Bu GitHub dalını ZIP olarak indirip çıkart veya Git ile klonla:

   ```powershell
   git clone --branch codex/factory-integration --single-branch https://github.com/GuzelAlper/virtual-robot-inspector.git
   ```

3. Depo içindeki `INSTALL_ON_FRIEND_PC.cmd` dosyasına çift tıkla. Kurulum; ROS 2
   Jazzy, Gazebo Harmonic, Go2, Nav2, Python ortamı, PyTorch, iki final model ve
   `inspector_world` paketini hazırlar.

4. Kurulum sonunda masaüstüne kopyalanan `START_ROBOT_INSPECTOR.cmd` dosyasına
   çift tıkla. `STOP_ROBOT_INSPECTOR.cmd` bütün ROS/Gazebo süreçlerini kapatır.

## Yeni fabrika sahnesini bağlama

Arkadaşının hazırladığı ortam Gazebo Harmonic uyumlu bir `.sdf` dosyası olmalı.
Mesh ve texture kullanıyorsa ilgili klasörleri de birlikte tutmalıdır. Isaac Sim
`.usd/.usda` dosyası doğrudan kullanılamaz; önce Gazebo SDF biçimine aktarılmalıdır.

Yeni ortam için üç dosya gerekir:

- `factory_hall.sdf`: Gazebo dünyası;
- `factory_map.yaml` ve yanında referans verdiği `.pgm`: Nav2 haritası;
- `factory_route.yaml`: başlangıç, bitiş ve kontrol noktaları.

Bu dosyaları Ubuntu içindeki `~/factory_scene/` klasörüne koy. Model/texture
klasörleri varsa `~/factory_scene/models/` altına koy. Ardından Windows masaüstündeki
`START_CUSTOM_FACTORY.cmd` dosyasına çift tıkla; başlangıç konumu
`factory_route.yaml` dosyasından otomatik okunur.

Geçici test komutu:

```bash
source ~/inspection_venv/bin/activate
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

ros2 launch inspector_world inspection_mission.launch.py \
  world:=/tam/yol/factory_hall.sdf \
  map:=/tam/yol/factory_map.yaml \
  route:=/tam/yol/factory_route.yaml \
  spawn_x:=0.0 spawn_y:=0.0 spawn_yaw:=0.0 \
  software_render:=false camera_view:=true ai:=true ai_view:=true
```

`factory_route.yaml`, mevcut `inspector_world/config/route.yaml` ile aynı yapıdadır.
Her cihaz için robotun duracağı `x`, `y`, `yaw` koordinatları girilir. Yeni cihazlar
P-01, P-02, T-01 ve V-01 ile aynı görsel tür/ölçekteyse mevcut model kullanılabilir.
Farklı gösterge türü veya skala varsa modelin veri seti genişletilmelidir.

## Çalışınca oluşan dosyalar

- SQLite: `~/inspection_data/inspection.db`
- Görev raporu: `~/inspection_reports/<tarih_saat>/report.md`
- JSON/CSV: raporla aynı klasörde
- AI görüntüleri: rapor klasöründe `*_AI.png`

Rapor; rota başarısını, modelin okuduğu değeri, birimi, `OK/ALARM` durumunu,
güven oranını ve görüntüleri içerir. Her çalıştırma ayrı tarih-saat klasörüne yazılır.

## GitHub'dan güncelleme

Depo klasöründe:

```powershell
git pull origin codex/factory-integration
```

Kod veya fabrika sahnesi güncellendikten sonra `INSTALL_ON_FRIEND_PC.cmd` yeniden
çalıştırılabilir. Betik mevcut ROS çalışma alanını günceller ve tekrar derler.
