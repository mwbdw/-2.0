# 🔥 抖音续火花

自动与抖音好友互发消息，保持火花连续不断。macOS 独立 App，无需安装 Python。

![macOS](https://img.shields.io/badge/macOS-12%2B-black?logo=apple)
![Python](https://img.shields.io/badge/Python-3.9-blue?logo=python)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 功能

- 自动向指定好友发送消息，维持抖音火花
- 支持多个好友、多条消息模板随机发送
- 定时调度：设定时间每天自动运行
- 无头模式：后台静默运行，不干扰正常使用
- 实时日志：Console 风格操作记录

## 下载安装（推荐）

> 适合所有用户，无需安装 Python 或任何依赖。

1. 前往 [Releases](https://github.com/mwbdw/-2.0/releases/latest) 下载 `火花2.0.zip`
2. 解压后，打开**终端**执行：

```bash
xattr -cr ~/Downloads/火花2.0.app
```

3. 将 `火花2.0.app` 拖入「应用程序」文件夹，双击打开
4. 首次运行会自动下载 Chromium（约 130MB），稍等片刻即可

> ⚠️ 第 2 步必须执行。macOS 对未经 Apple 认证的 App 会显示「已损坏」，这是正常的安全机制，运行 xattr 命令后即可解除。

---

## 从源码运行

```bash
git clone https://github.com/mwbdw/-2.0.git
cd -- -2.0

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

python3 app.py
```

## 系统要求

| 项目 | 要求 |
|------|------|
| 系统 | macOS 12 Monterey 或更高 |
| 芯片 | Apple Silicon（M1/M2/M3） |
| 网络 | 首次运行需联网下载 Chromium |

## 使用说明

1. 点击「登录」，在弹出窗口中扫码登录抖音
2. 在「好友列表」中添加要发送的好友备注名
3. 在「消息模板」中添加发送内容（每次随机选一条）
4. 设置定时时间，点击「启动定时」
5. 开启「无头模式」后台静默运行

## 免责声明

本项目仅供学习交流，请勿用于商业用途或大规模自动化操作。使用本工具造成的账号风险由用户自行承担。

---

<p align="center">Made with ❤️ for keeping streaks alive</p>
