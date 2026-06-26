# shop-asset-pipeline

上传一张产品图，自动产出电商平台常用素材：1:1 白底主图、1:1 场景图和产品视频。

## 特性

- **白底主图**：基于 `rembg` 本地抠图，无需 API。
- **1:1 产品图片**：所有产品图片等比例放入正方形画布，不拉伸、不裁切产品边缘细节。
- **场景图**：通过 DashScope / Qwen-Image 生成，并强制保存为 1:1。
- **产品视频**：通过 Kling 图生视频生成，可选字幕。
- **Web UI**：Streamlit 浏览器界面，上传即可使用。
- **本地编排**：只有调用外部生成 API 时才需要网络。

## 5 分钟上手

### 1. 安装 Python 3.11+

```powershell
winget install Python.Python.3.11
```

### 2. 安装依赖

```powershell
cd shop-asset-pipeline
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 配置 API Key

```powershell
copy .env.example .env
notepad .env
```

填写 `DASHSCOPE_API_KEY`，如需生成视频再填写 `KLING_API_KEY` / `KLING_API_SECRET`。

注册地址：

- DashScope: https://dashscope.console.aliyun.com/apiKey
- Kling: https://klingai.kuaishou.com/dev

### 4. 启动

```powershell
streamlit run app.py
```

浏览器会自动打开 http://localhost:8501。

## 使用

1. 上传产品图，建议光线均匀、主体清晰。
2. 选择产品类型：服装、3C、食品或其他。
3. 选择主图尺寸，输出会保持 1:1 正方形。
4. 勾选是否生成场景图和视频。
5. 点击“开始生成”，结果会保存到 `outputs/{产品ID}/`。

## 质量规则

- 主图不再居中裁切原图，而是完整保留产品后等比例缩放。
- 场景图请求尺寸固定为 `1024*1024`。
- 场景图下载后会再次规整为正方形，避免外部 API 返回非方图。
- 提示词会要求模型保持产品形状、比例、颜色、纹理、logo 和细节。

## 项目结构

```text
src/shop_pipeline/
├── config.py             # .env 配置读取
├── image_utils.py        # 图片等比例正方形处理
├── logging_setup.py      # 统一日志
├── pipeline.py           # 流水线编排
├── steps/                # 各处理步骤
│   ├── remove_bg.py
│   ├── generate_scene.py
│   ├── generate_video.py
│   └── postprocess.py
├── prompts/              # 各产品类型的 prompt 模板
└── clients/              # 外部 API 客户端
```

## 开发

```powershell
pytest
pytest --cov
ruff check .
```

## 许可

仅供个人使用。生成内容需符合平台规则，并确保你拥有产品图版权或使用授权。
