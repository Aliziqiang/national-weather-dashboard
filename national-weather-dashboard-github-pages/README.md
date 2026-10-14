# 全国天气看板

GitHub Pages 静态站点部署目录。入口文件为 `index.html`。

## 发布

将本目录内容推送到 GitHub 仓库后，在仓库 Settings → Pages 中选择从 `main` 分支的根目录发布。页面会从浏览器直接请求 Open-Meteo 天气 API。

天气数据仅在页面打开时获取，并在页面打开期间按看板设定的时刻刷新。
