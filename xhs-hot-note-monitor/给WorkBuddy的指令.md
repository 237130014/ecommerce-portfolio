# 小红书热门笔记抓取 — 给 WorkBuddy 的一句话指令

> 用法：让对方把下面这段**指令**原样复制，粘贴发给他们的 WorkBuddy 即可。
> WorkBuddy 会自动完成「装环境 → 改关键词 → 抓取 → 生成看板」全流程，无需对方懂技术。

---

## 📋 复制这段发给 WorkBuddy

```text
帮我运行「小红书热门笔记抓取」工具，步骤如下：

1. 先执行这条命令克隆工具仓库（如果已经克隆过就跳过）：
   git clone https://github.com/237130014/ecommerce-portfolio.git

2. 进入工具目录 ecommerce-portfolio/xhs-hot-note-monitor，检查并准备好 Python 环境（命令里的路径，Windows 用 .venv\Scripts\python.exe，Mac/Linux 用 .venv/bin/python，按系统选一个）：
   - 如果没有 .venv 目录，先创建：python -m venv .venv
   - 安装依赖：pip install -r requirements.txt（用 .venv 里的 python 执行，可加 -i https://pypi.tuna.tsinghua.edu.cn/simple 加速）
   - 装浏览器内核：playwright install chromium（同样用 .venv 里的 python 执行）

3. 我要抓取的关键词是：【在这里填你的关键词，例如：黄金项链、银饰耳环、珍珠手链】
   请你把 references/keywords.json 里的 keywords 改成这些词（多个词用逗号隔开，保持 JSON 格式）。

4. 运行抓取（首次会自动弹出二维码，请让我用小红书 App 扫码登录）：
   .venv\Scripts\python.exe run.py   （Mac/Linux 用 .venv/bin/python run.py）

5. 抓取完成后，把生成结果告诉我：
   - xhs-baseline 文件夹里的「小红书热门笔记-日期.html」是网页看板
   - 「热门笔记明细.csv」是表格
   并把这两个文件的路径展示给我，方便我打开查看。
```

---

## 📝 对方只需改一个地方

上面第 3 步里的**【在这里填你的关键词】**，换成对方想抓的词即可，其余原样复制。

---

## ✅ 对方能省掉的事

| 原本要自己做的 | 现在 WorkBuddy 代劳 |
|----------------|---------------------|
| 装 Python | ✅ 自动判断、自动装 |
| 双击 setup.bat | ✅ 自动装依赖 + 内核 |
| 编辑 keywords.json | ✅ 按你说的词自动改 |
| 双击 run.bat | ✅ 自动跑 |
| 找结果文件 | ✅ 自动定位并展示路径 |
| 扫码登录 | 首次仍需本人扫一次（安全所需） |

---

## ⚠️ 唯一需要对方本人做的

**首次扫码登录**——因为登录态绑定对方的个人账号，WorkBuddy 不能代扫码（也不该代）。扫码只需一次，之后自动复用。
