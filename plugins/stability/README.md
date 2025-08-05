# Stability 插件配置说明

本插件提供多种AI图像处理和视频生成功能，包括即梦绘图、去背景、图片编辑、修图、多图融合和视频生成等。

## 配置项说明

### 基本配置
- `api_key`: Stability AI的API密钥
- `robot_names`: 机器人名称列表，用于@消息识别
- `total_timeout`: 默认超时时间（秒），默认10秒

### 即梦AI绘图配置
- `jimeng_prefix`: 即梦绘图指令前缀，默认"jimeng"
- `jimeng_api_key`: 即梦AI的API密钥
- `jimeng_url`: 即梦AI的API地址
- `jimeng_timeout`: 即梦服务专用超时时间（秒），默认120秒
  - **注意**: 图片生成通常需要较长时间，建议设置为120秒或更长

### 去背景配置
- `rmbg_url`: 去背景服务的API地址
- `rmbg_prefix`: 去背景指令前缀，默认"去背景"

### 垫图配置 (OpenAI)
- `edit_image_prefix`: 垫图指令前缀，默认"垫图"
- `openai_image_api_key`: OpenAI图像API的密钥
- `openai_image_api_base`: OpenAI图像API的基础地址
- `image_model`: 使用的图像模型，默认"gpt-image-1"

### 修图配置 (Gemini)
- `inpaint_prefix`: 修图指令前缀，默认"修图"
- `google_api_key`: Google API密钥
- `gemini_model_name`: Gemini模型名称，默认"models/gemini-2.0-flash-exp"

### 多图编辑配置
- `blend_prefix`: 多图编辑开始指令，默认"/b"
- `end_prefix`: 多图编辑结束指令，默认"/e"

### FAL相关配置
- `fal_edit_prefix`: FAL图片编辑指令，默认"/p"
- `fal_img_prefix`: 图生视频指令前缀，默认"图生视频"
- `fal_text_prefix`: 文生视频指令前缀，默认"文生视频"
- `fal_api_key`: FAL API密钥
- `fal_edit_model`: FAL编辑模型，默认"flux-pro/kontext"
- `fal_kling_img_model`: Kling图生视频模型
- `fal_kling_text_model`: Kling文生视频模型

### Veo3视频生成配置
- `veo3_prefix`: Veo3视频生成指令前缀，默认"veo3"
- `veo3_api_key`: Veo3 API密钥
- `veo3_api_base`: Veo3 API基础地址
- `veo3_retry_times`: Veo3重试次数，默认30次

## 超时配置说明

由于不同服务的处理时间不同，插件提供了不同的超时配置：

- `total_timeout`: 大部分API的默认超时时间，建议10-30秒
- `jimeng_timeout`: 即梦绘图专用超时时间，建议120秒或更长

图片生成和视频生成通常需要较长时间，如果遇到超时问题，可以适当增加相应的超时配置值。

## 最近更新

### v2.1.1
- 新增 `jimeng_timeout` 配置项，解决即梦服务超时问题
- 默认jimeng超时时间从10秒增加到120秒
- 更新配置文件模板，包含所有支持的配置项
- 新增完整的配置文档说明
- 优化错误处理和日志输出 