# 全国天气看板（和风天气版）

此目录作为 GitHub Pages 仓库根目录使用，包含全国 338 城市页面、QWeather 定时拉取脚本和 GitHub Actions 发布流程。网页只读取 `weather-data.json`，JWT 私钥仅由 GitHub Actions Secret 使用，不会下发到浏览器。

## 自动更新和免费额度

- GitHub Actions 按北京时间每天 08:30 和 17:00 执行。
- 逐天预报每天早上拉取一次，实况天气早晚更新，分钟级降水每次挑选降雨信号最强的 11 个城市。
- 在免费额度内，脚本按每天约 980 次请求规划，并按免费 QPM 限制控制请求速度。当前天气为兼顾额度会轮换少数城市的其中一次更新；每个城市每天至少更新一次。
- 页面显示接口实际返回的预报天数。免费套餐是否返回 3 天或 7 天以和风控制台及接口响应为准，不能显示 16 天；分钟级降水仅覆盖中国，时效为未来 2 小时。
- 天气页面需要展示和风天气归属说明，页脚已有来源链接。

## GitHub 仓库配置

1. 将本目录内的所有文件（包括隐藏目录 `.github`）上传到天气看板仓库根目录，保留 `index.html`、`cities.json`、`qweather_refresh.py`、`requirements.txt`、`weather-data.json` 和 `.github/workflows/qweather-pages.yml`。
2. 在仓库 **Settings → Secrets and variables → Actions** 中添加 Repository variables：
   - `QWEATHER_API_HOST`：`je2r72q662.re.qweatherapi.com`
   - `QWEATHER_KID`：凭据 ID `KJGUK27CAX`
   - `QWEATHER_SUB`：项目 ID `2KDX55UMBB`
   - `QWEATHER_ISS`：控制台“设置”页里的开发者 ID（Q 开头）
3. 在同一页面的 **Secrets** 中添加 `QWEATHER_PRIVATE_KEY`，值为该 JWT 凭据对应的完整 PEM 私钥内容。私钥不要提交进仓库，也不要粘贴到公开网页或聊天中。
4. 在 **Settings → Pages → Build and deployment** 把 Source 设为 **GitHub Actions**。
5. 在 **Settings → Actions → General → Workflow permissions** 允许工作流读写仓库内容。
6. 打开 **Actions → Refresh QWeather data and publish Pages → Run workflow**。运行成功后页面会发布；之后工作流按计划自动更新。

如果当前和风凭据的 API 限制启用了“指定数据”，请确保至少允许实况天气、天气预报、分钟降水。脚本只调用这三类数据。
