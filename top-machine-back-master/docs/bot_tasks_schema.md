## Таблица bot_tasks

### Схема
| Поле | Тип | Default | Описание |
|------|-----|---------|----------|
| id | SERIAL PRIMARY KEY | auto | Уникальный ID |
| application_id | INTEGER NOT NULL | - | FK → applications(id) ON DELETE CASCADE |
| target_site | VARCHAR(500) NOT NULL | - | Целевой сайт для захода |
| keyword | VARCHAR(500) NOT NULL | - | Ключевая фраза для поиска |
| daily_visit_count | INTEGER NOT NULL | 0 | Счётчик заходов за сегодня |
| daily_visit_target | INTEGER NOT NULL | 50 | Целевое количество заходов в день |
| proxy_url | VARCHAR(1000) | NULL | Прокси ссылка (socks5://login:pass@server:port) |
| successful_visits | INTEGER | NULL | Общее кол-во успешных заходов (null = бот не начал) |
| failed_visits | INTEGER NOT NULL | 0 | Общее кол-во неуспешных попыток |
| is_paused | BOOLEAN NOT NULL | FALSE | Флаг паузы (менеджер может остановить бота) |
| created_at | TIMESTAMP | NOW() | Дата создания |
| updated_at | TIMESTAMP | NOW() | Дата обновления |

### Кто заполняет какие поля
**Админ/менеджер** (через админ панель): target_site, keyword, daily_visit_target, proxy_url, is_paused
**Внешний бот** (при выполнении задач): daily_visit_count, successful_visits, failed_visits

### Флоу
1. Менеджер открывает страницу клиента в админке
2. Выбирает регион из dropdown (данные из ASocks API /dir/states, страна всегда RU id:2017370)
3. Нажимает "Получить прокси" → бэкенд вызывает ASocks POST /proxy/create-port → возвращает proxy URL
4. Менеджер заполняет форму задачи: целевой сайт, ключевую фразу, количество заходов в день
5. Proxy URL автоматически подставляется из шага 3 (или вводится вручную)
6. Задача сохраняется в таблицу bot_tasks
7. Внешний бот периодически читает задачи из таблицы, использует proxy_url, ходит на target_site
8. Бот обновляет daily_visit_count, successful_visits, failed_visits
9. Менеджер может поставить задачу на паузу (is_paused = true) или возобновить

### API эндпоинты
| Метод | Путь | Описание |
|-------|------|----------|
| GET | /admin/asocks/regions | Получить регионы RU из ASocks |
| POST | /admin/asocks/create-proxy?state=... | Создать прокси порт |
| GET | /admin/asocks/balance | Баланс ASocks аккаунта |
| GET | /admin/applications/{app_id}/bot-tasks | Список задач бота для проекта |
| POST | /admin/applications/{app_id}/bot-tasks | Создать задачу |
| PATCH | /admin/bot-tasks/{task_id}/pause | Пауза/возобновление |
| PATCH | /admin/bot-tasks/{task_id}/proxy | Назначить прокси |
| DELETE | /admin/bot-tasks/{task_id} | Удалить задачу |

### Заметки
- daily_visit_count сбрасывается внешним ботом или кроном (пока не реализовано на бэке)
- successful_visits = null означает бот ещё не начал работу
- ON DELETE CASCADE: при удалении проекта все задачи бота удаляются автоматически
