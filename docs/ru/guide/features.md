---
title: "Возможности - скиллы, субагенты, правила и инструменты для Claude Code"
description: "Что внутри плагина maxforge-claude для Claude Code: скиллы, субагенты с закреплёнными моделями, правила, шаблоны, инструменты и рекомендуемые дополнения, которые не поставляются."
---

# Возможности: скиллы, субагенты, правила и инструменты

## Скиллы (`skills/*/SKILL.md`)

| Скилл | Назначение |
|---|---|
| `task` | вести быструю или полную задачу: триаж, разбиение, волны, один PR |
| `spec` | сбор вводных, реестр допущений, спецификация и план |
| `project-new` | старт нового проекта: позиционирование, ADR, начальная настройка |
| `qa-verify` | проверка исправления бага или фичи по доказательствам |
| `ui-task` | добавить или изменить экран приложения с дизайн-системой и гейтами QA |
| `site` | продающие страницы через конвейер из 8 этапов с подписями |
| `handoff` | записать `progress.md` задачи |
| `project-sync` | пересобрать `docs/project/STATE.md` из git и GitHub |
| `lesson` | записать поправку вместе с проверкой |
| `grilling` | проверить план на прочность вопросами |
| `laravel-best-practices` | практики Laravel (сторонний, MIT) |
| `worker-core`, `code-pack`, `design-pack`, `research-pack`, `review-pack` | подгружаются в воркеров, не для основной сессии |

## Субагенты (`agents/*.md`)

Модель и effort закреплены во frontmatter каждого файла.

| Агент | Роль | Модель, effort |
|---|---|---|
| `verifier` | пытается опровергнуть, что завершённая задача работает | opus, high |
| `code-reviewer` | одно независимое ревью интегрированного диффа | opus, high |
| `security-reviewer` | диффы с авторизацией, загрузками, оплатой, вебхуками, секретами | opus, high |
| `design-judge` | единственный судья UI | opus, high |
| `ui-builder` | собирает новые или ценные экраны | opus, medium |
| `ui-qa` | запускает UI QA на поднятой сборке и статическую проверку по правилам веб-интерфейсов (правила Vercel, MIT) со списком блокирующих правил | sonnet, medium |
| `researcher` | исследование кода и веба только на чтение | sonnet, medium |
| `lite-worker` | механические правки, переименования, документация | sonnet, medium |
| `design-critic`, `product-reviewer`, `marketing-reviewer`, `slop-detector` | рецензенты дизайн-панели | sonnet, medium |

## Правила (`rules/*.md`)

Всегда включены: `code-quality`, `task-lifecycle`, `project-state`. По путям, с принуждением через гейт правил: `design-ui-ux`, `ui-engineering-qa`, `laravel-php`, `vue-ts`, `python`, `llm-features`.

## Шаблоны и инструменты

В `templates/project/` лежат файлы для репозитория (`PROJECT.md`, `STATE.md`, `DESIGN.md`, спецификация, отчёт проверки, дизайн-скоркард). В `tools/`: создание worktree (`wt-new.sh`), подбор тестов (`affected-tests`, `q`), карта файла (`outline`), UI-раннеры и отчёты по расходу (`usage-report.py`, `token-audit.py`).

## Дополнительные файлы плагина

- `extras/output-styles/dense-en.md`: короткие ответы, вердикт первым.
- `extras/rules/core.md`: общие базовые правила процесса, не больше 80 строк.

## Рекомендуемые дополнения (не поставляются)

Автор пользуется и скиллами, написанными другими людьми. В плагин они не входят: ставьте их у авторов и проверяйте лицензию каждого сами.

| Скиллы | Источник |
|---|---|
| маркетинговые (copywriting, cro, content-strategy, customer-research, product-marketing, marketing-psychology, competitor-profiling) | github.com/coreyhaines31/marketingskills |
| контекст-инжиниринг (context-compression, context-fundamentals, context-optimization, harness-engineering, multi-agent-patterns) | github.com/muratcankoylan/Agent-Skills-for-Context-Engineering |
| taste-skill, redesign-skill | github.com/leonxlnx/taste-skill |
| stop-slop | github.com/hardikpandya/stop-slop |
| council-review | github.com/ngmeyer/council-review |
| emil-design-eng | github.com/emilkowalski/skill |

Плагин работает и без них: у дизайн- и маркетинговых скиллов просто меньше референсов.
