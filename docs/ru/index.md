---
layout: home
title: "maxforge-claude - Claude Code для больших задач и целых проектов"
description: "Плагин Claude Code: спецификация до кода, параллельные субагенты в отдельных рабочих деревьях, проверяющий агент, один PR. Хуки отклоняют короткие пути. Токенов примерно в 1,49 раза больше."
hero:
  name: maxforge-claude
  text: "Claude Code для больших задач и целых проектов: сначала план, потом параллельные агенты, доказательства перед каждым PR."
  tagline: "Плагин Claude Code: спецификация до кода, параллельные субагенты в отдельных рабочих деревьях, проверяющий агент, один PR. Хуки отклоняют короткие пути, от push в main до PR с ненажатыми кнопками."
  image:
    src: /readme/art/hero.webp
    alt: "Иллюстрация: робот-прораб режет большой чертёж на карточки задач; шесть роботов параллельно собирают детали, каждый в своей стеклянной кабинке; детали проходят янтарные ворота проверки и складываются в одну башню."
  actions:
    - theme: brand
      text: "Установка: 3 команды"
      link: /ru/guide/install
    - theme: alt
      text: Как идёт задача
      link: /ru/guide/workflow
    - theme: alt
      text: GitHub
      link: https://github.com/sanctusmorte/maxforge-claude
features:
  - icon: { src: /readme/art/parallel.webp, width: 160, height: 107 }
    title: Большая задача от начала до конца
    details: Сортировка, спецификация с требованиями и волнами, по субагенту на часть в своём рабочем дереве и ветке, интеграционная ветка, одно ревью, проверяющий агент, один PR.
    link: /ru/guide/workflow
  - icon: { src: /readme/art/project.webp, width: 160, height: 107 }
    title: Целый проект
    details: "/maxforge-claude:project-new: исследование, PROJECT.md и ADR, которые ревьюер пытается опровергнуть, старт с CI и тестовым стендом, этапы, которые становятся задачами. STATE.md генерируется из git и GitHub."
  - icon: { src: /readme/art/relay.webp, width: 160, height: 107 }
    title: Длинные сессии без потери нити
    details: progress.md задачи коммитится перед сжатием контекста и возвращается после него; субагент у предела контекста передаёт работу через FENCE-HANDOFF.
  - icon: { src: /readme/art/verifier.webp, width: 107, height: 107 }
    title: Доказательство перед «готово»
    details: Проверяющий агент, который не писал код, пытается его опровергнуть; остановка с непроверенными требованиями блокируется. PR с интерфейсом требует отчёт о кликах и отчёт о вёрстке.
    link: /ru/guide/gates
  - icon: { src: /readme/art/gate.webp, width: 107, height: 107 }
    title: Гейты в любом репозитории
    details: Push в main, force-push, --no-verify, rm -rf ~, разрушительные команды БД и секреты в коммите отклоняют хуки, и каждый отказ называет причину.
    link: /ru/guide/gates
  - icon: { src: /readme/art/lessons.webp, width: 107, height: 107 }
    title: Исправления становятся проверками
    details: Когда вы поправляете агента, lesson-capture это отмечает, а навык lesson записывает, что было не так, как правильно, и проверку; каждый новый субагент получает активные уроки.
---

## Установка

```text
/plugin marketplace add sanctusmorte/maxforge-claude
/plugin install maxforge-claude@maxforge-claude
/maxforge-claude:setup
```

`setup` сначала показывает пробный прогон, затем копирует правила в `~/.claude/rules/maxforge/` (старая копия сохраняется) и запускает `maxforge doctor`. После этого откройте новую сессию, чтобы правила подгрузились.

::: info Цена
Токенов уходит больше, а не меньше: примерно в 1,49 раза больше, чем в чистом Claude Code, при равном качестве (A/B-замер автора, 2026-10-13). Плагин не редактирует ваш `CLAUDE.md`.
:::

## Как выглядит отказ

![Повтор четырёх настоящих выводов хуков: guard-bash отклоняет git push origin main и rm -rf ~, secret-scan отклоняет коммит с ключом в стиле AWS, stop-guard не даёт закончить с тремя непроверенными требованиями.](/readme/terminal-light.svg)

Гейт дизайна на тестовой странице, дословно из `hooks/guard-bash.py` (хуки отвечают по-английски):

```text
guard-bash: design gate: a PASS scorecard exists but is not complete — dashboard/scorecard.md: dead-clicks: 2 control(s) without effect or with an error: NO_EFFECT «Dead button», ERROR «Throwing button» — every State matrix row needs a screenshot or an 'n/a reason'; every control needs an effect in dead-clicks/report.json (allowlist only with a reason) or the scorecard says 'Interaction: n/a — <reason>'; geometry/report.json (tools/ui-geometry.mjs) with 0 errors or 'Geometry: n/a — <reason>' (templates/project/design-scorecard.md § State matrix, § Interaction, § Geometry)
```

Все гейты с условиями и переменными-обходами: [Гейты](/ru/guide/gates).

## Сравнение

Другие наборы предупреждают, советуют или полагаются на текст ревью; здесь хук отклоняет вызов инструмента и называет недостающий отчёт. Таблица со ссылками: [README, сравнение](https://github.com/sanctusmorte/maxforge-claude/blob/main/README.ru.md#сравнение-с-тем-чем-вы-возможно-уже-пользуетесь).

Требования: Python 3.10+ и git. Необязательно: `gh`, Node 18+ и Playwright для UI-инструментов. Лицензия: MIT. Телеметрии нет.
