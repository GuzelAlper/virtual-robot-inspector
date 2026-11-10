# Virtual Robot Inspector

ROS 2 ve Gazebo tabanli sanal robot denetci donem projesi.

## Proje hedefi

Sistem, sanal bir mobil robotu kontrol ederek tanimli kontrol noktalarini ziyaret eder, engellere tepki verir, sanal inceleme yapar ve gorev sonucunu kaydeder. Gorev mantigi, ortak bir robot arayuzu ve degistirilebilir platform adaptorleri sayesinde belirli bir robot veya simulatora bagimli olmaz.

## Ekip

- Alper: sistem mimarisi, Robot API, Mission Manager, Mock Adapter, raporlama ve testler
- Ozgur: Gazebo dunyasi, robot modeli, sensorler, Nav2 ve Gazebo Adapter
- Ortak: entegrasyon, kabul testleri, dokumantasyon ve sunum

## Planlanan teknoloji

- Ubuntu 24.04
- ROS 2 Jazzy
- Gazebo Harmonic
- Nav2
- Python ve rclpy
- OpenCV
- YAML ve JSON

## Harici robot modeli

Simulasyonda Unitree Go2 icin asagidaki acik kaynak ROS 2 paketi kullanilir:

- [khaledgabr77/unitree_go2_ros2](https://github.com/khaledgabr77/unitree_go2_ros2)

Bu depo ROS 2 Jazzy, Gazebo Harmonic, CHAMP tabanli hareket kontrolu, RViz ve sanal sensor destegi saglar. Kaynak kodu bu projeye kopyalamak yerine kurulum sirasinda ayri bir bagimlilik olarak klonlanir. Tekrarlanabilir kurulum icin calisan commit kimligi daha sonra sabitlenecektir.

## Depo yapisi

```text
config/       Gorev, robot ve Nav2 ayarlari
docs/         Mimari, kurulum ve test belgeleri
simulation/   Gazebo dunyalari, modeller ve haritalar
src/          ROS 2 paketleri ve uygulama kodu
tests/        Birim ve entegrasyon testleri
scripts/      Kurulum ve yardimci komutlar
```

## Gelistirme kurali

`main` dalina dogrudan kod gonderilmez. Her is icin bir GitHub Issue ve ayri bir `feature/...` dali acilir. Degisiklikler diger ekip uyesinin inceleyecegi Pull Request ile birlestirilir.

Kurulum icin [docs/INSTALLATION.md](docs/INSTALLATION.md), ilk demonstrasyon kapsami icin [docs/MVP.md](docs/MVP.md) dosyasina bakin.

