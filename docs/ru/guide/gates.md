---
title: "Гейты качества и хуки Claude Code - что блокирует каждый"
description: "Каждый хук и гейт maxforge-claude: какую команду или действие он отклоняет, файл реализации, тест-доказательство и способ обхода."
---

# Гейты качества: что блокирует каждый хук Claude Code

Каждый гейт это Python-хук (только стандартная библиотека), зарегистрированный в `hooks/hooks.json`. Отказ возвращается модели с однострочной причиной и подсказкой. Все пути внутри плагина.

## PreToolUse для Bash

| Гейт | Отклоняет | Файл | Тест | Обход |
|---|---|---|---|---|
| Git и разрушительные команды | push в `master`/`main`/`dev`; force-push в защищённую ветку; `commit --no-verify`/`-n`; разрушительные команды БД (migrate fresh/reset, db wipe, drop database/table) вне тестовой базы, в том числе по ssh; `rm -rf` вне временных, сборочных и зависимостных путей; `git reset --hard`, `git clean -f`, `git checkout -- .` в основном checkout; PR в `main`, пока есть `origin/dev` | `hooks/guard-bash.py` | `tools/test-hooks.py` | `CLAUDE_GUARD_OFF=1 <команда>` |
| Дизайн-гейт | PR не в draft с UI-файлами без скоркарда `Verdict: PASS`, который новее последнего UI-коммита, или без свежего отчёта dead-click (если в теле PR не объяснено, почему n/a) | `hooks/guard-bash.py` | `tools/test-designgate.py` | то же |
| Геометрический гейт | тот же PR без `geometry/report.json`, который новее последнего UI-коммита и без ошибок (если в скоркарде не указано `Geometry: n/a - <причина>`); отчёт строится проверками перекрытий, обрезки, переполнения и выравнивания при 390/768/1440/2560 px с режимом растянутого текста | `hooks/guard-bash.py` | `tools/test-ui-geometry.mjs` | то же |
| Сканер секретов | коммит, добавленные строки которого похожи на учётные данные, или в который попали `.env`, `*.pem`, `id_rsa`, `*.key`, JSON сервисного аккаунта | `hooks/secret-scan.py` | отдельного теста нет | `CLAUDE_ALLOW_SECRETS=1 git commit ...` |
| Подсказка против выгрузок | `cat`/`sed -n`/`head`/`tail`/`less` обычного файла длиннее лимита строк внутри git worktree | `hooks/dump-nudge.py` | `tools/test-hooks.py` | нет; читайте диапазон |
| Фоновый маршрутизатор | не отказ: переносит сборки, установки, запуски тестов и деплои в фон (субагенты гоняют тесты на переднем плане с таймаутом 270 с) | `hooks/bg-router.py` | `tools/test-hooks.py` | `CLAUDE_BG_ROUTER_OFF=1` |

## PreToolUse для Edit и Write

| Гейт | Отклоняет | Файл | Тест | Обход |
|---|---|---|---|---|
| Гейт правил | правку файла, подпадающего под правило стека (`paths:` во frontmatter `rules/*.md`), пока агент не прочитал это правило в своём транскрипте | `hooks/rules-gate.py` | `tools/test-hooks.py` | `CLAUDE_GUARD_OFF=1` |

## Token guard

`hooks/token-guard.py` выдаёт однострочные отказы: ограда контекста для субагентов (затем `FENCE-HANDOFF`), пустые ожидания (длинный `sleep`, `gh ... --watch`), чтение файла целиком выше лимита, повторное чтение уже прочитанного, запуск всего набора тестов без области, возобновление «холодного» субагента. Тесты: `tools/test-hooks.py`, `tools/test-token-audit.py`. Обход: `CLAUDE_TOKEN_GUARD_OFF=1`. Журнал отказов: `logs/token-guard.log`.

## Жизненный цикл сессии

| Хук | Событие | Эффект | Тест |
|---|---|---|---|
| `hooks/stop-guard.py` | Stop | не даёт завершить, пока worktree этой сессии грязный или в нём есть непушенные коммиты | `tools/test-hooks.py` |
| `hooks/precompact-handoff.py` | PreCompact | обновляет и коммитит `progress.md` задачи, пушит в фоне | `tools/test-continuity.py` |
| `hooks/session-restore.py` | SessionStart (compact, resume) | подставляет `progress.md`, `git status` и последние коммиты | `tools/test-continuity.py` |
| `hooks/project-sync.py` | SessionStart | короткая сводка `docs/project/STATE.md` | `tools/test-hooks.py` |
| `hooks/lesson-capture.py` | промпт | помечает вероятную поправку, чтобы записать её как урок | `tools/test-lessons.py` |
| `hooks/ctx-monitor.py`, `hooks/statusline.py` | PostToolUse, строка статуса | необязательный бюджет токенов задачи и строка статуса | `tools/test-hooks.py` |
| `hooks/doc-sync-reminder.py` | PostToolUse | напоминает держать документацию 1:1 с кодом | отдельного теста нет |

## Инструменты проверки

<img src="/readme/art/clicks.webp" width="280" alt="Иллюстрация: маленький робот с лупой нажимает каждую кнопку на пульте; одна нажатая кнопка остаётся тёмной.">

| Инструмент | Что делает | Самотест |
|---|---|---|
| `tools/dead-clicks.mjs` | нажимает каждый элемент по маршруту, размеру экрана и режиму; `NO_EFFECT` или `ERROR` блокирует | `tools/fixtures/dead-clicks/` |
| `tools/ui-qa.mjs` | UI-проверки production-сборки по сетке размеров экрана | `tools/test-uiqa.mjs` |
| `tools/harness-lint.py` | проверяет числа в правилах, пути, модель и effort агентов, регистрацию хуков | запустите напрямую |

## Запуск самотестов

```bash
python3 tools/test-hooks.py
```

Он запускает и все `tools/test-*.py`. Код выхода 0 значит ноль падений.

## Ограничения

Гейты отклоняют известные шаблоны и не понимают намерение. Незнакомые им команды проходят. Если гейт вам мешает, используйте его обход и назовите причину либо [отключите его](/ru/guide/faq#как-отключить-один-хук).
