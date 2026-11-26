# Dead-click report

NAVIGATED: 1 · STATE_CHANGED: 1 · OVERLAY: 1 · NO_EFFECT: 1 · ERROR: 1 · SKIPPED: 1

| verdict | text | selector | page | viewport | evidence |
|---|---|---|---|---|---|
| ERROR | Throwing button | `#boom` | file://<repo>/tools/fixtures/dead-clicks/index.html | 1440x900 | pageerror: boom [shot](evidence/ui/dead-clicks-fixture/shots/09ea88-1440x900-4.png) |
| NO_EFFECT | Dead button | `#dead` | file://<repo>/tools/fixtures/dead-clicks/index.html | 1440x900 | no url/request/overlay/aria/DOM change [shot](evidence/ui/dead-clicks-fixture/shots/09ea88-1440x900-3.png) |
| SKIPPED | Удалить всё | `#del` | file://<repo>/tools/fixtures/dead-clicks/index.html | 1440x900 | destructive by text/aria |
| NAVIGATED | Go to page two | `#go` | file://<repo>/tools/fixtures/dead-clicks/index.html | 1440x900 | file://<repo>/tools/fixtures/dead-clicks/index.html -> file://<repo>/tools/fixtures/dead-clicks/page2.html |
| STATE_CHANGED | Toggle | `#toggle` | file://<repo>/tools/fixtures/dead-clicks/index.html | 1440x900 | aria/checked changed |
| OVERLAY | Open dialog | `#open` | file://<repo>/tools/fixtures/dead-clicks/index.html | 1440x900 | overlays 0 -> 1 |
