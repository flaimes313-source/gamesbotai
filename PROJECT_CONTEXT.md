# PROJECT_CONTEXT.md — Вайбми (AI Social Game Bot)

> Этот файл — единый источник правды о проекте. Обновляется по мере развития.
> При переезде в новый чат: скопируй содержимое и вставь первым сообщением.

---

## 1. ОБЩЕЕ ОПИСАНИЕ

**Название:** Вайбми — узнай свой вайб
**Тип:** Telegram-бот — социальная AI-игра
**Репозиторий:** https://github.com/flaimes313-source/gamesbotai
**Хостинг:** BotHost (без Docker)
**Владелец:** @flaimes313 (telegram_id: 462035571)
**Бот:** @gamesaiii_bot (id: 8967140406)

### Основной цикл

ФОТО → AI-АНАЛИЗ → КАРТОЧКА → SHARE → ДРУГ → СРАВНЕНИЕ → ИГРА → MATCH → ЧАТ

### Стек

- Python 3.11 (BotHost), 3.9 (локально)
- aiogram 3.15.0
- PostgreSQL (BotHost)
- SQLAlchemy 2.0.36 (async)
- GigaChat SDK 0.1.37 (текст + Vision)
- Pillow 11.0.0 (карточки)
- YooKassa (отложено, но код готов)
- FSM: MemoryStorage (не Redis)

---

## 2. АРХИТЕКТУРА

### Структура папок
gamebot/
├── main.py # Точка входа
├── config.py # Конфиг из .env
├── requirements.txt
├── .env # НЕ в git
├── .gitignore
├── PROJECT_CONTEXT.md # Этот файл
├── webhook_server.py # HTTP-сервер (YooKassa + health)
│
├── bot/
│ ├── handlers/ # Хендлеры aiogram
│ │ ├── init.py # register_handlers()
│ │ ├── start.py # /start, /help, кнопка 📸
│ │ ├── analysis.py # Фото → анализ → карточка
│ │ ├── profile.py # 👤 Мой профиль, 📤 Поделиться, ⚙️
│ │ ├── matching.py # 🎯 Найти игроков
│ │ ├── compare.py # 👥 Сравнить
│ │ ├── tests.py # 🧪 Тесты
│ │ ├── achievements.py # 🏆 Достижения
│ │ ├── game_opt_in.py # 🎮 Социальная игра
│ │ ├── privacy.py # Настройки приватности
│ │ ├── payments.py # 💎 PRO, промокоды
│ │ ├── subscriptions.py # Обязательные подписки
│ │ ├── blocking.py # 🚫 Блокировка
│ │ ├── advertising.py # Клики по рекламе
│ │ ├── chats.py # 💬 Мои чаты
│ │ ├── messaging.py # Стили сообщений, приколы
│ │ ├── support.py # 🆘 Поддержка
│ │ └── timezone.py # 🌍 Часовой пояс
│ │
│ ├── keyboards/
│ │ ├── main.py # main_menu_kb, share_kb, settings_kb, pro_menu_kb
│ │ ├── profile.py # profile_kb
│ │ ├── matching.py # modes_kb, match_actions_kb
│ │ ├── chats.py # chat_actions_kb
│ │ ├── timezone.py # timezone_menu_kb
│ │ └── admin.py # admin_menu_kb + меню разделов
│ │
│ └── middlewares/
│ ├── feature_flags.py # BotEnabledMiddleware (bot_enabled)
│ └── mandatory_subscription.py # Hard-gate обязательной подписки
│
├── admin/
│ ├── handlers.py # /admin + все разделы
│ ├── subscriptions_wizard.py # FSM-мастер подписок
│ └── broadcast.py # FSM-мастер рассылки
│
├── services/
│ ├── ai/
│ │ ├── base.py # AIProvider (ABC)
│ │ ├── gigachat.py # GigaChatProvider
│ │ ├── yandex.py # YandexGPTProvider (заглушка)
│ │ └── factory.py # get_ai_provider() — async!
│ │
│ ├── analysis/
│ │ ├── photo_analysis.py # analyze_photo()
│ │ ├── profile_builder.py # build_profile()
│ │ └── scoring.py # clamp_scores()
│ │
│ ├── matching/
│ │ ├── matcher.py # find_candidates, create_match_record
│ │ └── compatibility.py # compatibility_score()
│ │
│ ├── cards/
│ │ ├── generator.py # generate_card()
│ │ ├── themes.py # 10+ тем по архетипам
│ │ ├── icons.py # stat_icon, achievement_icon
│ │ ├── icons_data.py # base64 PNG-иконки (генерируется)
│ │ └── fonts_embedded.py # base64 шрифты (генерируется)
│ │
│ ├── chats.py # get_or_create_chat, send_chat_message
│ ├── messaging.py # deliver_message, get_inbox
│ ├── jokes.py # random_joke, categories
│ ├── premium.py # is_premium()
│ ├── whitelist.py # is_whitelisted, add/remove
│ ├── access.py # has_full_access, access_level
│ ├── rate_limit.py # check_and_increment (1/day FREE, 50/day PRO)
│ ├── feature_flags.py # is_enabled, set_flag, get_all_flags
│ ├── achievements.py # unlock_achievement
│ ├── experiments.py # A/B тесты промтов
│ ├── experiments_report.py # Отчёт A/B
│ ├── timezones.py # get_local_hour, humanize_datetime
│ ├── metrics.py # full_stats, funnel_stats, chats_stats
│ │
│ ├── share_calls.py # Персональные призывы по архетипу
│ │
│ ├── analytics/
│ │ ├── tracker.py # track() — все события
│ │ └── funnel.py # get_funnel, format_funnel
│ │
│ ├── advertising/
│ │ ├── broadcaster.py # maybe_send_ad
│ │ └── reports.py # ads_report
│ │
│ ├── notifications/
│ │ ├── daily_sender.py # Ежедневный AI-результат в 20:00 локально
│ │ ├── chat_reminder.py # Напоминание о неответе 24ч
│ │ ├── premium_reminder.py # За 3д, 1д и после истечения PRO
│ │ └── db_cleanup.py # Чистка старых записей (30-90 дней)
│ │
│ ├── subscriptions/
│ │ ├── checker.py # is_subscribed (учитывает whitelist)
│ │ ├── link_parser.py # parse_channel_link
│ │ └── channel_resolver.py # resolve_channel (Telegram API)
│ │
│ └── payments/
│ └── yookassa_client.py # create_pro_payment
│
├── database/
│ ├── connection.py # engine, async_session, get_session
│ ├── models.py # Все ORM-модели
│ ├── queries.py # (заготовка)
│ ├── init_db.py # create_all + миграции
│ ├── seed_tests.py # 10 тестов
│ └── seed_achievements.py # 11 достижений
│
├── prompts/
│ ├── photo_analysis.py # PHOTO_ANALYSIS_PROMPT (v1)
│ ├── photo_analysis_v2.py # PHOTO_ANALYSIS_PROMPT_V2
│ ├── daily_result.py # DAILY_RESULT_PROMPT
│ ├── match_description.py # MATCH_DESCRIPTION_PROMPT
│ ├── message_helper.py # MESSAGE_HELPER_PROMPT
│ ├── test_question.py # TEST_QUESTION_PROMPT
│ ├── test_result.py # TEST_RESULT_PROMPT
│ └── chat_helper.py # CHAT_REPLY_PROMPT, CHAT_ANALYSIS_PROMPT
│
├── utils/
│ └── logging.py # setup_logging, get_logger
│
├── tools/
│ ├── build_embedded_fonts.py # Генерирует fonts_embedded.py
│ └── build_embedded_icons.py # Генерирует icons_data.py
│
├── data/
│ ├── fonts/ # TTF для сборки (в git)
│ ├── icons/ # PNG для сборки (в git)
│ ├── jokes.json # 7 категорий приколов
│ └── test_card.png # не в git
│
└── logs/ # НЕ в git

### Порядок роутеров в `register_handlers()`

```python
# 1. Админка + FSM-мастера
admin_handlers.router
subs_wizard_router
broadcast_router

# 2. Пользовательские
start, analysis, profile, timezone, matching, compare,
tests, achievements, game_opt_in, privacy, payments,
subscriptions, blocking, advertising

# 3. Чаты — до catch-all
chats.router

# 4. Catch-all
messaging.router   # PENDING_CHAT_REPLY → text
support.router     # PENDING_TICKET → text
3. БАЗА ДАННЫХ
Все таблицы (PostgreSQL)

users
text

id, telegram_id (unique), username, first_name, language,
timezone (default 'Europe/Moscow'), timezone_confirmed,
created_at, last_active_at,
is_blocked, is_admin, is_whitelisted,
participates_in_game,
show_photo (default False), show_username (default False),
show_profile (default True), allow_messages (default True),
premium_until,
referrer_id (BigInteger),
last_subscription_offer, last_ad_received

profiles
text

id, user_id FK,
archetype, description,
charisma, confidence, humor, energy, sociability,
intellect, creativity, calmness, chaos, leadership,
funny_trait, danger_level, friendship_score, vibe,
created_at, updated_at

photo_analyses
text

id, user_id FK,
telegram_file_id, telegram_file_unique_id,
analysis_json (JSON), model, prompt_version,
created_at

tests / user_tests
text

tests: id, name, description, is_active, is_premium, sort_order
user_tests: id, user_id, test_id, result_json, created_at

matches
text

id, user1_id, user2_id, match_type, score, status,
created_at
UNIQUE (user1_id, user2_id)

chats
text

id, user1_id, user2_id,
user1_last_read_msg_id, user2_last_read_msg_id,
created_at, updated_at
UNIQUE (user1_id, user2_id) — user1_id < user2_id

messages
text

id, chat_id FK, sender_id, receiver_id,
type ('text'/'joke'), text, status, is_read,
created_at

chat_reports
text

id, chat_id, reporter_id, target_id, reason, status, created_at

achievements / user_achievements
text

achievements: id, code (unique), title, description, emoji
user_achievements: id, user_id, achievement_code, unlocked_at
UNIQUE (user_id, achievement_code)

feature_flags
text

id, key (unique), enabled, updated_at

events (аналитика)
text

id, user_id, telegram_id, name, payload (JSON), created_at

experiment_assignments (A/B)
text

id, experiment, telegram_id, variant, created_at
UNIQUE (experiment, telegram_id)

ai_usage (rate limit)
text

id, user_id, day, count
UNIQUE (user_id, day)

support_tickets
text

id, user_id, message, status ('open'/'closed'),
admin_reply, admin_id, created_at, closed_at

whitelist
text

id, user_id (BigInteger), reason, added_by, created_at, expires_at

payments
text

id, user_id, yookassa_payment_id (unique),
amount, currency, status, payment_type, description,
created_at, paid_at

promocodes
text

id, code (unique), type, value, max_uses, used_count,
expires_at, is_active

subscription_campaigns / subscription_events
text

campaigns: id, name, status, is_active,
  channel_id, channel_username, channel_link,
  price_per_subscription, subscriber_limit, budget,
  confirmed_subscribers, started_at, ended_at
events: id, campaign_id, user_id, channel_id, status,
  checked_at, confirmed_at
  UNIQUE (campaign_id, user_id)

advertising_campaigns / user_ad_events
text

campaigns: id, name, status, text, image_file_id,
  target_type, target_url, impression_limit, budget,
  price_per_impression, clicks, sent_count, started_at, ended_at
events: id, campaign_id, user_id, shown_at, clicked_at

markdown

**user_engagement** (вовлечение)

id, user_id (unique),
current_streak, max_streak, last_visit_date,
total_points, level,
archetypes_collected (JSON),
total_analyses, total_messages, total_tests, total_shares, total_referrals,
created_at, updated_at
text


**daily_challenges**

id, date (unique), title, description,
task_type, target_value, reward_points,
created_at
text


**user_challenges**

id, user_id, challenge_id, progress, status, completed_at, created_at
UNIQUE (user_id, challenge_id)
text



4. AI-СЛОЙ (GigaChat)
Провайдер

services/ai/base.py — интерфейс AIProvider:

    analyze_photo(image_bytes, prompt_override) — Vision

    generate_daily_result(profile)

    generate_match_description(profile1, profile2, match_score)

    generate_message_suggestions(my_archetype, their_archetype, match_score, style)

    generate_test_question(test_name, test_description)

    generate_test_result(test_name, answers)

    generate_chat_reply_suggestions(history, my_name, other_name)

    analyze_chat(history, my_name, other_name)

services/ai/gigachat.py — реализация.

ВАЖНО:

    get_ai_provider() — async! Всегда provider = await get_ai_provider().

    Модели из env: GIGACHAT_MODEL (текст), GIGACHAT_VISION_MODEL (Vision).

    Vision-модель обязательна для анализа фото (у нас GigaChat-2-Max).

    _extract_json — устойчив к битому JSON (автопочинка пропущенных запятых + retry).

    _chat_json — обёртка с retry (temperature 0.7 → 0.3).

    analyze_photo retry при 5xx (502, 503, 504).

Переменные .env
text

BOT_TOKEN=
DATABASE_URL=postgresql+asyncpg://...
GIGACHAT_API_KEY=
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_MODEL=GigaChat-2
GIGACHAT_VISION_MODEL=GigaChat-2-Max
ADMIN_IDS=462035571
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET=

5. КАРТОЧКА
Дизайн

    Размер: 900×1200

    Неоновая тема: градиент фон + свечения + боковая полоса

    10+ тем по ключевым словам архетипа (chaos, calm, leader, intellect, mystery, humor, creativity, danger, energy, charisma, default)

    Характеристики: PNG-иконки (Twemoji) + название + прогресс-бар с градиентом + число

    Опасность: цветная плашка (зелёная/жёлтая/красная)

    Цитата: плашка с акцентной полосой слева

    Достижения: PNG-иконки под цитатой (до 3)

    Футер: «ВАЙБМИ · узнай свой вайб» + @bot_username

    Без эмодзи в коде (DejaVu Sans их не рендерит) — только PNG-иконки

Иконки

services/cards/icons.py — кэш, stat_icon(key, size), achievement_icon(code, size).

services/cards/icons_data.py — base64 PNG. Генерируется скриптом tools/build_embedded_icons.py.

data/icons/ — исходные PNG (Twemoji, ~500-1500 байт каждый):

    stat_charisma.png (26a1 ⚡)

    stat_humor.png (1f602 😂)

    stat_chaos.png (1f9e8 🧨)

    stat_intellect.png (1f9e0 🧠)

    stat_energy.png (1f4a5 💥)

    stat_creativity.png (1f3a8 🎨)

    ach_first_photo.png (1f4f8 📸)

    ach_first_share.png (1f4e4 📤)

    ach_friend_joined.png (1f465 👥)

    ach_first_test.png (1f9ea 🧪)

    ach_five_tests.png (1f393 🎓)

    ach_chaos_90.png (1f9e8)

    ach_charisma_90.png (2728 ✨)

    ach_five_analyses.png (1f525 🔥)

    ach_first_match.png (1f3af 🎯)

    ach_ten_messages.png (1f4ac 💬)

    ach_pro_first.png (1f48e 💎)

    ach_default.png (1f3c6 🏆)

Шрифты

services/cards/fonts_embedded.py — base64 TTF. Генерируется tools/build_embedded_fonts.py.

data/fonts/ — NotoSans-Regular.ttf, NotoSans-Bold.ttf (в git).
Анализ карточки (bot/handlers/analysis.py)

    Скачивание фото.

    Rate limit (1/день FREE, 50/день PRO).

    A/B тест промта (photo_v1 / photo_v2).

    GigaChat Vision → JSON.

    Сохранение в photo_analyses + profiles.

    Достижения: first_photo, chaos_90, charisma_90, five_analyses.

    generate_card() → PNG.

    Персональный призыв (pick_share_call(archetype)).

    Caption: результат + призыв + ссылка. Reply-кнопки share_kb.

    Хук maybe_send_ad.

    ## 5.1. ВОВЛЕЧЕНИЕ (engagement)

**`services/engagement/`** — сервисы вовлечения:

- **`points.py`** — очки + 20 уровней:
  - Логика: `add_points(user_id, action, multiplier)`
  - Таблица `LEVELS` — 20 уровней с титулами
  - `level_for_points`, `title_for_level`, `points_to_next_level`
  - Награды: daily_login 5, photo_analysis 15, new_archetype 30, test_complete 20, first_message 10, share 5, invite_friend 50, challenge_complete 50, streak_bonus × N, first_login 10

- **`streaks.py`** — серии дней:
  - `update_streak(user_id)` — вызывается при /start
  - Milestones: 3, 7, 14, 30, 100 дней → достижения streak_3, streak_7 и т.д.
  - Стрик сбрасывается при пропуске дня

- **`archetypes.py`** — коллекция архетипов:
  - `add_archetype(user_id, archetype)` — добавляет, возвращает is_new
  - `get_collection`, `get_collection_stats`
  - MAX_ARCHETYPES = 20

- **`challenges.py`** — ежедневный челлендж:
  - `CHALLENGE_POOL` — 7 типов заданий
  - `get_or_create_today_challenge()` — создаёт один раз в день
  - `increment_progress(user_id, task_type, amount)` — увеличивает прогресс
  - Награда: challenge_complete 50 очков

- **`service.py`** — единый API:
  - `on_user_visit(user_id)` — стрик
  - `on_photo_analyzed(user_id, archetype)` — анализ + архетип + челлендж
  - `on_test_completed(user_id)`
  - `on_message_sent(user_id)`
  - `on_share(user_id)`
  - `on_referral(user_id)`
  - `on_compare(user_id)`

**Интеграция в существующие хендлеры:**
- `start.py` → `on_user_visit`, `on_referral`
- `analysis.py` → `on_photo_analyzed`, `on_share`
- `tests.py` → `on_test_completed`
- `messaging.py`, `chats.py` → `on_message_sent`
- `compare.py` → `on_compare`

**Очки (POINTS):**
first_login: 10, daily_login: 5, streak_bonus: ×N,
photo_analysis: 15, new_archetype: 30,
test_complete: 20, first_message: 10,
share: 5, invite_friend: 50,
challenge_complete: 50
text

Раздел 5.1 (Вовлечение): 

    bot/handlers/engagement.py — все хендлеры UI.

    bot/keyboards/engagement.py — клавиатуры.

    services/notifications/tops_sender.py — еженедельные топы.

    Кнопки в меню: 🎯 Челлендж дня, 📊 Моя статистика, 🏆 Топы.


**Уровни (LEVELS):** 20 уровней от «Новичок» (0 очков) до «ЛЕГЕНДА ВАЙБМИ» (55000).

6. СОБЫТИЯ (EVENT_NAMES)

services/analytics/tracker.py — белый список:
text

new_users, photo_sent, analysis_started, analysis_completed,
second_analysis, share_clicked, share_generated,
referral_opened, referral_completed,
game_opt_in, game_opt_out,
search_used, match_created, block_user,
test_started, test_completed,
pro_purchase, pro_gift_sent, pro_gift_received,
subscription_offer_shown, subscription_confirmed,
subscription_gate_shown, ad_shown, ad_clicked,
premium_reminder_3d, premium_reminder_1d, premium_expired,
daily_sent, chat_reminder_sent,
chats_list_viewed, chat_message_sent,
chat_ai_sent, chat_ai_analyzed,
message_sent, joke_sent, inbox_viewed

ВАЖНО: при добавлении новых событий — добавлять их в EVENT_NAMES.
7. FEATURE FLAGS

Хранятся в БД. Управляются через /admin → ⚙️ Feature flags.

Список:
Flag	Дефолт	Где проверяется
bot_enabled	True	bot/middlewares/feature_flags.py
ai_enabled	True	services/ai/factory.py
matching_enabled	True	bot/handlers/matching.py
referrals_enabled	True	bot/handlers/start.py
mandatory_subscriptions_enabled	False	bot/middlewares/mandatory_subscription.py
advertising_enabled	False	services/advertising/broadcaster.py
premium_enabled	False	bot/handlers/payments.py
daily_content_enabled	False	services/notifications/daily_sender.py
friend_comparison_enabled	True	bot/handlers/compare.py
player_search_enabled	True	bot/handlers/matching.py
ai_message_helper_enabled	True	bot/handlers/chats.py

API: await is_enabled(key, default) → bool; await set_flag(key, value); await get_all_flags().
8. ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ

Hard gate через MandatorySubscriptionMiddleware (зарегистрирован на dp.message и dp.callback_query).

Логика:

    /start, /help, /cancel, sub_check_* — пропускаются.

    Админ / whitelist / PRO — пропускаются.

    Если есть активная кампания и юзер не подписан → любое действие блокируется.

    Показывается экран со всеми активными каналами (до 3 через LIMIT 3).

    Кнопка «✅ Я подписался на все» проверяет все каналы.

    Если хоть один не подтверждён — экран с недостающими.

    Все подтверждены → пуск.

Важно:

    Middleware на message и callback_query, НЕ на update. Иначе event = Update и всё ломается.

    Всегда _safe_answer для callback.

    URL канала: channel_link или https://t.me/{channel_username}.

Кампании создаются через /admin → 📣 Подписки → ➕ Новая кампания — FSM-мастер:

    Отправь ссылку на канал (@username или https://t.me/...).

    Бот разрешает username через Telegram API.

    Показывает превью.

    Подтверждение → создание.

9. ПРО-ПОДПИСКА

Цены: 390₽ / мес, 1990₽ / 6 мес (-15%), 3490₽ / 12 мес (-25%).

Что даёт:

    50 AI-анализов в день (вместо 1)

    Режимы «🧠 Интеллектуальный» и «🧨 Максимальный хаос»

    AI-помощник в чатах

    Без рекламы

    Обход обязательных подписок

services/rate_limit.py:

    FREE_DAILY_LIMIT = 1

    PRO_DAILY_LIMIT = 50

    ADMIN_DAILY_LIMIT = 999999

Напоминания (services/notifications/premium_reminder.py):

    За 3 дня — уведомление

    За 1 день — уведомление

    После истечения — уведомление (раз в 48 ч)

    Не приходит ночью по локали юзера

    Loop каждые 6 часов

Автопродление — ОТКЛОЖЕНО. save_payment_method=False в YooKassa.
10. ЧАТЫ

Модели: Chat (user1_id < user2_id), Message (с chat_id, is_read), ChatReport.

Список: 💬 Мои чаты — reply-кнопка → list_user_chats.

Открытие: chat_open_<id> → последние 30 сообщений + humanize_datetime.

Ответ: chat_reply_<id> → PENDING_CHAT_REPLY[user] → текст.

AI-помощник (PRO):

    chat_ai_reply_<id> → 3 варианта от GigaChat

    chat_ai_analyze_<id> → анализ переписки

    Обе проверяют ai_message_helper_enabled и has_full_access

Жалоба: chat_report_<id> → ChatReport → при 3+ жалобах автоблокировка.

Файлы:

    services/chats.py — бизнес-логика

    bot/handlers/chats.py — хендлеры

    bot/keyboards/chats.py — клавиатуры

11. РАССЫЛКА

FSM-мастер admin/broadcast.py:

Типы:

    ✍️ Только текст

    🖼 Только картинка

    🖼+✍️ Картинка + текст

Опционально: inline-кнопка с URL (Текст кнопки | https://...).

Прогресс: каждые 100 сообщений.

Заблокированные автоматически помечаются is_blocked=True.

Пауза 0.05 сек между сообщениями (лимит Telegram 30/сек).
12. ВАЖНЫЕ СОГЛАШЕНИЯ
Код

    ВСЕГДА Optional[X] вместо X | None (BotHost — 3.11, локально — 3.9).

    datetime.now(timezone.utc) вместо datetime.utcnow() — для сравнения с БД (TIMESTAMPTZ).

    await get_ai_provider() — функция async!

    _safe_answer(callback) вместо await callback.answer() в админке.

    В catch-all хендлерах — использовать динамический фильтр (проверка PENDING_REPLY / PENDING_TICKET) чтобы не перехватывать кнопки.

    logger.exception(...) — для отлова ошибок с трейсбеком.

Что НЕ работает (важно помнить)

    Эмодзи в Pillow — DejaVu Sans не рендерит. Только PNG-иконки.

    data/ на BotHost — папка пустая, если файлы не в Git (мы уже проходили). Решение: встроить в base64.

    qrcode[pil] в requirements — может ломать сборку BotHost. Использовать qrcode==8.0 или убрать.

    .gitignore — блокирует data/ целиком. Разрешить !data/fonts/, !data/icons/, !data/jokes.json.

Middleware

    dp.update.middleware(...) — event = Update, не Message.

    dp.message.middleware(...) и dp.callback_query.middleware(...) — event = Message/CallbackQuery.

13. КОМАНДЫ
Локальная разработка
powershell

cd C:\Users\Alexandr\Desktop\BOTS\gamebot
.\venv\Scripts\Activate.ps1

# Запуск
python main.py

# Тест карточки
python -c "
from services.cards.generator import generate_card
data = {
    'archetype': 'ГЛАВНЫЙ ПО ХАОСУ',
    'scores': {'charisma': 74, 'humor': 67, 'chaos': 89, 'energy': 91, 'intellect': 70, 'creativity': 75},
    'danger_level': 45,
    'short_description': 'Энергия, когда ты ешь так, будто это последний раз в жизни.',
    'achievements': ['first_photo', 'chaos_90', 'first_match'],
}
open('data/test_card.png', 'wb').write(generate_card(data, 'tester', 'gamesaiii_bot'))
print('OK')
"

# Пересобрать шрифты base64
python tools\build_embedded_fonts.py

# Пересобрать иконки base64
python tools\build_embedded_icons.py

# Деплой
git add .
git commit -m "..."
git push

BotHost

    Redeploy (не Restart) — для пересборки образа.

    Clear cache + Redeploy — если кеш.

14. ИСТОРИЯ ПРОБЛЕМ И РЕШЕНИЙ
Проблема	Решение
GigaChat 400 application/octet-stream	BytesIO с .name = "photo.jpg"
GigaChat 422 Model does not support image	Отдельная GIGACHAT_VISION_MODEL=GigaChat-2-Max
GigaChat 504 Gateway Timeout	Retry 3 раза с паузами
Битый JSON от GigaChat	_extract_json с автопочинкой + retry с temp 0.3
Квадраты вместо кириллицы	Встроить DejaVu/NotoSans в base64
column support_tickets.admin_id does not exist	ALTER TABLE ... ADD COLUMN IF NOT EXISTS
VACUUM cannot run inside a transaction	isolation_level="AUTOCOMMIT"
Unknown event name	Добавить в EVENT_NAMES
Кнопка «Сравнить» не работает	Добавить @router.message(F.text == "👥 Сравнить")
coroutine was never awaited	await get_ai_provider()
Middleware не работает	Регистрировать на message/callback_query, не на update
Иконки не грузятся	Twemoji PNG + base64
bytes | None TypeError	Optional[bytes]
15. ТЕКУЩИЙ СТАТУС
Готово

    ✅ MVP: фото → AI → карточка → share

    ✅ Виральность: реферальная система, приглашения

    ✅ Социальная игра: поиск, матчи, чат

    ✅ AI-помощник в чате (PRO)

    ✅ Тесты, достижения

    ✅ Приватность, tz

    ✅ PRO с тарифами + напоминаниями

    ✅ YooKassa (код готов, не подключена)

    ✅ Реклама

    ✅ Обязательные подписки (до 3 каналов, FSM-мастер)

    ✅ Админка (12+ разделов)

    ✅ Рассылка (FSM-мастер)

    ✅ Feature flags из БД

    ✅ Rate limit 1/день

    ✅ Чистка БД

    ✅ Неоновая карточка с 10+ темами

    ✅ PNG-иконки (base64)

В работе / отложено

    🟡 Вовлечение (этап 3-5):

        Стрик (серия дней)

        Очки + уровни

        Коллекция архетипов

        Ежедневный челлендж

        Еженедельный топ

        Персональная статистика

    ❌ Автопродление PRO — отложено

    ❌ Монетизация пакетами / подарками — отложено

16. СЛЕДУЮЩИЕ ЭТАПЫ (вовлечение)
Этап 1-2 (БД + сервисы)

Новые таблицы:
text

user_engagement:
  user_id PK, current_streak, max_streak, last_visit_date,
  total_points, level,
  archetypes_collected (JSON array),
  total_analyses, total_messages, total_tests,
  updated_at

daily_challenges:
  id, date (unique), title, description, task_type, target_value,
  reward_points, created_at

user_challenges:
  id, user_id, challenge_id, progress, target,
  status ('in_progress'/'completed'), completed_at,
  UNIQUE (user_id, challenge_id)

Очки (логика):
Действие	Очки
Первый вход	10
Ежедневный вход	5
Стрик × N дней	+1×N
Анализ фото	15
Новый архетип	30
Первое сообщение в чате	10
Тест	20
Share	5
Приглашён друг	50
Челлендж дня	50

Уровни (всего 20):
Уровень	Очки	Титул
1	0	Новичок
2	50	Наблюдатель
3	150	Участник
4	300	Завсегдатай
5	500	Постоянный
6	800	Активист
7	1200	Ветеран
8	1800	Опытный
9	2600	Мастер вайба
10	3600	Гуру вайба
11	5000	Легенда
12	7000	Миф
13	9500	Хранитель
14	12500	Владыка хаоса
15	16000	Архитектор вайбов
16	20000	Творец
17	25000	Создатель
18	32000	Полубог
19	42000	Бог вайба
20	55000	ЛЕГЕНДА ВАЙБМИ

Стрики (награды):

    3 дня → достижение «3 дня подряд»

    7 дней → достижение «Неделя с Вайбми» + промокод скидка

    14 дней → «2 недели подряд»

    30 дней → «Месяц с Вайбми» + промокод на 30 дней PRO

    100 дней → «Сотка» + PRO 12 мес в подарок

Челлендж дня (примеры):

    «Отправь фото и получи архетип»

    «Пройди любой тест»

    «Отправь 3 сообщения в чате»

    «Пригласи друга»

    «Сделай 2 анализа»

    «Сравнись с другом»

    «Оцени 5 игроков» (лайки)

Топы (еженедельно, воскресенье 20:00 UTC):

    🔥 Топ-10 по хаосу

    😂 Топ-10 по юмору

    ✨ Топ-10 по харизме

    🏆 Топ-10 по очкам

    👥 Топ-5 по приглашённым друзьям

Публикуются в бот юзерам с participates_in_game и в канал партнёра.
Этап 3-5 (хендлеры + UI)

    Кнопка «🎯 Челлендж дня»

    Кнопка «📊 Моя статистика»

    Кнопка «🏅 Уровень» (в профиле)

    Публикация топов раз в неделю

    ### Этап 1-2 (БД + сервисы) — ✅ ЗАВЕРШЕН
- user_engagement, daily_challenges, user_challenges — созданы
- services/engagement/ — 5 файлов
- Интеграция в хендлеры — сделана

Этап 3-5 вовлечения — завершён

17. КАК ВОССТАНОВИТЬ КОНТЕКСТ В НОВОМ ЧАТЕ

Первое сообщение в новом чате:
text

Продолжаем работу над проектом Вайбми (Telegram AI-бот, aiogram 3.15).
Контекст проекта ниже:

[вставляешь содержимое PROJECT_CONTEXT.md]

Продолжаем с этапа 1-2 (вовлечение): БД + сервисы стрик/очки/челлендж.

Что я сделаю: прочитаю контекст, пойму проект, продолжу с указанного этапа.
18. КОНТАКТЫ И ССЫЛКИ

    GitHub: https://github.com/flaimes313-source/gamesbotai

    Бот: @gamesaiii_bot

    BotHost: https://bothost.ru

    PostgreSQL: node1.pghost.ru:16127

Секреты: только в .env (не в Git) и в панели BotHost → Environment Variables.

Версия контекста: 1.0
Последнее обновление: 2026-09-20
text


---

