# 世界歌剧院动态全览（opera-hub）

一个完全独立于 Codex 应用运行的个人信息站：每天定时采集全球主要歌剧院的演出排期、行业新闻和你关注艺术家的动态，自动整理成日报推送给你，同时更新网页看板供随时全览。

## 功能

- 📰 每日新闻：从歌剧行业媒体抓取最新报道，自动过滤噪音
- 🗓️ 排期数据：接入歌剧院官网订阅（iCal/JSON）
- 🎤 艺术家关注榜：指挥、导演、歌唱家的动态扫描与档案积累
- 🏛️ 国家大剧院关联识别：梳理大剧院过往歌剧制作与艺术家档案，新闻提到相关艺术家时自动特别标注
- 📊 网页看板：未来 30 天演出、最新新闻、艺术家动态一目了然
- 📮 日报推送：支持 Telegram、邮件、通用 Webhook
- ☁️ 全部部署在 GitHub，免费、无需依赖本应用

## 目录结构

```text
opera-hub/
├── config/
│   ├── news.json         # 新闻源与过滤关键词
│   ├── houses.json       # 关注的歌剧院清单与订阅链接
│   ├── artists.json      # 艺术家关注名单
│   ├── ncpa.json         # 国家大剧院过往歌剧制作与合作艺术家档案
├── src/                  # 采集、整理、推送代码
├── data/                 # 自动生成的数据与日报（会提交到仓库）
├── index.html / app.js / style.css   # 网页看板（纯静态）
└── .github/workflows/    # 每日定时任务
```

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows；macOS/Linux 用 source .venv/bin/activate
pip install -r requirements.txt
python src/run_daily.py --no-notify
```

运行后 `data/` 下会生成新闻、日报和看板数据。用浏览器打开 `index.html` 即可预览看板。

## 部署到 GitHub（免费、全自动）

1. 在 GitHub 新建一个仓库（公开或私有都可以），把本目录推送上去；
2. 打开仓库 Settings → Pages，Source 选择 "Deploy from a branch"，分支选 `main`，目录选 `/ (root)`，保存；
3. 打开仓库 Actions 页面，找到「每日歌剧动态」，点 Run workflow 手动跑一次验证；
4. 以后每天 09:00（北京时间）会自动运行：采集 → 整理 → 推送 → 更新看板。

网站地址就是 `https://<你的用户名>.github.io/<仓库名>/`。

> 看板是纯静态页面，同样可以直接拖到 Cloudflare Pages 或 Vercel 上托管，无需任何构建步骤。

## 接入数据源

### 新闻（已内置，可继续加）

已启用并通过测试的源：OperaWire、Parterre Box、Opera Today、Slipped Disc。
在 `config/news.json` 的 `sources` 里加 `{"id": "...", "name": "...", "url": "订阅地址", "enabled": true}` 即可。
`filter_keywords` 是新闻过滤关键词，只保留相关的报道，可按需增删。

### 歌剧院排期

14 家剧院的数据源已经全部配置好，见 `config/houses.json`。每家的情况：

| 剧院 | 数据源 | 状态 |
|---|---|---|
| 纽约大都会歌剧院 | 官网 API（需浏览器模式） | ✅ |
| 伦敦皇家歌剧院 | 官网日历 API | ✅ |
| 维也纳国家歌剧院 | 官网月历页（含指挥/卡司） | ✅ |
| 米兰斯卡拉 | 官网日历页 | ✅ |
| 巴黎歌剧院 | 官网节目单接口 | ✅ |
| 慕尼黑巴伐利亚国家歌剧院 | 官网演出计划页（需浏览器模式） | ✅ |
| 苏黎世歌剧院 | 官网日历（自动翻页） | ✅ |
| 萨尔茨堡音乐节 | 官网日历接口 | ✅ |
| 拜罗伊特音乐节 | 官网节目页 + 制作详情页 | ✅ |
| 芝加哥抒情歌剧院 | 官网 API（需浏览器模式） | ✅ |
| 旧金山歌剧院 | 官网 API | ✅ |
| 悉尼歌剧院 | 官网 what's on（歌剧分类） | ✅ |
| 格林德伯恩歌剧节 | — | ⚠️ 无公开接口，待确认 |
| 柏林德意志歌剧院 | — | ⚠️ 官网接口返回 500，待确认 |

其中标"需浏览器模式"的三家（大都会、芝加哥、巴伐利亚）被 Cloudflare
反爬保护，定时任务会启动一个无头浏览器先通过校验再抓取，无需你做额外设置。

数据源的具体做法参考了开源项目
[Leporello](https://github.com/philphilphil/leporello-mcp) 的抓取思路。

如需手动追加订阅源，支持通用格式：

- `ics`：iCal 日历订阅链接；
- `json`：结构化接口，用 `field_map` 指定字段名映射：

```json
{
  "type": "json",
  "url": "https://某剧院/api/performances",
  "field_map": {
    "title": "name",
    "date": "startDate",
    "composer": "composer",
    "venue": "venue",
    "url": "link"
  }
}
```

## 国家大剧院艺术家库与日报关联标注

`config/ncpa.json` 按制作逐部收录国家大剧院（NCPA）过往歌剧的主创与主演，
目前含 24 部制作档案（原创歌剧与西方经典制作）与 130 余位艺术家，覆盖：

- 原创歌剧：西施、山村女教师、赵氏孤儿、运河谣、骆驼祥子、长征、红高粱、青春之歌等
- 西方经典制作：图兰朵、托斯卡、假面舞会、纳布科、奥赛罗、游吟诗人、阿依达、齐格弗里德等

每天整理日报时，系统会把每条新闻的标题和摘要与大剧院艺术家库做比对：
一旦新闻中提到合作过的艺术家（中英文名均可识别，如“和慧”“Hui He”
“多明戈”“Plácido Domingo”），日报就会单独列出“国家大剧院关联动态”，
并附上该艺术家在大剧院合作过的剧目与年份，例如：

```text
▍国家大剧院关联动态
- Hui He returns to Salzburg as Aida ｜ OperaWire
  · 和慧（歌唱家）：曾合作 假面舞会(2012)、游吟诗人(2014)、阿依达(2015)
  · 祖宾·梅塔（指挥）：曾合作 阿依达(2015)
```

看板页面还提供“国家大剧院合作艺术家库”，可搜索艺术家及其合作制作。
比对结果同时写入 `data/digest/latest.json`（`ncpa` 字段）供前端使用，
并导出 `data/ncpa_artists.json` 作为可浏览的艺术家库数据。

### 扩充艺术家数据库

每部制作支持以下字段，直接编辑 `config/ncpa.json` 即可：

```json
{
  "id": "示例-2020",
  "year": 2020,
  "title": "剧目名",
  "composer": "作曲家",
  "type": "原创歌剧",
  "first_run": "2020-01-01",
  "roles": { "指挥": ["某人"], "导演": ["某人"] },
  "cast": [{"name": "歌手", "role": "角色名"}],
  "notes": "补充说明，也会参与关联匹配"
}
```

`aliases` 字段用于补充艺术家外文名（如 “和慧”: `["Hui He"]`），
外文名出现在新闻里时同样能命中。两字中文名（如“张艺”“王凯”）做了
边界判断，避免“张艺谋”“万方数据”这类误报。

## 配置推送渠道（选一个即可）

在 GitHub 仓库的 Secrets 里按需添加以下变量：

| 渠道 | Secret 名称 |
|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` |
| 邮件（SMTP） | `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASS`、`EMAIL_FROM`、`EMAIL_TO` |
| 通用 Webhook | `WEBHOOK_URL` |

本地测试时在终端设置同名环境变量即可，例如 PowerShell：

```powershell
$env:TELEGRAM_BOT_TOKEN = "你的 token"
$env:TELEGRAM_CHAT_ID = "你的 chat id"
python src/run_daily.py
```

优先级：Telegram → 邮件 → Webhook。都没配置时日报只写入文件，不推送。

### 本地启用浏览器模式（可选）

大都会、芝加哥、巴伐利亚这三家需要无头浏览器抓取。本地调试时：

```powershell
pip install -r requirements-browser.txt
python -m playwright install chromium
$env:OP_HUB_ENABLE_BROWSER = "1"
python src/run_daily.py --no-notify
```

GitHub Actions 每天会自动安装浏览器并启用该模式，本地不装也不影响其他剧院。

## 调整运行时间

编辑 `.github/workflows/daily-digest.yml` 里的 cron（当前为每天 01:00 UTC = 09:00 北京时间）。

## 常见问题

- **排期为空**：先检查是否开了浏览器模式（大都会/芝加哥/巴伐利亚需要）；再看运行日志里有没有"排期源抓取失败"的警告。
- **个别源抓取失败**：代码会记录警告并跳过该源，不影响整体运行。
- **看板更新慢**：GitHub Pages 在数据提交后会自动重新部署，通常几分钟内完成。
- **数据授权**：各家剧院与新闻源的数据各有使用条款，个人非商业使用通常允许署名引用，商用前请自行确认授权。
