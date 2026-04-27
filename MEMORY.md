# Idealista-Notion Sync — Project Memory

## Overview
Daily sync of property listings from Idealista agency pages to Notion database "Residential Properties".

## Key Files
- `agencies_queue.json` — rotation queue of agency URLs (processed one per day)
- `scripts/deep_sync_v2.py` — main sync script (uses Playwright internally)
- `SKILL.md` — full skill documentation

## Database IDs
- Residential Properties: `21512f74-2f9e-8153-bdda-c3df73a32f59`

## Notes
- Script uses Playwright internally — do NOT use web_fetch or browser tool directly
- idealista.com blocks web_fetch requests (403)
- No other MEMORY.md, DESIGN.md or config files exist in this project

## 2026-04-26
- По команде Валерия остановлен Idealista → Notion sync: OpenClaw cron `idealista_daily_sync` отключён, активный процесс `deep_sync_v2.py ... --fill-empty` принудительно остановлен. Причина: синк работает неверно, до разборки не включать.

### Требования Валерия к Idealista sync (26.04.2026)
- Синк сейчас отключён до исправления. Валерий удалил плохие синхронизации и оставил одну тестовую страницу Notion Calle de Sant Vicent Màrtir.
- Требования: дедупликация должна быть качественной по stable Idealista ID/URL, Map не должен хранить ссылку Idealista, поля объекта должны заполняться всеми данными из объявления, фото только фото недвижимости без логотипов/energy scale/мусора, описание должно быть чистым продающим текстом абзацами без auto-translate строк, браузерные вкладки должны закрываться после каждого объекта.

### Реализация rework Idealista sync (26.04.2026)
- Добавлены правила работы: Notion ID = stable Idealista property id, URL = нормализованный source URL, Map очищается и не используется для ссылки Idealista.
- Константы для каждой страницы: Email www.realestatespain.net@gmail.com, Phone +34744728273, Комиссия `0.05`, Ваш% комиссии `0.50`.
- Properties заполняются из объявления: Price, Address, Type, Area, Bedrooms, Bathroom, Этаж, Year Built, Amenities, Description, Cover.
- Фото: собираются только id.pro.es.image.master Idealista, без webp-дублей/логотипов/служебных картинок; до 30 фото идут в property Cover, внутри страницы строится блок фотографий через column_list на 4 колонки.
- Описание: чистится от строк автоперевода и юридического мусора, разбивается на абзацы, дополняется фактами объекта.
- Вкладки объекта закрываются через `finally`; при обновлении страницы старые блоки архивируются и заменяются, не накапливаются дубли.
- Тестовый объект Calle de Sant Vicent Màrtir (110213328) прогнан вручную: поля заполнились, Map=null, Cover=22, Type=Piso, Area=342, Bedrooms=6, Bathrooms=3, Этаж=7, Year Built=1957.

- idealista_daily_sync включён обратно по команде Валерия после rework. Следующий запуск по расписанию: ежедневно 10:00 Europe/Madrid.

- Убраны упоминания исходных агентств из Idealista sync: описание/блоки не должны писать K&N Elite/Sfero/Lux Cullera/Best Broker, объекты позиционируются как i-Club. Старые страницы очищены скриптом 	emp/clean_agency_mentions.py: pages_updated=12, blocks_updated=26. Cron перенесён на ежедневный ночной запуск 30 4 * * * Europe/Madrid.
