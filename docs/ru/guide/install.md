---
title: "Установка плагина maxforge-claude для Claude Code"
description: "Установите maxforge-claude за минуту через маркетплейс плагинов Claude Code, запустите setup для копирования правил и проверьте результат командой maxforge doctor."
---

# Установка плагина для Claude Code за минуту

## Шаги

Внутри Claude Code:

```text
/plugin marketplace add sanctusmorte/maxforge-claude
/plugin install maxforge-claude@maxforge-claude
/maxforge-claude:setup
```

Затем попросите Claude выполнить проверку (`bin/` есть в PATH инструмента Bash в Claude Code, а не в вашей оболочке):

```bash
maxforge doctor
```

## Что делает setup

Claude Code не подгружает правила из плагина автоматически, поэтому `/maxforge-claude:setup` копирует `rules/*.md` и общие базовые правила в `~/.claude/rules/maxforge/`. Всё, что заменяется, сохраняется в резервную копию, рядом пишется отметка версии (`.maxforge-version`). Хук SessionStart предупреждает, если копия отсутствует или старше плагина.

| Флаг | Действие |
|---|---|
| (нет) | скопировать правила |
| `--settings` | по желанию: влить рекомендуемые настройки в ваш `settings.json`, сначала копия |
| `--node` | установить Playwright и axe для UI-инструментов (`ui-qa`, `dead-clicks`) |
| `--dry-run` | показать, что изменится |

## Требования

- Обязательно: Python 3.10+ (хуки используют только стандартную библиотеку) и git.
- Необязательно: `gh` для работы с PR; Node 18+ и Playwright для UI QA и проверки dead-click.

## Проверка

`maxforge doctor` показывает каждое требование, копию правил и её версию. Если хук кажется молчащим, начните с doctor.

## Дополнительные файлы

`extras/output-styles/dense-en.md` это стиль коротких ответов (вердикт первым, без воды). `extras/rules/core.md` это общая версия правил процесса. Оба файла обычные: скопируйте туда, где нужно.

Удаление: [удаление](/ru/guide/uninstall). Что делает каждый гейт: [гейты](/ru/guide/gates).
