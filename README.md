# 全国天气看板（Streamlit）

## 部署到 Streamlit Community Cloud

1. 将本目录内的 `app.py`、`requirements.txt` 和 `README.md` 上传到 GitHub 仓库根目录并提交。
2. 登录 [Streamlit Community Cloud](https://share.streamlit.io/)，连接 GitHub。
3. 选择 **Create app**，选择你的仓库和 `main` 分支。
4. Main file path 填 `app.py`，点击 **Deploy**。
5. 部署完成后使用 Community Cloud 提供的 `*.streamlit.app` 地址访问。

依赖文件和入口文件放在仓库根目录，符合 Community Cloud 的文件组织要求。

## 数据刷新

使用 Open-Meteo 免费天气 API；全国城市数据按北京时间每天 08:30 和 17:00 设置缓存时次，并在应用运行时首次请求该时次数据。Streamlit Community Cloud 的应用可能休眠，因此无法承诺休眠期间后台准点刷新；用户重新打开或应用重新运行后会获取当前时次。
