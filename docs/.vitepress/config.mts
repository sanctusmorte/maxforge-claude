import { defineConfig, type HeadConfig } from 'vitepress'

const SITE = 'https://sanctusmorte.github.io/maxforge-claude/'
const REPO = 'https://github.com/sanctusmorte/maxforge-claude'

const descEn =
  'maxforge-claude is a Claude Code plugin: hooks that block unsafe git and shell commands, subagents for review and verification, UI QA that clicks every button, and state that survives compaction.'
const descRu =
  'maxforge-claude: плагин для Claude Code. Хуки блокируют опасные git и shell команды, субагенты проверяют работу, UI QA нажимает каждую кнопку, состояние задачи переживает сжатие контекста.'

const sidebar = (p: string, t: Record<string, string>) => [
  {
    text: t.guide,
    items: [
      { text: t.why, link: `${p}/guide/why` },
      { text: t.install, link: `${p}/guide/install` },
      { text: t.features, link: `${p}/guide/features` },
      { text: t.gates, link: `${p}/guide/gates` },
      { text: t.workflow, link: `${p}/guide/workflow` },
      { text: t.faq, link: `${p}/guide/faq` },
      { text: t.uninstall, link: `${p}/guide/uninstall` },
    ],
  },
]

// 'guide/why.md' -> 'guide/why'; 'ru/index.md' -> 'ru/'
const toPath = (rel: string) =>
  rel.replace(/(^|\/)index\.md$/, '$1').replace(/\.md$/, '')

export default defineConfig({
  title: 'maxforge-claude',
  base: '/maxforge-claude/',
  cleanUrls: true,
  srcExclude: ['project/**'],
  lastUpdated: false,
  sitemap: { hostname: SITE },
  head: [
    ['link', { rel: 'icon', href: '/maxforge-claude/og.svg', type: 'image/svg+xml' }],
    ['meta', { name: 'theme-color', content: '#d97757' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'maxforge-claude' }],
    ['meta', { property: 'og:image', content: `${SITE}og.svg` }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:image', content: `${SITE}og.svg` }],
  ],
  transformHead({ pageData }) {
    const rel = pageData.relativePath
    const isRu = rel.startsWith('ru/')
    const enPath = toPath(isRu ? rel.slice(3) : rel)
    const ruPath = toPath(isRu ? rel : `ru/${rel}`)
    const self = SITE + (isRu ? ruPath : enPath)
    const title = pageData.frontmatter.title || pageData.title || 'maxforge-claude'
    const desc = pageData.frontmatter.description || pageData.description || (isRu ? descRu : descEn)
    const head: HeadConfig[] = [
      ['link', { rel: 'canonical', href: self }],
      ['link', { rel: 'alternate', hreflang: 'en', href: SITE + enPath }],
      ['link', { rel: 'alternate', hreflang: 'ru', href: SITE + ruPath }],
      ['link', { rel: 'alternate', hreflang: 'x-default', href: SITE + enPath }],
      ['meta', { property: 'og:title', content: title }],
      ['meta', { property: 'og:description', content: desc }],
      ['meta', { property: 'og:url', content: self }],
      ['meta', { property: 'og:locale', content: isRu ? 'ru_RU' : 'en_US' }],
      ['meta', { name: 'twitter:title', content: title }],
      ['meta', { name: 'twitter:description', content: desc }],
    ]
    return head
  },
  locales: {
    root: {
      label: 'English',
      lang: 'en',
      description: descEn,
      themeConfig: {
        nav: [
          { text: 'Guide', link: '/guide/why' },
          { text: 'Install', link: '/guide/install' },
          { text: 'Gates', link: '/guide/gates' },
        ],
        sidebar: sidebar('', {
          guide: 'Guide', why: 'Why a harness', install: 'Install', features: 'Features',
          gates: 'Gates', workflow: 'Workflow', faq: 'FAQ', uninstall: 'Uninstall',
        }),
        outline: { label: 'On this page' },
      },
    },
    ru: {
      label: 'Русский',
      lang: 'ru',
      link: '/ru/',
      description: descRu,
      themeConfig: {
        nav: [
          { text: 'Руководство', link: '/ru/guide/why' },
          { text: 'Установка', link: '/ru/guide/install' },
          { text: 'Гейты', link: '/ru/guide/gates' },
        ],
        sidebar: sidebar('/ru', {
          guide: 'Руководство', why: 'Зачем обвязка', install: 'Установка', features: 'Возможности',
          gates: 'Гейты', workflow: 'Рабочий процесс', faq: 'FAQ', uninstall: 'Удаление',
        }),
        outline: { label: 'На странице' },
        docFooter: { prev: 'Назад', next: 'Дальше' },
        sidebarMenuLabel: 'Меню',
        returnToTopLabel: 'Наверх',
        darkModeSwitchLabel: 'Тема',
        langMenuLabel: 'Язык',
      },
    },
  },
  themeConfig: {
    socialLinks: [{ icon: 'github', link: REPO }],
    search: { provider: 'local' },
    footer: { message: 'Released under the MIT License.', copyright: 'maxforge-claude' },
  },
})
