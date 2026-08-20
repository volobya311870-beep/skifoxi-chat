[app]
# Название приложения на экране телефона
title = SkiFoxi Mesh

# Название пакета для системы Android
package.name = skifoxi_mesh
package.domain = org.skifoxi

# Имя вашего главного файла с кодом
source.include_exts = py

# Версия нашей сборки
version = 1.0.0

# Требования к библиотекам (Kivy и jnius для Wi-Fi Direct обязательно!)
requirements = python3, kivy, jnius

# Ориентация экрана (фиксируем вертикально, чтобы чат не прыгал)
orientation = portrait

# ТАКТИЧЕСКИЕ РАЗРЕШЕНИЯ ANDROID (Без них Wi-Fi Direct ослепнет!)
# Нам нужен интернет, доступ к Wi-Fi и геолокация (Android требует её для сканирования Wi-Fi)
android.permissions = INTERNET, ACCESS_WIFI_STATE, CHANGE_WIFI_STATE, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, NEARBY_WIFI_DEVICES

# Минимальная и целевая версии Android (подходит для большинства современных смартфонов)
android.api = 33
android.minapi = 21

# Режим сборки
release = False
