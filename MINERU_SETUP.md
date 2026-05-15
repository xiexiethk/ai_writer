# MinerU 环境安装指南

本项目提供了两个 MinerU conda 环境配置文件：

## 📦 文件说明

### 1. `mineru_environment.yml` (完整版)
- 包含所有依赖包的精确版本
- 适用于需要完全复现现有环境的场景
- 文件较大，包含所有传递依赖

### 2. `mineru_environment_simple.yml` (精简版)
- 只包含核心依赖
- 更容易维护和安装
- 推荐**大多数情况**使用此文件

---

## 🚀 安装步骤

### 方法一：使用精简版配置（推荐）

```bash
# 1. 创建 conda 环境
conda env create -f mineru_environment_simple.yml

# 2. 激活环境
conda activate mineru

# 3. 验证安装
python -c "import mineru; print(mineru.__version__)"
```

### 方法二：使用完整版配置

```bash
# 1. 创建 conda 环境
conda env create -f mineru_environment.yml

# 2. 激活环境
conda activate mineru

# 3. 验证安装
python -c "import mineru; print(mineru.__version__)"
```

### 方法三：手动创建环境

如果自动安装失败，可以手动创建：

```bash
# 1. 创建基础环境
conda create -n mineru python=3.10 -y
conda activate mineru

# 2. 安装 MinerU 核心包
pip install mineru

# 3. 安装深度学习依赖
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 4. 安装其他依赖
pip install opencv-python pillow pdfminer-six pypdf pikepdf
pip install fastapi gradio loguru rich
```

---

## ⚙️ 系统要求

### 最低配置
- **Python**: 3.10
- **CUDA**: 12.x (GPU 加速)
- **RAM**: 8GB
- **磁盘空间**: 10GB

### 推荐配置
- **Python**: 3.10
- **CUDA**: 12.1+
- **RAM**: 16GB+
- **GPU**: NVIDIA RTX 3060 或更高
- **磁盘空间**: 20GB+

---

## 🔧 主要依赖说明

### 深度学习框架
- `torch==2.8.0` - PyTorch 核心库
- `xformers==0.0.32.post1` - Transformer 优化库
- `vllm==0.11.0` - LLM 推理加速

### 计算机视觉
- `opencv-python==4.12.0.88` - 图像处理
- `albumentations==2.0.8` - 数据增强
- `pillow==11.3.0` - 图像IO

### 文档处理
- `pdfminer-six==20250506` - PDF 解析
- `pikepdf==10.1.0` - PDF 操作
- `pypdfium2==4.30.0` - PDF 渲染
- `reportlab==4.4.7` - PDF 生成

### Web 框架
- `fastapi==0.128.0` - API 框架
- `gradio==5.49.1` - Web UI

---

## 🐛 常见问题

### 1. CUDA 版本不匹配

**问题**: 安装 torch 时提示 CUDA 版本不匹配

**解决方案**:
```bash
# 检查系统 CUDA 版本
nvidia-smi

# 根据版本安装对应的 PyTorch
# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 2. 内存不足

**问题**: 训练或推理时提示 CUDA OOM

**解决方案**:
```bash
# 使用 CPU 版本（较慢）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 或者减少批处理大小
```

### 3. 依赖冲突

**问题**: 安装时出现版本冲突

**解决方案**:
```bash
# 使用 mamba 替代 conda
conda install mamba -n base
mamba env create -f mineru_environment_simple.yml
```

### 4. Windows 上安装失败

**问题**: Windows 上某些包无法编译

**解决方案**:
```bash
# 使用预编译的 wheel 文件
pip install package_name --only-binary :all:

# 或安装 Visual Studio Build Tools
# 下载: https://visualstudio.microsoft.com/downloads/
```

---

## 📝 使用指南

### 在项目中使用 MinerU

```python
# 导入 MinerU
from mineru import SingleFileDocument

# 处理 PDF 文档
doc = SingleFileDocument("path/to/pdf")
result = doc.process()

# 获取 Markdown 内容
markdown_content = result["markdown"]
```

### 配置后端使用 MinerU

在 `backend/.env` 中配置：

```env
# MinerU 配置
MINERU_BACKEND=pipeline
MINERU_OUTPUT_DIR=./parsed_output
MINERU_LANG=ch
```

---

## 🔄 更新环境

### 更新所有依赖

```bash
conda activate mineru
pip install --upgrade -r requirements.txt
```

### 更新单个包

```bash
conda activate mineru
pip install --upgrade mineru
```

### 导出当前环境

```bash
# 完整导出
conda env export -n mineru > mineru_environment_updated.yml

# 仅导出主要依赖
conda env export -n mineru --from-history > mineru_environment_history.yml
```

---

## 🧹 清理环境

### 完全删除环境

```bash
# 1. 停用环境
conda deactivate

# 2. 删除环境
conda env remove -n mineru

# 3. 清理缓存
conda clean --all
```

---

## 📚 相关资源

- **MinerU GitHub**: https://github.com/opendatalab/MinerU
- **MinerU 文档**: https://opendatalab.github.io/MinerU/
- **PyTorch 安装**: https://pytorch.org/get-started/locally/
- **CUDA 下载**: https://developer.nvidia.com/cuda-downloads

---

## 🤝 贡献

如果发现环境配置问题，欢迎提交 Issue 或 Pull Request。

---

## 📄 许可证

MIT License
