# Админ-панель TopMashina — План реализации

## Стек
- **Frontend:** Vue 3 (Vite), Reka UI, Tailwind CSS
- **Цветовая схема:** светло-голубые/синие оттенки
- **Backend:** расширяем существующий FastAPI бэкенд (новые роуты `/admin/`)
- **БД:** PostgreSQL (существующая база top-machine)

---

## Фаза 1 — Backend: БД и авторизация админов

### 1.1 Миграция: таблица `admin_users`
```
admin_users:
  id             SERIAL PRIMARY KEY
  email          VARCHAR(255) UNIQUE NOT NULL
  password_hash  VARCHAR(255) NOT NULL
  name           VARCHAR(255) NOT NULL
  role           admin_role ENUM ('superadmin', 'admin', 'manager')
  is_active      BOOLEAN DEFAULT TRUE
  created_at     TIMESTAMP DEFAULT NOW()
```

### 1.2 Миграция: таблица `admin_invites`
```
admin_invites:
  id             SERIAL PRIMARY KEY
  email          VARCHAR(255) NOT NULL
  role           admin_role NOT NULL
  token          VARCHAR(255) UNIQUE NOT NULL
  invited_by     INT REFERENCES admin_users(id)
  expires_at     TIMESTAMP NOT NULL
  used           BOOLEAN DEFAULT FALSE
  created_at     TIMESTAMP DEFAULT NOW()
```

### 1.3 Миграция: добавить `manager_id` в `applications`
```
ALTER TABLE applications ADD COLUMN manager_id INT REFERENCES admin_users(id);
```

### 1.4 Роуты авторизации админов (`/admin/auth/`)
- [x] `POST /admin/auth/login` — логин по email/password, возвращает JWT
- [x] `POST /admin/auth/invite` — создание приглашения (admin+ может звать admin и manager, superadmin — всех)
- [x] `POST /admin/auth/register` — регистрация по invite-токену
- [x] `GET /admin/auth/me` — текущий профиль

### 1.5 Middleware: проверка ролей
- [x] `require_admin_role(min_role)` — декоратор/зависимость для проверки роли

---

## Фаза 2 — Backend: API для управления

### 2.1 Клиенты (`/admin/clients/`)
- [x] `GET /admin/clients/` — список клиентов (пагинация, поиск, фильтр)
- [x] `GET /admin/clients/{id}` — детали клиента (проекты, платежи, баланс)
- [x] `PATCH /admin/clients/{id}` — редактирование (telegram, телефон, имя)

### 2.2 Заявки (`/admin/applications/`)
- [x] `GET /admin/applications/` — список заявок (фильтр по статусу, дате)
- [x] `GET /admin/applications/{id}` — детали заявки
- [x] `PATCH /admin/applications/{id}/status` — принять/отклонить
- [x] `PATCH /admin/applications/{id}/manager` — назначить менеджера

### 2.3 Проекты (`/admin/projects/`)
- [x] `GET /admin/projects/{id}` — детали проекта с ключевыми словами
- [x] `PATCH /admin/projects/{id}` — редактирование (регион, сайт, слова)

### 2.4 Команда (`/admin/team/`)
- [x] `GET /admin/team/` — список админов и менеджеров
- [x] `DELETE /admin/team/{id}` — деактивация пользователя

### 2.5 Статистика (`/admin/stats/`)
- [x] `GET /admin/stats/dashboard` — общая статистика (кол-во клиентов, заявок, сумма платежей)

---

## Фаза 3 — Frontend: инициализация проекта

### 3.1 Scaffolding
- [x] `npm create vue@latest` с TypeScript, Vue Router, Pinia
- [x] Установить Tailwind CSS, Reka UI
- [x] Настроить цветовую палитру (голубые/синие тона)
- [x] Настроить прокси API на бэкенд

### 3.2 Layouts
- [x] Sidebar layout: боковая навигация (Клиенты, Заявки, Команда, Настройки)
- [x] Auth layout: страницы логина/регистрации

---

## Фаза 4 — Frontend: страницы

### 4.1 Авторизация
- [x] `/login` — вход
- [x] `/invite/:token` — регистрация по приглашению

### 4.2 Дашборд
- [x] `/` — общая статистика, последние заявки

### 4.3 Клиенты
- [x] `/clients` — таблица клиентов с поиском
- [x] `/clients/:id` — карточка клиента (проекты, платежи, история)

### 4.4 Заявки
- [x] `/applications` — таблица заявок, фильтры по статусу
- [x] Действия: принять, отклонить, назначить менеджера

### 4.5 Команда
- [x] `/team` — список админов/менеджеров
- [x] Кнопка "Пригласить" → модалка с формой (email + роль)

---

## Порядок работы

| #  | Задача                              | Зависимости |
|----|-------------------------------------|-------------|
| 1  | Миграции БД (admin_users, invites, manager_id) | — |
| 2  | DB queries для админов              | 1 |
| 3  | Admin auth роуты + JWT middleware   | 2 |
| 4  | Admin API: клиенты, заявки, проекты | 2 |
| 5  | Admin API: команда, статистика      | 2 |
| 6  | Создать seed-скрипт для superadmin  | 2 |
| 7  | Scaffold Vue 3 проект               | — |
| 8  | Auth страницы (login, invite)        | 3, 7 |
| 9  | Layout + sidebar навигация          | 7 |
| 10 | Страницы: дашборд, клиенты, заявки  | 4, 9 |
| 11 | Страницы: команда, приглашения      | 5, 9 |

---

## Заметки
- JWT для админов отдельный от клиентских (разный secret или prefix)
- Superadmin создается через seed-скрипт (CLI), не через UI
- Приглашения по email используют существующий mail-сервис
- В будущем: чат с клиентами, расширенная аналитика
