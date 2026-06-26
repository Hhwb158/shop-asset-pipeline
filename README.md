# shop-asset-pipeline

> 输入一张产品图,自动产出电商平台所需素材:白底主图 + 场景图 + 短视频。

## 特性

- **白底主图**:基于 `rembg` 本地抠图,无需 API
- **场景图**:阿里通义(Qwen-Image)生成,中文场景描述准确
- **产品视频**:可灵(Kling)图生视频,5~10 秒,带字幕
- **Web UI**:Streamlit,浏览器拖图即用
- **完全本地编排**,只在调用外部 API 时走网络

## 5 分钟上手

### 1. 安装 Python 3.11+

```powershell
winget install Python.Python.3.11
```

### 2. 克隆并安装依赖

```powershell
git clone git@github.com:Hhwb158/shop-asset-pipeline.git
cd shop-asset-pipeline
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 配置 API Key

```powershell
copy .env.example .env
notepad .env
# 填入 DASHSCOPE_API_KEY 和 KLING_API_KEY / KLING_API_SECRET
```

注册地址:
- 通义 DashScope:https://dashscope.console.aliyun.com/apiKey
- 可灵:https://klingai.kuaishou.com/dev

### 4. 启动

```powershell
streamlit run app.py
# 浏览器会自动打开 http://localhost:8501
```

## 使用

1. **上传产品图**(手机拍即可,建议光线均匀)
2. **选产品类型**:服饰 / 3C / 食品 / 其他
3. **勾选要生成的素材**:白底主图 / 场景图 / 产品视频
4. **点 [开始生成]**,等 1~5 分钟
5. **在 outputs/{产品ID}/ 目录** 下载所有素材

## 架构

```
上传 → 抠图 (rembg) → 白底主图
                     ↓
              DashScope 场景图
                     ↓
              Kling 图生视频
                     ↓
              ffmpeg 加字幕
                     ↓
                outputs/{id}/
```

## 项目结构

```
src/shop_pipeline/
├── config.py             # .env 集中读取
├── logging_setup.py      # 统一日志
├── pipeline.py           # 编排
├── steps/                # 每个 step 一个文件
│   ├── remove_bg.py
│   ├── generate_scene.py
│   ├── generate_video.py
│   └── postprocess.py
├── prompts/              # 各产品类型的 prompt 模板
└── clients/              # 各家 API 客户端(mock 友好)
```

## 开发

```powershell
# 测试
pytest

# 覆盖率
pytest --cov

# Lint
ruff check .
```

## 许可

仅供个人使用。注意:生成内容需符合平台合规要求,确保你拥有商品图版权。
