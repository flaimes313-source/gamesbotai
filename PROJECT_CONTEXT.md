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
│ │ ├── timezone.py # 🌍 Часовой пояс
│ │ ├── engagement.py # 🎯 Челлендж, статистика, топы, неделя, квесты
│ │ └── info.py # ℹ️ О боте
│ │
│ ├── keyboards/
│ │ ├── main.py # main_menu_kb, share_kb, settings_kb, pro_menu_kb
│ │ ├── profile.py
│ │ ├── matching.py
│ │ ├── chats.py
│ │ ├── timezone.py
│ │ ├── admin.py
│ │ ├── engagement.py # challenge_kb, tops_kb, level_back_kb и т.д.
│ │ └── info.py
│ │
│ └── middlewares/
│ ├── feature_flags.py
│ └── mandatory_subscription.py
│
├── admin/
│ ├── handlers.py
│ ├── subscriptions_wizard.py
│ └── broadcast.py
│
├── services/
│ ├── ai/
│ │ ├── base.py
│ │ ├── gigachat.py
│ │ ├── yandex.py
│ │ └── factory.py # get_ai_provider() — async!
│ │
│ ├── analysis/
│ │ ├── photo_analysis.py # analyze_photo() + сезонный контекст
│ │ ├── profile_builder.py
│ │ └── scoring.py
│ │
│ ├── matching/
│ │ ├── matcher.py
│ │ └── compatibility.py
│ │
│ ├── cards/
│ │ ├── generator.py
│ │ ├── themes.py
│ │ ├── icons.py
│ │ ├── icons_data.py # base64 PNG-иконки
│ │ └── fonts_embedded.py # base64 шрифты
│ │
│ ├── engagement/ # Этап 5.1 + 6.2.2 + 6.3 + 7
│ │ ├── points.py # Очки, уровни, add_custom_points
│ │ ├── streaks.py # Стрики
│ │ ├── archetypes.py # Коллекция архетипов
│ │ ├── challenges.py # Дневной челлендж
│ │ ├── weekly_challenges.py # Недельный челлендж
│ │ ├── quests.py # Квесты (цепочки заданий)
│ │ ├── rewards.py # Универсальные награды (claim/grant)
│ │ ├── referral_reward.py # 10 рефералов → 7 дней PRO
│ │ ├── streak_rewards.py # PRO за стрики
│ │ ├── points_rewards.py # PRO за очки
│ │ ├── referrals.py # Реферальная логика
│ │ ├── notifications.py # Очередь уведомлений
│ │ └── service.py # Единый API (on_*)
│ │
│ ├── chats.py
│ ├── messaging.py
│ ├── jokes.py
│ ├── premium.py
│ ├── whitelist.py
│ ├── access.py
│ ├── rate_limit.py # check_and_increment(telegram_id, user_id)
│ ├── feature_flags.py
│ ├── achievements.py
│ ├── experiments.py
│ ├── experiments_report.py
│ ├── timezones.py
│ ├── metrics.py
│ ├── seasons.py # Сезоны (Хэллоуин, НГ, 8 марта, 23 февраля)
│ ├── share_calls.py
│ │
│ ├── analytics/
│ │ ├── tracker.py
│ │ └── funnel.py
│ │
│ ├── advertising/
│ │ ├── broadcaster.py
│ │ └── reports.py
│ │
│ ├── notifications/
│ │ ├── daily_sender.py
│ │ ├── chat_reminder.py
│ │ ├── premium_reminder.py
│ │ ├── tops_sender.py
│ │ └── db_cleanup.py
│ │
│ ├── subscriptions/
│ │ ├── checker.py
│ │ ├── link_parser.py
│ │ └── channel_resolver.py
│ │
│ └── payments/
│ └── yookassa_client.py
│
├── database/
│ ├── connection.py
│ ├── models.py # Все ORM-модели
│ ├── queries.py
│ ├── init_db.py # create_all + миграции
│ ├── seed_tests.py
│ └── seed_achievements.py
│
├── prompts/
│ ├── photo_analysis.py
│ ├── photo_analysis_v2.py
│ ├── daily_result.py
│ ├── match_description.py
│ ├── message_helper.py
│ ├── test_question.py
│ ├── test_result.py
│ └── chat_helper.py
│
├── utils/
│ └── logging.py
│
├── tools/
│ ├── build_embedded_fonts.py
│ └── build_embedded_icons.py
│
├── data/
│ ├── fonts/
│ ├── icons/
│ ├── jokes.json
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
start, analysis, profile, timezone, engagement, info,
matching, compare, tests, achievements, game_opt_in,
privacy, payments, subscriptions, blocking, advertising

# 3. Чаты — до catch-all
chats.router

# 4. Catch-all
messaging.router   # PENDING_CHAT_REPLY → text
support.router     # PENDING_TICKET → text
3. БАЗА ДАННЫХ

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

user_engagement (вовлечение)
text

id, user_id (unique),
current_streak, max_streak, last_visit_date,
total_points, level,
archetypes_collected (JSON),
total_analyses, total_messages, total_tests,
total_shares, total_referrals,
created_at, updated_at

daily_challenges
text

id, date (unique), title, description,
task_type, target_value, reward_points,
created_at

user_challenges
text

id, user_id, challenge_id, progress, status, completed_at, created_at
UNIQUE (user_id, challenge_id)

referral_rewards
text

id, referrer_id FK, referred_id FK (unique),
points_awarded, created_at

reward_claims (разовые награды)
text

id, user_id FK, reward_code, payload (JSON), claimed_at
UNIQUE (user_id, reward_code)

weekly_challenges
text

id, week_start (unique), title, description,
task_type, target_value, reward_points,
created_at

user_weekly_challenges
text

id, user_id FK, challenge_id FK,
progress, status, completed_at, created_at
UNIQUE (user_id, challenge_id)

quests / quest_steps / user_quest_progress
text

quests: id, code (unique), title, description,
  emoji, is_active, sort_order
quest_steps: id, quest_id FK, step_number, title, description,
  task_type, target_value, reward_points
  UNIQUE (quest_id, step_number)
user_quest_progress: id, user_id FK, quest_id FK,
  current_step, step_progress, status, started_at, completed_at
  UNIQUE (user_id, quest_id)

4. AI-СЛОЙ (GigaChat)
Провайдер

services/ai/base.py — интерфейс AIProvider:

    analyze_photo(image_bytes, prompt_override) — Vision

    generate_daily_result(profile)

    generate_match_description(profile1, profile2, match_score)

    generate_message_suggestions(...)

    generate_test_question(...)

    generate_test_result(...)

    generate_chat_reply_suggestions(...)

    analyze_chat(...)

services/ai/gigachat.py — реализация.

ВАЖНО:

    get_ai_provider() — async! Всегда provider = await get_ai_provider().

    Модели из env: GIGACHAT_MODEL (текст), GIGACHAT_VISION_MODEL (Vision).

    Vision-модель обязательна для анализа фото (GigaChat-2-Max).

    _extract_json — устойчив к битому JSON.

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

    10+ тем по ключевым словам архетипа

    Характеристики: PNG-иконки (Twemoji) + название + прогресс-бар + число

    Опасность: цветная плашка

    Цитата: плашка с акцентной полосой

    Достижения: PNG-иконки (до 3)

    Футер: «ВАЙБМИ · узнай свой вайб» + @bot_username

    Без эмодзи в коде — только PNG-иконки

Иконки / Шрифты

    services/cards/icons.py — stat_icon(key, size), achievement_icon(code, size)

    services/cards/icons_data.py — base64 PNG

    services/cards/fonts_embedded.py — base64 TTF

    tools/build_embedded_icons.py, tools/build_embedded_fonts.py

Анализ карточки (bot/handlers/analysis.py)

    Скачивание фото.

    Rate limit (check_and_increment(telegram_id, user.id)).

    A/B тест промта (photo_v1 / photo_v2).

    analyze_photo() → JSON + сезонный контекст.

    Сохранение в photo_analyses + profiles. Модель = GIGACHAT_VISION_MODEL.

    Достижения.

    generate_card() → PNG.

    Персональный призыв (pick_share_call).

    Caption + Reply-кнопки share_kb.

    Хук maybe_send_ad.

    flush_notifications.

5.1. ВОВЛЕЧЕНИЕ (engagement)
Сервисы

    points.py — очки + 20 уровней.

        add_points(user_id, action, multiplier) — начисление по POINTS[action]

        add_custom_points(user_id, amount) — произвольное количество (используется в квестах, челленджах, рефералке)

        level_for_points, title_for_level, points_to_next_level

        get_or_create_engagement(session, user_id)

    streaks.py — серии дней.

        update_streak(user_id) — вызывается при /start. Очки начисляются вне сессии.

        Milestones: 3, 7, 14, 30, 100.

        При milestone: unlock_achievement + add_streak_notification + check_streak_reward.

    archetypes.py — коллекция.

        add_archetype(user_id, archetype) → is_new

        MAX_ARCHETYPES = 20

    challenges.py — дневной челлендж.

        CHALLENGE_POOL — 7 типов

        get_or_create_today_challenge()

        increment_progress(user_id, task_type, amount) — награда через add_custom_points(challenge.reward_points)

    weekly_challenges.py — недельный челлендж.

        WEEKLY_POOL — 5 типов

        get_or_create_weekly_challenge() — понедельник 00:00 UTC

        increment_weekly_progress(...) — награда через add_custom_points(wc.reward_points)

    quests.py — цепочки заданий.

        QUESTS_SEED — 2 квеста: explorer, communicator

        seed_quests() — идемпотентно

        advance_quest(user_id, task_type, amount) — двигает один квест (первый по sort_order), накапливает step_progress, награда = step.reward_points через add_custom_points

        get_active_quests(user_id) — список для UI

    rewards.py — универсальные разовые награды.

        claim_reward(user_id, reward_code, payload) → bool

        grant_pro_days(user_id, days, reason) → bool

        grant_whitelist_days(user_id, days, reason) → bool

    referral_reward.py — 10 активных рефералов → 7 дней PRO.

        Порядок: user → claim_reward → grant_pro_days

    streak_rewards.py — PRO за стрики.

        7 → 1 день, 30 → 3 дня, 100 → 7 дней.

        Порядок: user → grant_pro_days → claim_reward

    points_rewards.py — PRO за очки.

        1500 → 3 дня, 15000 → 7 дней.

        Порядок: user → grant_pro_days → claim_reward

    referrals.py — реферальная логика.

        on_referred_user_analyzed(referred_user_id) — вызывается после первого анализа друга

        Защита от повторов через ReferralReward

        Окно 30 дней

        Награда пригласившему: add_custom_points(referrer, REFERRAL_POINTS=50)

        Проверка check_referral_reward

    notifications.py — очередь уведомлений (in-memory).

        add_achievement_notification, add_level_up_notification, add_streak_notification, add_custom_notification

        flush_notifications(bot, telegram_id) — отправка и очистка

    service.py — единый API.

        on_user_visit, on_photo_analyzed, on_test_completed, on_message_sent, on_share, on_compare, on_search

Интеграция в хендлеры

    start.py → on_user_visit

    analysis.py → on_photo_analyzed, on_referred_user_analyzed, flush_notifications

    tests.py → on_test_completed

    messaging.py, chats.py → on_message_sent

    compare.py → on_compare

    matching.py → on_search

    analysis.py (cb_do_share) → on_share

Очки (POINTS)
text

first_login: 10, daily_login: 5, streak_bonus: ×N,
photo_analysis: 15, new_archetype: 30,
test_complete: 20, first_message: 10,
share: 5, invite_friend: 50,
challenge_complete: 50

Уровни (LEVELS) — 20 уровней

От «Новичок» (0) до «ЛЕГЕНДА ВАЙБМИ» (55000).

Достижения за уровни: level_5, level_10, level_15, level_20.
Достижения за вовлечение

    streak_3, streak_7, streak_14, streak_30, streak_100

    level_5, level_10, level_15, level_20

UI кнопки в главном меню

    🎯 Челлендж дня

    🗓 Челлендж недели

    🧭 Квесты

    📊 Моя статистика

    🏆 Топы

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
message_sent, joke_sent, inbox_viewed,

# Вовлечение (5.1)
challenge_viewed, challenge_completed, tops_sent,

# Награды (6.2.2 + 6.3)
reward_claimed, referral_reward_10, streak_reward, points_reward,

# Недельные челленджи и квесты (7)
weekly_challenge_viewed, weekly_challenge_completed,
quest_started, quest_step_completed, quest_completed,
season_active

ВАЖНО: при добавлении новых событий — добавлять их в EVENT_NAMES.
7. FEATURE FLAGS

Хранятся в БД. Управляются через /admin → ⚙️ Feature flags.
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

API: await is_enabled(key, default); await set_flag(key, value); await get_all_flags().
8. ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ

Hard gate через MandatorySubscriptionMiddleware (на dp.message и dp.callback_query).

    /start, /help, /cancel, sub_check_* — пропускаются.

    Админ / whitelist / PRO — пропускаются.

    Middleware на message и callback_query, НЕ на update.

Кампании — через /admin → 📣 Подписки → ➕ Новая кампания (FSM-мастер).
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

    check_and_increment(telegram_id, user_id) — telegram_id первый, user_id второй!

Автопродление — отложено.
10. ЧАТЫ

Модели: Chat (user1_id < user2_id), Message, ChatReport.

AI-помощник (PRO): chat_ai_reply_<id>, chat_ai_analyze_<id>.
11. РАССЫЛКА

FSM-мастер admin/broadcast.py. Прогресс каждые 100 сообщений. Пауза 0.05 сек.
12. ВАЖНЫЕ СОГЛАШЕНИЯ
Код

    ВСЕГДА Optional[X] вместо X | None (BotHost — 3.11, локально — 3.9).

    datetime.now(timezone.utc) вместо datetime.utcnow().

    await get_ai_provider() — функция async!

    _safe_answer(callback) вместо await callback.answer() в админке.

    В catch-all хендлерах — динамический фильтр по FSM-состоянию.

    logger.exception(...) для отлова ошибок с трейсбеком.

    Detached-объекты: считывать нужные поля до session.commit(), если потом нужен доступ после закрытия async with.

    Вложенные сессии: не вызывать add_points/add_custom_points внутри async with async_session() — они открывают свою сессию. Выносить за блок.

    Награды: начислять через add_custom_points(user_id, reward_points), если значение переменное. add_points(action, multiplier) — только для фиксированных POINTS[action].

    Reward-файлы: порядок user → grant_pro_days → claim_reward (снижает риск потери награды при падении grant).

Что НЕ работает (важно помнить)

    Эмодзи в Pillow — DejaVu Sans не рендерит. Только PNG-иконки.

    data/ на BotHost — папка пустая, если файлы не в Git. Решение: base64.

    qrcode[pil] в requirements — может ломать сборку BotHost. Использовать qrcode==8.0 или убрать.

    .gitignore — блокирует data/ целиком. Разрешить !data/fonts/, !data/icons/, !data/jokes.json.

Middleware

    dp.update.middleware(...) — event = Update.

    dp.message.middleware(...) и dp.callback_query.middleware(...) — event = Message/CallbackQuery.

13. КОМАНДЫ
Локальная разработка
powershell

cd C:\Users\Alexandr\Desktop\BOTS\gamebot
.\venv\Scripts\Activate.ps1

# Запуск
python main.py

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

Отладочные команды (только для админа)

    /grant_pro <tg_id> <days> [reason] — выдать PRO вручную

    /fake_refs <count> — создать N фиктивных рефералов

⚠️ Удалить после тестирования.
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
step_progress отсутствует после деплоя	ALTER TABLE user_quest_progress ADD COLUMN IF NOT EXISTS step_progress INTEGER NOT NULL DEFAULT 0;
Квесты: шаг закрывался за 1 действие	Добавить step_progress, накапливать в advance_quest
Награда за челлендж/квест/реферал не соответствовала reward_points	Использовать add_custom_points(user_id, amount) вместо add_points(..., multiplier=N)
DetachedInstanceError в reward-файлах	Считывать значения до session.commit()
Вложенные сессии при add_points внутри async with	Выносить add_points за блок сессии
Сезонный блок терялся, если prompt_override=None	final_prompt = (prompt_override or "") + season_block — добавлять всегда
X | None ломает Python 3.9 локально	Использовать Optional[X] — но ловим только по факту
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

    ✅ Обязательные подписки

    ✅ Админка (12+ разделов)

    ✅ Рассылка

    ✅ Feature flags

    ✅ Rate limit 1/день

    ✅ Чистка БД

    ✅ Неоновая карточка с 10+ темами

    ✅ PNG-иконки (base64)

    ✅ Вовлечение 5.1: стрики, очки, уровни, коллекция, челлендж дня, топы, статистика

    ✅ Этап 6.2.2: реферальная награда 10 друзей → 7 дней PRO

    ✅ Этап 6.3: PRO за стрики (7/30/100) и очки (1500/15000)

    ✅ Этап 7: сезоны, недельные челленджи, квесты

В работе / отложено

    🟡 Автопродление PRO — отложено

    🟡 Монетизация пакетами / подарками — отложено

    🟡 Команды (кланы), взаимные лайки — не начато

    🟡 A/B тесты промтов — базовая инфраструктура есть

    🟡 Аналитика воронки и метрик — базовая есть

16. ПРАВКИ ЭТАПА 6.2.2 + 6.3 + 7 (сделано)
Новые файлы

    services/seasons.py — определение сезона

    services/engagement/rewards.py — универсальные награды

    services/engagement/referral_reward.py

    services/engagement/streak_rewards.py

    services/engagement/points_rewards.py

    services/engagement/weekly_challenges.py

    services/engagement/quests.py

Изменённые файлы (ключевые правки)

database/models.py

    Добавлены: RewardClaim, WeeklyChallenge, UserWeeklyChallenge, Quest, QuestStep, UserQuestProgress

    В UserQuestProgress добавлено поле step_progress (Integer, default 0)

database/init_db.py

    Добавлена миграция: ALTER TABLE user_quest_progress ADD COLUMN IF NOT EXISTS step_progress INTEGER NOT NULL DEFAULT 0;

    Индексы для новых таблиц

main.py

    Добавлен вызов seed_quests() после seed_achievements()

    _log_boot использует datetime.now(timezone.utc)

services/analytics/tracker.py

    Добавлены события: reward_claimed, referral_reward_10, streak_reward, points_reward, weekly_challenge_viewed, weekly_challenge_completed, quest_started, quest_step_completed, quest_completed, season_active

services/engagement/points.py

    Добавлена add_custom_points(user_id, amount) — произвольное начисление

    Вынес _check_points_rewards в отдельную функцию

services/engagement/quests.py

    Правильная логика advance_quest:

        step_progress накапливается

        Двигается только один квест (первый по sort_order)

        Награда = step.reward_points через add_custom_points

        Повреждённый квест помечается completed, не падает

services/engagement/service.py

    Добавлен on_search в __all__

    Явные amount=1 в вызовах advance_quest

services/analysis/photo_analysis.py

    Баг фикс: final_prompt = (prompt_override or "") + season_block — сезон добавляется всегда, даже если prompt_override=None

bot/handlers/analysis.py

    model = getattr(config, "GIGACHAT_VISION_MODEL", config.GIGACHAT_MODEL) — правильная модель в БД

    check_and_increment(telegram_id, user.id) — правильный порядок (не трогать!)

bot/handlers/engagement.py

    _get_user_by_tg возвращает Optional[User] (было User | None)

    track("challenge_viewed", telegram_id=message.from_user.id) (было message.chat.id)

bot/handlers/matching.py

    Добавлен вызов on_search(me.id) в mode_selected — для квестового шага search

services/engagement/referral_reward.py

    Убраны мёртвые импорты (UserEngagement, add_achievement_notification)

    Порядок: user → claim_reward → grant_pro_days

    Глобальный импорт add_custom_notification

services/engagement/points_rewards.py

    Порядок: user → grant_pro_days → claim_reward

    Warning на гонку

services/engagement/streak_rewards.py

    Порядок: user → grant_pro_days → claim_reward

    Warning на гонку

services/engagement/referrals.py

    referrer_user_id и new_referral_count считываются до commit()

    Убрана мёртвая переменная referrer_telegram_id

    add_custom_points(referrer_user_id, REFERRAL_POINTS) вместо add_points(..., "invite_friend")

services/engagement/streaks.py

    add_points для first_login вынесен за async with async_session() — убраны вложенные сессии

services/engagement/challenges.py

    add_custom_points(user_id, challenge.reward_points) вместо фиксированных 50

    Убран мёртвый импорт List

    progress/status считываются внутри async with

services/engagement/weekly_challenges.py

    add_custom_points(user_id, wc.reward_points) вместо фиксированных 200

    _week_start — обычная (не async) функция

    progress/status считываются внутри async with

services/engagement/notifications.py

    Убран мёртвый from typing import Optional

17. КАК ВОССТАНОВИТЬ КОНТЕКСТ В НОВОМ ЧАТЕ

Первое сообщение в новом чате:

    Продолжаем работу над проектом Вайбми (Telegram AI-бот, aiogram 3.15).
    Контекст проекта ниже:

    [вставляешь содержимое PROJECT_CONTEXT.md]

    Продолжаем с [указать этап/задачу].

18. КОНТАКТЫ И ССЫЛКИ

    GitHub: https://github.com/flaimes313-source/gamesbotai

    Бот: @gamesaiii_bot

    BotHost: https://bothost.ru

    PostgreSQL: node1.pghost.ru:16127

Секреты: только в .env (не в Git) и в панели BotHost → Environment Variables.

Версия контекста: 1.1
Последнее обновление: 2026-09-21
text


---

## Что изменилось в контексте

**Ключевые дополнения:**

1. **Раздел 2 (архитектура)** — добавил `bot/handlers/engagement.py`, `bot/handlers/info.py`, `services/seasons.py`, всю папку `services/engagement/` с новыми файлами, `bot/keyboards/engagement.py`, `bot/keyboards/info.py`.
2. **Порядок роутеров** — актуализировал (включая `engagement` и `info`).
3. **Раздел 3 (БД)** — добавил все новые таблицы: `referral_rewards`, `reward_claims`, `weekly_challenges`, `user_weekly_challenges`, `quests`, `quest_steps`, `user_quest_progress` (с `step_progress`).
4. **Раздел 5 (карточка)** — уточнил модель (`GIGACHAT_VISION_MODEL`).
5. **Раздел 5.1 (вовлечение)** — расписал по каждому файлу, что и как работает, включая `add_custom_points`.
6. **Раздел 6 (события)** — добавил все новые `EVENT_NAMES`.
7. **Раздел 9 (PRO)** — уточнил сигнатуру `check_and_increment`.
8. **Раздел 12 (соглашения)** — добавил пункты про detached-объекты, вложенные сессии, `add_custom_points`, порядок grant/claim в reward-файлах.
9. **Раздел 13 (команды)** — добавил отладочные `/grant_pro`, `/fake_refs`.
10. **Раздел 14 (история проблем)** — добавил 8 новых кейсов из наших правок.
11. **Раздел 15 (статус)** — отметил этапы 6.2.2, 6.3, 7 как завершённые.
12. **Новый раздел 16** — «Правки этапа 6.2.2 + 6.3 + 7» — перечислены все изменённые файлы и что именно в них поменялось.

**Что НЕ трогал:** разделы 1, 4, 7, 8, 10, 11, 17, 18 — оставил как было (они не касаются этапа 6.2.2 + 6.3 + 7).

---

## 17. ШАГ 1.2 — РЕДКИЕ / ЛЕГЕНДАРНЫЕ АРХЕТИПЫ (2026-09-22)

### Кратко

AI генерит обычный архетип, а бэк с шансом **3%** подменяет его
на один из **8 легендарных**. Легендарка = золотая рамка на карточке,
особый caption, +300 очков, 2 достижения.

### Список легендарных (8 штук)

```
1. ХРАНИТЕЛЬ ТИШИНЫ
2. НЕКРОНОМИКОН В КАРМАНЕ
3. ПОСЛЕДНИЙ ИЗ ЛЕГЕНД
4. ТОТ КОГО НЕ ДОЛЖНО БЫЛО БЫТЬ
5. ИМПЕРАТОР БЕЗ ТРОНА
6. ГЛАВНЫЙ ГЕРОЙ ЧУЖОГО СНА
7. ФЕНИКС ИЗ ПЕПЛА
8. АРХИТЕКТОР РЕАЛЬНОСТИ
```

Все — капсом, длинные, не пересекаются с ключевыми словами
тем из `services/cards/themes.py`.

### Защита от инфляции

- Не чаще **одной легендарки в 7 дней** (cooldown).
- Не раньше **3-го анализа** у юзера.
- Если недавно была — шанс понижается до **1%**.

### Новые файлы

| Файл | Назначение |
|---|---|
| `services/analysis/rarity.py` | Список легендарных, шансы, cooldown, `maybe_make_legendary()`, `mark_legendary_received()`, `is_legendary()`, `pick_random_legendary()` |
| `prompts/photo_analysis_v3.py` | Промт v3: эпичные названия + явный запрет AI генерить легендарки |

### Изменённые файлы

| Файл | Что сделано |
|---|---|
| `services/cards/themes.py` | Тема `legendary` (золото+янтарь). `theme_for()` / `theme_name_for()` — приоритет `is_legendary()` над keyword-поиском. `tag_for_archetype()` для легендарки → `#легендарный_вайб` |
| `services/cards/generator.py` | Параметр `is_legendary: bool=False`. Золотая двойная рамка (`_draw_legendary_border`), значок «ЛЕГЕНДАРНЫЙ» со звёздочками (`_draw_legendary_badge`), заголовок «ЛЕГЕНДАРНЫЙ АРХЕТИП», усиленные свечения, сдвиг блока характеристик на 20px вниз |
| `database/models.py` | `UserEngagement.last_legendary_at` (DateTime, nullable) |
| `database/init_db.py` | Миграция `ALTER TABLE user_engagement ADD COLUMN IF NOT EXISTS last_legendary_at TIMESTAMPTZ;` |
| `database/seed_achievements.py` | Достижения `first_legendary` (✨) и `five_legendaries` (🌟) |
| `services/analytics/tracker.py` | В EVENT_NAMES: `legendary_archetype`, `legendary_achievement` |
| `bot/handlers/analysis.py` | `maybe_make_legendary()` после AI, подмена `analysis["archetype"]`, `_handle_legendary_achievements()`, `_count_unique_legendaries()`, `mark_legendary_received()`, `add_custom_points(300)`, особый caption, `generate_card(..., is_legendary=...)` |
| `services/experiments.py` | `EXPERIMENTS["photo_prompt"] = ["photo_v1", "photo_v2", "photo_v3"]`. Fallback на v3 для устаревших вариантов |

### Поток в `analysis.py`

```
AI → analysis["archetype"]
  ↓
maybe_make_legendary(user.id, archetype) → (final_archetype, is_legendary)
  ↓
если легендарка: analysis["archetype"] = final_archetype
  ↓
сохраняем Profile (в БД уже легендарное имя)
  ↓
on_photo_analyzed → обычные очки (15 + 30 если новый)
  ↓
если легендарка:
    track("legendary_archetype")
    add_custom_points(user.id, 300)
    mark_legendary_received(user.id)         # cooldown
    _handle_legendary_achievements(...)      # first / five
  ↓
build_result_text(is_legendary) — плашка в caption
  ↓
generate_card(..., is_legendary=True) — золотая рамка
```

### Константы (`services/analysis/rarity.py`)

| Константа | Значение | Смысл |
|---|---|---|
| `LEGENDARY_ARCHETYPES` | 8 имён | Список легендарных |
| `LEGENDARY_CHANCE` | 0.03 | Базовый шанс 3% |
| `LEGENDARY_CHANCE_REDUCED` | 0.01 | Пониженный 1% (в кулдауне) |
| `LEGENDARY_COOLDOWN_DAYS` | 7 | Дней между легендарками |
| `LEGENDARY_MIN_ANALYSES` | 3 | Минимум анализов до первой |
| `LEGENDARY_POINTS` | 300 | Очков за легендарку |

### Достижения

| Код | Название | Условие |
|---|---|---|
| `first_legendary` | «Первый легендарный» | Первая легендарка |
| `five_legendaries` | «Коллекционер легенд» | 5 **разных** легендарных |

### A/B/C-тест промтов

- `photo_v1` — базовый
- `photo_v2` — расширенный (дерзкий стиль)
- `photo_v3` — эпичные названия + запрет легендарок

Назначение стабильно на `telegram_id` (md5). Старые юзеры НЕ
переезжают при изменении списка. Отчёт `experiments_report.py`
покажет 3 строки автоматически.

### Как тестировать легендарку

В `services/analysis/rarity.py` временно:

```python
LEGENDARY_CHANCE = 1.0
LEGENDARY_MIN_ANALYSES = 0
LEGENDARY_COOLDOWN_DAYS = 0
```

Первая же легендарка выпадет. **Откатить после теста!**

### Порядок в reward-логике (важно)

Для легендарки:
1. `track("legendary_archetype")`
2. `add_custom_points(user.id, 300)`
3. `mark_legendary_received(user.id)` — cooldown
4. `_handle_legendary_achievements(...)` — достижения

Если упадёт шаг 2 — cooldown не обновится, легендарка может выпасть снова.
Если упадёт шаг 3 — очки начислены, но cooldown не сдвинут.
Это **осознанный компромисс**: важнее наградить игрока, чем
защититься от повторной легендарки.

### История проблем этого шага

| Проблема | Решение |
|---|---|
| Легендарка подменялась после сохранения Profile | `maybe_make_legendary` вызывается ДО `build_profile` |
| Тема `legendary` не подхватывалась, если в имени есть ключевое слово | Приоритет `is_legendary()` в `theme_for()` перед keyword-поиском |
| `last_legendary_at` отсутствовал в БД | Миграция в `init_db.py` + `getattr(eng, "last_legendary_at", None)` в `rarity.py` |
| AI сам генерил «легендарные» имена | Явный запрет в промте v3 |
| Старые юзеры застревали на удалённом варианте A/B | Fallback на v3 в `pick_prompt_by_variant()` |
| Двойная сессия при cooldown | `mark_legendary_received()` — отдельная функция, вызывается после основной транзакции |

---

## 18. ШАГ 1.3 — ВАЙБ-ОТЧЁТ (AI-ПСИХОЛОГ) (2026-09-22)

### Кратко

Две связанные фичи:
1. **«Мой вайб-отчёт»** — по запросу, кнопка в профиле. Доступна при ≥ 3 анализов.
2. **«Твой вайб-месяц»** — авто-рассылка по воскресеньям 19:00 по TZ юзера,
   только для активных (≥ 3 активных дней за неделю). С картинкой-сводкой.

### Новые файлы

| Файл | Назначение |
|---|---|
| `prompts/vibe_report.py` | 2 промта: `VIBE_REPORT_PROMPT` (портрет) и `VIBE_WEEKLY_PROMPT` (сводка) |
| `services/analysis/vibe_report.py` | `build_vibe_report(user_id, weekly)` — сбор данных + перцентили + AI |
| `bot/handlers/vibe_report.py` | Хендлер кнопки «🧠 Мой вайб-отчёт» |
| `services/cards/vibe_summary.py` | Карточка «Твой вайб-месяц» (PNG, 900×1200) |
| `services/notifications/vibe_weekly.py` | Планировщик: `weekly_vibe_loop(bot)` |

### Изменённые файлы

| Файл | Что сделано |
|---|---|
| `services/ai/base.py` | Абстрактный метод `generate_vibe_report(profile_data, weekly=False)` |
| `services/ai/gigachat.py` | Реализация + утилита `_parse_vibe_report_text()` |
| `bot/keyboards/profile.py` | Кнопка «🧠 Мой вайб-отчёт» (callback `vibe_report`) |
| `bot/handlers/__init__.py` | Регистрация `vibe_report.router` после `profile.router` |
| `services/analytics/tracker.py` | События `vibe_report_viewed`, `vibe_weekly_sent` |
| `main.py` | Запуск `weekly_vibe_loop(bot)` после `tops_loop` |

### Как работает отчёт по запросу

```
👤 Мой профиль → 🧠 Мой вайб-отчёт
  ↓
build_vibe_report(user_id, weekly=False)
  ├── проверка: >= 3 анализов? нет → заглушка «Сделай ещё N»
  ├── сбор: 10 последних профилей, статистика, коллекция
  ├── перцентили (charisma, chaos, humor, points) — по всей БД
  ├── рекомендации: непройденный тест / охота за легендаркой / друг
  └── AI → {text, summary, recommendation}
  ↓
Отправка: header + text + «💡 Совет: …» + inline-кнопки
  (🔄 Обновить / 📤 Поделиться / ⬅️ В профиль)
```

### Как работает недельная рассылка

```
weekly_vibe_loop(bot) просыпается каждые 15 минут
  ↓
для юзеров с локальным «воскресенье 19:00»:
  ├── уже слали сегодня? → skip
  ├── active_days < 3 за 7 дней? → skip (skipped_inactive)
  └── да:
        build_vibe_report(user_id, weekly=True)
        generate_vibe_summary_card(summary, stats, archetype, bot_username, period_label)
        send_photo(card, caption)
        track("vibe_weekly_sent")
```

### Перцентили

Считаются на бэке: `PERCENT_RANK` через `COUNT(*) WHERE column < my_value / total * 100`.
Порог `total >= 20` — если база меньше, перцентиль = `None` (не позорим «топ-100%»).
Передаётся AI как факт: `«харизма — топ-20%»`.

### Рекомендации (3 типа)

1. **Непройденный тест** — `Test.is_active`, `is_premium=False`, не в `user_tests`.
2. **Охота за легендаркой** — если `legendary_count == 0` и `total_analyses >= 3`.
3. **Приглашение друга** — если `total_referrals == 0`.

Максимум 3. Бэк решает, AI вплетает в текст.

### Формат ответа AI

GigaChat возвращает **ТЕКСТ** (не JSON), с маркерами:

```
[SUMMARY]
одна короткая фраза для картинки

[REPORT]
основной текст отчёта (HTML)

[RECOMMENDATION]
одна рекомендация
```

Парсер `_parse_vibe_report_text()` в `gigachat.py` достаёт блоки регуляркой.
Fallback: если маркеров нет — весь текст в `text`, первое предложение в `summary`.

### Константы

| Где | Что | Значение |
|---|---|---|
| `services/analysis/vibe_report.py` | `MIN_ANALYSES_FOR_REPORT` | 3 |
| `services/analysis/vibe_report.py` | `PROFILES_LIMIT` | 10 |
| `services/notifications/vibe_weekly.py` | `WEEKLY_TARGET_HOUR` | 19 |
| `services/notifications/vibe_weekly.py` | `WEEKLY_TARGET_WEEKDAY` | 6 (вс) |
| `services/notifications/vibe_weekly.py` | `MIN_ACTIVE_DAYS_FOR_WEEKLY` | 3 |
| `services/notifications/vibe_weekly.py` | `CHECK_INTERVAL_SECONDS` | 900 (15 мин) |

### Что НЕ хранится

- Отчёты **не сохраняются** в БД (без кэша).
- Генерация **всегда свежая** при каждом запросе.
- Единственное, что пишется — событие в `events` (для аналитики и anti-dup).

### События

| Событие | Когда | Payload |
|---|---|---|
| `vibe_report_viewed` | Юзер открыл/обновил отчёт в профиле | `{weekly, text_len, has_recommendation}` |
| `vibe_weekly_sent` | Недельная сводка отправлена | `{active_days, had_card}` |

### Карточка «Твой вайб-месяц»

- Размер **900×1200** (как основная).
- Тема — по последнему архетипу юзера (если легендарка → золотая тема).
- Заголовок «Т В О Й   В А Й Б - М Е С Я Ц».
- Плашка с summary от AI (крупным шрифтом).
- **6 плиток 2×3** с цифрами:
  📸 Анализов · ⭐ Очков · 🔥 Стрик · 📅 Активных дней · 🎨 Архетипов · ✨ Легендарных
- Иконки — PNG-base64 из `stat_icon()`. Фолбэк — ромб.
- Футер: «ВАЙБМИ · твой вайб-месяц» + @bot_username.

### Защита от дублей

- `_already_sent_today(telegram_id)` — проверяет `events.vibe_weekly_sent` за сегодня.
- Если бот перезапустился в 19:05, повторная отправка не произойдёт.

### Как тестировать

**Отчёт по запросу:**
1. Сделай ≥ 3 анализа.
2. `👤 Мой профиль → 🧠 Мой вайб-отчёт`.
3. Проверь: заголовок «МОЙ ВАЙБ-ОТЧЁТ», текст от AI, кнопки.

**Недельная рассылка:**
- Планировщик срабатывает только **в воскресенье 19:00 по TZ**.
- Для теста — временно поменяй `WEEKLY_TARGET_HOUR` / `WEEKLY_TARGET_WEEKDAY`
  на текущие значения, дождись итерации (до 15 мин), откати.
- Проверь: `active_days >= 3` (иначе `MIN_ACTIVE_DAYS_FOR_WEEKLY = 0` временно).

### History проблем

| Проблема | Решение |
|---|---|
| GigaChat вернул JSON вместо текста | Промт явно требует `[SUMMARY]/[REPORT]/[RECOMMENDATION]`, парсер устойчив к отсутствию |
| `KeyError` в `format()` из-за weekly-переменных в портретном промте | В `VIBE_REPORT_PROMPT` weekly-переменные в комментарии-заглушке |
| AI разошёлся — текст > 4096 | Обрезка до 3800 символов в `vibe_report.py` (handler) |
| Перцентиль «топ-100%» при малой базе | Порог `total >= 20` → `None` |
| Юзер неактивен — спамить некрасиво | Фильтр `active_days >= 3` |
| Дубль при перезапуске в 19:05 | `_already_sent_today` через events |
| AI упал — юзер не должен видеть ошибку | Fallback-текст + `available=True` |
| DetachedInstanceError при сборе профилей | Всё собирается внутри одной сессии, AI вызывается после закрытия |

### Точка отката

Если нужно выключить фичу целиком:
- **По запросу:** закомментировать кнопку в `bot/keyboards/profile.py`.
- **Недельная:** `is_enabled("weekly_vibe_enabled", default=True)` в `vibe_weekly.py` → поставить `default=False`.

---

## 19. ЭТАП 1 + ЭТАП 2 — ВОВЛЕЧЕНИЕ И УВЕДОМЛЕНИЯ (2026-09-24)

### Кратко

- **Этап 1 — Инфраструктура уведомлений.** Единый сервис `hub.py`,
  настройки юзера, тихие часы, дневной лимит, очередь.
- **Этап 2 — Карма дня.** Случайный бонус очков при первом заходе.

### Этап 1: Инфраструктура уведомлений

#### Зачем

Раньше у каждого типа уведомлений был свой `*_loop`
(`daily_sender`, `chat_reminder`, `premium_reminder`, `tops_sender`,
`vibe_weekly`). Логика тихих часов и лимитов дублировалась. С ростом
фич это превращается в кашу — поэтому построили центральный хаб.

#### Новые файлы

| Файл | Назначение |
|---|---|
| `services/notifications/hub.py` | Единый сервис: очередь, проверки, воркер |
| `bot/handlers/settings_notifications.py` | UI настроек (7 тумблеров) |

#### Новые таблицы

| Таблица | Что |
|---|---|
| `user_notification_settings` | Тумблеры категорий (7 штук, по умолчанию все True) |
| `profile_views` | Лог просмотров профилей (viewer_id, viewed_id, source) |
| `horoscopes` | Кэш гороскопов (user_id, date, text) UNIQUE(user_id, date) |

#### Изменённые файлы

| Файл | Что |
|---|---|
| `database/models.py` | 3 новые таблицы |
| `database/init_db.py` | Миграции |
| `bot/keyboards/main.py` | Кнопка «🔔 Уведомления» в `settings_kb()` |
| `bot/handlers/__init__.py` | Регистрация `settings_notifications.router` |
| `services/analytics/tracker.py` | События `notif_menu_viewed`, `notif_toggle`, `horoscope_sent`, `secret_feature_sent`, `profile_views_sent`, `premium_reminder_sent` |
| `main.py` | Запуск `notification_worker_loop` |

#### Как работает hub

```
schedule_notification(user_id, kind, priority, payload, tz_name)
  ↓
can_send_now():
  1. feature flag (KIND_TO_FLAG)
  2. настройки юзера (KIND_TO_SETTING)
  3. тихие часы (23:00–08:00 TZ)
  4. дневной лимит (MAX_DAILY_PROACTIVE=2)
  5. дубли (уже слали сегодня?)
  ↓
очередь (in-memory, {user_id: [items]})
  ↓
notification_worker_loop (раз в 15 мин)
  ↓
_send_notification → track(event_name)
```

#### Константы

| Константа | Значение |
|---|---|
| `MAX_DAILY_PROACTIVE` | 2 |
| `PRIORITY_DROP_THRESHOLD` | 4 |
| `WORKER_INTERVAL_SECONDS` | 900 (15 мин) |

**Логика приоритета:** если дневной лимит набран, отбрасываются только
низкоприоритетные (priority >= 4). Высокоприоритетные (1-3) — проходят.

#### Маппинги (kind → ...)

| kind | feature flag | setting | event |
|---|---|---|---|
| `daily_result` | `daily_content_enabled` | `daily_result_enabled` | `daily_sent` |
| `horoscope` | `horoscope_enabled` | `horoscope_enabled` | `horoscope_sent` |
| `secret_feature` | `secret_feature_enabled` | `secret_feature_enabled` | `secret_feature_sent` |
| `profile_views` | `profile_views_enabled` | `profile_views_enabled` | `profile_views_sent` |
| `weekly_vibe` | `weekly_vibe_enabled` | `weekly_vibe_enabled` | `vibe_weekly_sent` |
| `tops` | `tops_enabled` | `tops_enabled` | `tops_sent` |
| `premium_reminder` | `premium_reminder_enabled` | `premium_reminder_enabled` | `premium_reminder_sent` |

**Примечание:** feature flags `horoscope_enabled`, `secret_feature_enabled`,
`profile_views_enabled`, `weekly_vibe_enabled`, `tops_enabled`,
`premium_reminder_enabled` **не заведены в `ensure_flags_exist`** — они
используются через дефолт `True` при отсутствии в БД. Если захочешь
глобально выключать — добавь в `DEFAULTS` в `feature_flags.py`.

#### UI настроек

`⚙️ Настройки` → `🔔 Уведомления` → 7 тумблеров (✅/❌).
Callback: `notif_menu`, `notif_toggle_<name>`.

### Этап 2: Карма дня

#### Что

При **первом заходе за день** юзер получает случайный бонус очков.

#### Шансы

| Шанс | Очки |
|---|---|
| 70% | +10 |
| 20% | +30 |
| 8% | +50 |
| 2% | +100 (джекпот) |

Максимум за раз: **100 очков**. Средний выхлоп: ~18 очков.

#### Как работает

```
/start
  ↓
on_user_visit (стрик)
  ↓
roll_karma_for_today(user_id)
  ├── уже получал сегодня? → None (тихо)
  ├── roll: random.random()
  ├── RewardClaim(reward_code="karma_YYYY-MM-DD")
  └── add_custom_points(user_id, points)
  ↓
format_karma_message(karma) → message.answer()
```

#### Новые файлы

| Файл | Назначение |
|---|---|
| `services/engagement/karma.py` | `roll_karma_for_today`, `format_karma_message` |

#### Изменённые файлы

| Файл | Что |
|---|---|
| `bot/handlers/start.py` | Вызов кармы после главного меню |
| `services/analytics/tracker.py` | Событие `karma_rolled` |

#### Защита от дублей

- **`RewardClaim`** с `reward_code="karma_YYYY-MM-DD"` (UNIQUE user_id + reward_code).
- При гонке (два `/start` одновременно) — один поймает `IntegrityError`,
  тихо выйдет, очки не удвоятся.

#### Если `add_custom_points` падает

`RewardClaim` уже записан → награда «сгорает». Это осознанный компромисс:
лучше так, чем дать юзеру бесконечные попытки.

### События Этапа 1+2

| Событие | Когда | Payload |
|---|---|---|
| `notif_menu_viewed` | Открыл настройки уведомлений | — |
| `notif_toggle` | Переключил тумблер | `{field, value}` |
| `karma_rolled` | Выпала карма дня | `{points}` |
| `horoscope_sent` | Отправлен гороскоп (пока не летит) | `{kind}` |
| `secret_feature_sent` | Отправлена секретная фича (пока не летит) | `{kind}` |
| `profile_views_sent` | Отправлено уведомление о просмотрах (пока не летит) | `{kind}` |
| `premium_reminder_sent` | Отправлено PRO-напоминание | `{kind}` |

### Порядок воркеров в main.py

```
daily_loop
chat_reminder_loop
db_cleanup_loop
premium_reminder_loop
tops_loop
weekly_vibe_loop
notification_worker_loop  ← новый
start_polling
```

### Как тестировать

**Этап 1 — настройки уведомлений:**
1. `/start` → `⚙️ Настройки` → `🔔 Уведомления`.
2. 7 тумблеров, все ✅.
3. Нажми — переключится на ❌. Нажми ещё раз — обратно.
4. В БД: `SELECT * FROM user_notification_settings WHERE user_id=...`.

**Этап 2 — карма:**
1. `/start`.
2. После главного меню должно прийти **«🎁 КАРМА ДНЯ»** с очками.
3. Повторный `/start` в тот же день — кармы **нет**.
4. В БД: `SELECT * FROM reward_claims WHERE reward_code LIKE 'karma_%'`.
5. В БД: `SELECT * FROM events WHERE name='karma_rolled' ORDER BY id DESC LIMIT 5`.

### History проблем

| Проблема | Решение |
|---|---|
| Логика тихих часов дублировалась в 5 файлах | Централизовали в `hub.py` |
| Юзер не мог отключить уведомления | Таблица `user_notification_settings` + UI |
| Карма могла начислиться дважды | `RewardClaim` с UNIQUE + защита от `IntegrityError` |
| `add_custom_points` внутри `async with` — вложенная сессия | Вынес за пределы сессии (`roll_karma_for_today`) |
| `notif_toggle_*` callback не ловился | Регистрация `settings_notifications.router` в `__init__.py` |

### Точка отката

- **Отключить уведомления глобально:** в `feature_flags.py` добавить
  в `DEFAULTS` ключи `horoscope_enabled: False` и т.п.
- **Отключить карму:** закомментировать блок `Karma roll` в `start.py`.