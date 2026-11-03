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

Detayli gorev ve zaman plani icin [docs/WORK_PLAN.md](docs/WORK_PLAN.md), ilk demonstrasyon kapsami icin [docs/MVP.md](docs/MVP.md) dosyasina bakin.

