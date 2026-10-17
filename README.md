# 全国天气看板（和风天气版）
此仓库提供全国 338 个城市的天气看板。网页仅读取 GitHub Actions 生成的 weather-data.json 快照，不直接请求天气接口，也不会公开 API Key。
## 自动更新
- 目标刷新时间：每天北京时间 08:30 和 17:10。
- GitHub Actions 会在早上 08:45、09:15、09:30、09:45、10:15、10:30、10:45，以及下午 17:25、17:40、17:55、18:10、18:25、18:40 补跑。每次补跑先检查该时段是否已经更新；已更新就跳过天气请求，避免重复消耗额度。
- GitHub 定时任务可能延迟或漏派发；多次补跑能提高成功机会，但平台调度无法保证绝对准时。
- 脚本按正常每天约 980 次 API 请求规划，并把已用请求数写入快照，限制每天最多请求 1000 次；请求频率按免费套餐限制控制。少数城市的实况会轮换跳过一次，每个城市每天至少更新一次。
- 逐天预报显示接口实际返回的天数，具体范围取决于和风天气凭据权限；分钟降水是未来 2 小时临近预报。
## GitHub 配置
在 Settings → Secrets and variables → Actions 配置：
- Repository variable：QWEATHER_API_HOST，值为和风天气控制台提供的专属 API Host。
- Repository secret：QWEATHER_API_KEY，值为控制台生成的 API Key。请勿提交到仓库或网页代码。
Pages 的发布来源应设为 GitHub Actions。配置完成后，进入 Actions → Refresh QWeather data and publish Pages → Run workflow 手动运行一次；之后按计划自动更新。
如果凭据启用了 API 限制，请确保允许实况天气、天气预报和分钟降水。页面页脚包含和风天气归属链接。
