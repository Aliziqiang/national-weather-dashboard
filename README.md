# 全国天气看板（和风天气版）

此仓库提供全国 338 个城市的天气看板。网页仅读取 GitHub Actions 生成的 `weather-data.json` 快照，不直接请求天气接口，也不会公开 API Key。

## 自动更新

- 每天北京时间 08:30、17:00 运行 GitHub Actions。
- 实况天气早晚更新；逐天预报每天早上更新；分钟降水每次更新重点城市。
- 脚本按每天约 980 次 API 请求规划，并控制请求频率。受免费额度限制，少数城市的实况在其中一次运行轮换跳过，每个城市每天至少更新一次。
- 逐天预报显示接口实际返回的天数，具体范围取决于和风天气凭据权限；分钟降水是未来 2 小时临近预报。

## GitHub 配置

在 **Settings → Secrets and variables → Actions** 配置：

- Repository variable：`QWEATHER_API_HOST`，值为和风天气控制台提供的专属 API Host。
- Repository secret：`QWEATHER_API_KEY`，值为控制台生成的 API Key。请勿提交到仓库或网页代码。

Pages 的发布来源应设为 **GitHub Actions**。配置完成后，进入 **Actions → Refresh QWeather data and publish Pages → Run workflow** 手动运行一次；之后按计划自动更新。

如果凭据启用了 API 限制，请确保允许实况天气、天气预报和分钟降水。页面页脚包含和风天气归属链接。
