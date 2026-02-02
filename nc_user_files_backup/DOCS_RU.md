# Nextcloud User Files Backup

## Конфигурация

Home Assistant OS не предоставляет прямого доступа к USB-накопителям.
Для использования внешних дисков их необходимо заранее примонтировать в систему
и присвоить разделам уникальные метки файловой системы.
Метки используются аддоном для идентификации устройств.

## Подготовка системы

Для настройки монтирования дисков требуется доступ к системе Home Assistant
OS по SSH.

[![Developer docs – Home Assistant OS Debugging](https://img.shields.io/badge/Developer%20docs-Home%20Assistant-blue?logo=home-assistant&logoColor=white&labelColor=41B3A3)](https://developers.home-assistant.io/docs/operating-system/debugging)

После получения доступа:

1. Подключите внешний диск.
2. Присвойте разделу метку файловой системы.
3. Настройте автоматическое монтирование по метке.

Пример назначения метки разделу:

```bash
e2label /dev/sdb2 NC_backup
```

Для автоматического монтирования дисков автор использует решение на основе
[udev](https://gist.github.com/microraptor/be170ea642abeb937fc030175ae89c0c).
Автор решения: [microraptor](https://gist.github.com/microraptor).
Настройте правило монтирования в соответствии с инструкцией.

## Настройки аддона

### Файл конфигурации

После первого запуска аддон создаёт файл конфигурации settings.yaml.
Файл необходимо отредактировать в соответствии с вашей системой.

Расположение файла конфигурации:

```bash
Внутри аддона:

    /config/settings.yaml

В пользовательском интерфейсе Home Assistant:

    /addon_configs/901f89a0_nc_user_files_backup/settings.yaml
```

### Параметры конфигурации

```text
general.  
Общие настройки

- timezone (string, default: Europe/Moscow)  
  Часовой пояс

- schedule (string, default: 0 3 * * *)  
  Расписание запуска в формате cron

- rsync_options (string, default: -aHAX --delete)  
  Параметры rsync

- test_mode (bool, default: false)  
  Режим тестового выполнения

storage.  
Настройки хранения

- mount_path (string, default: media)  
  Базовый путь для монтирования

- label_backup (string, default: NC_backup)  
  Метка диска для резервных копий

- label_data (string, default: Cloud)  
  Метка диска с данными

- data_dir (string, default: data)  
  Каталог данных Nextcloud

power.  
Управление питанием

- enable_power (bool, default: true)  
  Включить управление питанием

- disc_switch (string, default: usb_disk_power)  
  Идентификатор выключателя без домена switch

notifications.  
Уведомления

- enable_notifications (bool, default: true)  
  Включить уведомления

- notification_service (string, default: send_message)  
  Сервис отправки уведомлений без домена notify

- success_message (string)  
  Сообщение об успешном завершении

- error_message (string)  
  Сообщение об ошибке
```

### Пример конфигурации

```yaml
general:
  timezone: Europe/Moscow
  schedule: 0 3 * * *
  rsync_options: -aHAX --delete
  test_mode: false

storage:
  mount_path: media
  label_backup: NC_backup
  label_data: Cloud
  data_dir: data

power:
  enable_power: true
  disc_switch: usb_disk_power

notifications:
  enable_notifications: false
  notification_service: telegram_cannel_system
  success_message: Nextcloud user files backup completed successfully!
  error_message: Nextcloud backup completed with errors!
```

Изменения конфигурации применяются при следующем запуске аддона.

## Принцип работы

При запуске аддон выполняет следующие шаги:

1. Включает питание внешнего диска (если включено управление питанием)
2. Монтирует диск резервного копирования
3. Выполняет инкрементное резервное копирование с использованием rsync
4. Отмонтирует диск
5. Отключает питание диска (если включено)
6. Отправляет уведомление о результате выполнения

### Первый запуск

При первом запуске аддон создаёт файл конфигурации и завершает работу без
выполнения резервного копирования.
После редактирования settings.yaml аддон готов к работе.

### Повторные запуски

При последующих запусках аддон инициализирует планировщик cron и ожидает
наступления заданного времени для выполнения резервного копирования.

### Тестовый режим

При включённом параметре test_mode аддон не выполняет фактическое копирование данных.
Вместо этого выполняется симуляция всех этапов без изменения файлов.

## Частые проблемы

- Configuration validation failed  
  Проверьте синтаксис и наличие обязательных параметров в settings.yaml.

- Backup disk not mounted  
  Проверьте метки файловых систем и правила udev.
