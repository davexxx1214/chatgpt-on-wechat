import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from plugins.event import EventAction
from common.log import logger
from common.expired_dict import ExpiredDict
from common.tmp_dir import TmpDir
import time
import os
import requests
import uuid
import io
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
import base64
import tempfile
import asyncio
import aiohttp
import traceback
import http.client

# Gemini imports - 优先使用新版SDK (google.genai)，支持图像生成
GEMINI_NEW_SDK = False
GEMINI_AVAILABLE = False
try:
    from google import genai as genai_new
    from google.genai import types as genai_types_new
    GEMINI_NEW_SDK = True
    GEMINI_AVAILABLE = True
    logger.info("[stability] Google genai (新版SDK) 已加载，支持图像生成")
except ImportError:
    try:
        import google.generativeai as genai
        from google.generativeai import types as genai_types
        GEMINI_AVAILABLE = True
        logger.warning("[stability] 仅加载旧版SDK (google.generativeai)，图像生成功能可能受限")
    except ImportError:
        logger.warning("[stability] Google Generative AI not available, Gemini修图功能将不可用")

# Fal client imports
try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False
    logger.warning("[stability] fal_client not available, FAL相关功能将不可用")

# MediaInfo imports (for video duration)
try:
    from pymediainfo import MediaInfo
    MEDIAINFO_AVAILABLE = True
except ImportError:
    MEDIAINFO_AVAILABLE = False
    logger.warning("[stability] pymediainfo not available, 视频时长将使用默认值")

@plugins.register(
    name="stability",
    desire_priority=2,
    desc="A plugin with seedream v4, qwen, hunyuan, remove background, edit image, inpaint, multi-image blend, fal edit, video generation features",
    version="2.2.0",
    author="davexxx",
)

class stability(Plugin):
    def __init__(self):
        super().__init__()
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.config = super().load_config()
                if not self.config:
                    raise Exception("config.json not found")
            
            # 设置事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            
            # 基本配置
            self.api_key = self.config.get("api_key", "")
            self.robot_names = self.config.get("robot_names", [])
            self.total_timeout = self.config.get("total_timeout", 10)
            
            # jimeng专用超时配置 - 图片生成通常需要更长时间
            self.jimeng_timeout = self.config.get("jimeng_timeout", 120)
            
            # jimeng配置
            self.jimeng_prefix = self.config.get("jimeng_prefix", "jimeng")
            self.jimeng_api_key = self.config.get("jimeng_api_key", "")
            self.jimeng_url = self.config.get("jimeng_url", "")
            
            # qwen配置
            self.qwen_prefix = self.config.get("qwen_prefix", "qwen")
            
            # hunyuan配置
            self.hunyuan_prefix = self.config.get("hunyuan_prefix", "hunyuan")
            
            # 去背景配置
            self.rmbg_url = self.config.get("rmbg_url", "")
            self.rmbg_prefix = self.config.get("rmbg_prefix", "去背景")
            
            # 垫图配置 (OpenAI)
            self.edit_image_prefix = self.config.get("edit_image_prefix", "垫图")
            self.openai_image_api_key = self.config.get("openai_image_api_key", "")
            self.openai_image_api_base = self.config.get("openai_image_api_base", "")
            self.image_model = self.config.get("image_model", "gpt-image-1.5")
            
            # 修图配置 (Gemini)
            self.inpaint_prefix = self.config.get("inpaint_prefix", "修图")
            self.google_api_key = self.config.get("google_api_key", "")
            self.gemini_model_name = self.config.get("gemini_model_name", "models/gemini-2.0-flash-exp")
            
            # 多图编辑配置
            self.blend_prefix = self.config.get("blend_prefix", "/b")
            self.end_prefix = self.config.get("end_prefix", "/e")
            
            # FAL相关配置
            self.fal_edit_prefix = self.config.get("fal_edit_prefix", "/p")
            self.fal_img_prefix = self.config.get("fal_img_prefix", "图生视频")
            self.fal_text_prefix = self.config.get("fal_text_prefix", "文生视频")
            self.fal_img_hd_prefix = self.config.get("fal_img_hd_prefix", "图生高清视频")
            self.fal_text_hd_prefix = self.config.get("fal_text_hd_prefix", "文生高清视频")
            self.veo3_prefix = self.config.get("veo3_prefix", "veo3")
            
            self.fal_api_key = self.config.get("fal_api_key", "")
            self.fal_edit_model = self.config.get("fal_edit_model", "bytedance/seedream/v4/edit")
            self.fal_kling_img_model = self.config.get("fal_kling_img_model", "kling-video/v2/master/image-to-video")
            self.fal_kling_text_model = self.config.get("fal_kling_text_model", "kling-video/v2/master/text-to-video")
            self.veo3_retry_times = self.config.get("veo3_retry_times", 30)
            
            # veo3专用配置
            self.veo3_api_key = self.config.get("veo3_api_key", "")
            self.veo3_api_base = self.config.get("veo3_api_base", "")
            
            # 状态管理
            self.params_cache = ExpiredDict(500)
            self.waiting_edit_image = {}
            self.waiting_inpaint_image = {}
            self.waiting_blend = {}
            self.waiting_fal_edit = {}  # FAL编辑等待状态
            self.waiting_video = {}     # 视频生成等待状态
            self.image_msgid_cache = set()
            
            # 文件目录，用于MD5查找
            self.files_dir = "files"
            os.makedirs(self.files_dir, exist_ok=True)
            
            # 初始化Gemini客户端
            self.gemini_client = None
            self.gemini_new_client = None  # 新版SDK客户端
            if GEMINI_AVAILABLE and self.google_api_key:
                try:
                    if GEMINI_NEW_SDK:
                        # 使用新版SDK (google.genai) - 支持图像生成
                        self.gemini_new_client = genai_new.Client(api_key=self.google_api_key)
                        logger.info(f"[stability] Google Gemini 新版客户端初始化成功，模型: {self.gemini_model_name}")
                    else:
                        # 使用旧版SDK (google.generativeai)
                        genai.configure(api_key=self.google_api_key)
                        self.gemini_client = genai.GenerativeModel(self.gemini_model_name)
                        logger.info(f"[stability] Google Gemini 旧版客户端初始化成功，模型: {self.gemini_model_name}")
                except Exception as e:
                    logger.error(f"[stability] Failed to initialize Google Gemini client: {e}")
            elif not GEMINI_AVAILABLE:
                logger.warning("[stability] Google Generative AI library not available")
            else:
                logger.warning("[stability] Google API key not provided")
            
            # 检查FAL可用性
            if not FAL_AVAILABLE:
                logger.warning("[stability] fal_client not available, FAL相关功能将不可用")
            elif not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                logger.warning("[stability] FAL API key not configured, FAL相关功能将不可用")
            
            logger.info("[stability] inited successfully")
        except Exception as e:
            logger.warn(f"stability init failed: {e}")

    def is_at_message(self, message) -> bool:
        """检查是否是@消息，兼容不同平台"""
        try:
            # 兼容字典格式
            if isinstance(message, dict):
                if not message.get("IsGroup"):
                    return False
                content = message.get("Content", "")
            else:
                # 兼容消息对象
                if not getattr(message, 'is_group', False):
                    return False
                content = getattr(message, 'content', "") or getattr(message, 'Content', "")
            
            # 去掉"昵称: 换行"前缀
            content = re.sub(r"^[^@\n]+:\s*\n", "", content)
            for robot_name in self.robot_names:
                if re.match(f"^@{robot_name}[\\s]*", content):
                    return True
            return False
        except Exception as e:
            logger.warning(f"stability: 检查@消息失败: {e}")
            return False

    def get_waiting_key(self, msg):
        """获取等待状态的键，兼容不同平台的消息对象"""
        try:
            # 尝试ChatMessage对象的属性
            if hasattr(msg, 'from_user_id'):
                return msg.from_user_id
            elif hasattr(msg, 'actual_user_id'):
                return msg.actual_user_id
            
            # 尝试字典格式（微信等）
            if isinstance(msg, dict):
                if msg.get("IsGroup"):
                    return msg.get("FromWxid", msg.get("from_user_id", "unknown"))
                else:
                    return msg.get("SenderWxid", msg.get("from_user_id", "unknown"))
            
            # 兜底方案
            return getattr(msg, 'from_user_id', 'unknown')
        except Exception as e:
            logger.warning(f"stability: 获取等待键失败: {e}, 使用默认值")
            return 'unknown'

    def find_image_by_md5(self, md5: str) -> bytes:
        """通过MD5在本地文件目录中查找图片"""
        if not md5:
            logger.warning("stability: MD5为空，无法查找图片")
            return None
        
        common_extensions = ["jpeg", "jpg", "png", "gif", "webp"]
        for ext in common_extensions:
            file_path = os.path.join(self.files_dir, f"{md5}.{ext}")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as f:
                        image_data = f.read()
                    logger.info(f"stability: 通过MD5找到图片: {file_path}, 大小: {len(image_data)} 字节")
                    return image_data
                except Exception as e:
                    logger.error(f"stability: 读取图片文件失败 {file_path}: {e}")
                    return None
        
        logger.warning(f"stability: 未找到MD5为 {md5} 的图片文件")
        return None

    def safe_at_list(self, at_list, bot=None):
        """过滤at列表，确保不会@机器人自己"""
        if not at_list:
            return at_list
        
        # 获取机器人自己的ID
        bot_id = None
        if bot:
            bot_id = getattr(bot, 'wxid', None) or getattr(bot, 'user_id', None) or getattr(bot, 'bot_id', None)
        
        if not bot_id:
            return at_list
        
        # 过滤掉机器人自己的ID
        filtered_list = [user_id for user_id in at_list if user_id != bot_id]
        
        if len(filtered_list) != len(at_list):
            logger.info(f"stability: 已过滤掉机器人自己的ID: {bot_id}")
        
        return filtered_list

    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT, ContextType.IMAGE]:
            return
        
        msg: ChatMessage = e_context["context"]["msg"]
        user_id = msg.from_user_id
        content = context.content

        # 初始化用户缓存
        if user_id not in self.params_cache:
            self.params_cache[user_id] = {
                'rmbg_quota': 0,
                'edit_quota': 0,
                'inpaint_quota': 0
            }
            logger.debug(f'Added new user to params_cache. user id = {user_id}')

        if context.type == ContextType.TEXT:
            self._handle_text_message(e_context, content, user_id)
        elif context.type == ContextType.IMAGE:
            self._handle_image_message(e_context, user_id)

    def _handle_text_message(self, e_context: EventContext, content: str, user_id: str):
        """处理文本消息"""
        msg: ChatMessage = e_context["context"]["msg"]
        
        # 处理jimeng指令（使用Seedream v4）
        if content.startswith(self.jimeng_prefix):
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，Seedream v4画图服务当前不可用，请联系管理员检查FAL API配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            jimeng_prompt = content[len(self.jimeng_prefix):].strip()
            if not jimeng_prompt:
                tip = f"💡欢迎使用Seedream v4画图，指令格式为:\n\n{self.jimeng_prefix} + 空格 + 主题(支持中文)\n例如：{self.jimeng_prefix} 一只可爱的猫"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            logger.info(f"seedream_v4_prompt = : {jimeng_prompt}")
            self._call_jimeng_service(jimeng_prompt, e_context)
            return

        # 处理qwen指令
        if content.startswith(self.qwen_prefix):
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，qwen画图服务当前不可用，请联系管理员检查FAL API配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            pattern = self.qwen_prefix + r"\s(.+)"
            match = re.match(pattern, content)
            if match:
                qwen_prompt = content[len(self.qwen_prefix):].strip()
                logger.info(f"qwen_prompt = : {qwen_prompt}")
                self._call_qwen_service(qwen_prompt, e_context)
            else:
                tip = f"💡欢迎使用qwen画图，指令格式为:\n\n{self.qwen_prefix}+ 空格 + 主题(支持中文)\n例如：{self.qwen_prefix} 画一只猫"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            return

        # 处理hunyuan指令
        if content.startswith(self.hunyuan_prefix):
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，hunyuan画图服务当前不可用，请联系管理员检查FAL API配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            pattern = self.hunyuan_prefix + r"\s(.+)"
            match = re.match(pattern, content)
            if match:
                hunyuan_prompt = content[len(self.hunyuan_prefix):].strip()
                logger.info(f"hunyuan_prompt = : {hunyuan_prompt}")
                self._call_hunyuan_service(hunyuan_prompt, e_context)
            else:
                tip = f"💡欢迎使用hunyuan画图，指令格式为:\n\n{self.hunyuan_prefix}+ 空格 + 主题(支持中文)\n例如：{self.hunyuan_prefix} 一只可爱的猫咪"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            return

        # 处理去背景指令
        if content.startswith(self.rmbg_prefix):
            self.params_cache[user_id]['rmbg_quota'] = 1
            tip = f"💡已经开启图片消除背景服务，请再发送一张图片进行处理"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理垫图指令
        if content.startswith(self.edit_image_prefix):
            user_prompt = content[len(self.edit_image_prefix):].strip()
            if not user_prompt:
                user_prompt = "请描述您要编辑图片的内容。"
            
            key = self.get_waiting_key(msg)
            self.waiting_edit_image[key] = {
                "timestamp": time.time(),
                "prompt": user_prompt
            }
            # 清除其他状态
            self.waiting_inpaint_image.pop(key, None)
            self.waiting_blend.pop(key, None)
            
            tip = f"💡已开启图片编辑模式({self.image_model})，您接下来第一张图片会进行编辑。\n当前的提示词为：\n{user_prompt}"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理修图指令
        if content.startswith(self.inpaint_prefix):
            if not self.gemini_client:
                tip = "抱歉，Gemini修图服务当前不可用，请联系管理员检查配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            user_prompt = content[len(self.inpaint_prefix):].strip()
            if not user_prompt:
                user_prompt = "请描述您要对图片进行的修改。"
            
            key = self.get_waiting_key(msg)
            self.waiting_inpaint_image[key] = {
                "timestamp": time.time(),
                "prompt": user_prompt
            }
            # 清除其他状态
            self.waiting_edit_image.pop(key, None)
            self.waiting_blend.pop(key, None)
            
            tip = f"💡已开启Gemini修图模式({self.gemini_model_name})，您接下来第一张图片会进行修图。\n当前的提示词为：\n{user_prompt}"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理多图编辑开始指令
        if content.startswith(self.blend_prefix):
            user_prompt = content[len(self.blend_prefix):].strip()
            if not user_prompt:
                tip = f"💡欢迎使用多图编辑功能，指令格式为:\n\n{self.blend_prefix} + 空格 + 图片描述\n\n📝 示例：\n{self.blend_prefix} 把两只猫融合在一起\n{self.blend_prefix} 将第一张图的人物放到第二张图的背景中"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            key = self.get_waiting_key(msg)
            self.waiting_blend[key] = {
                "timestamp": time.time(),
                "prompt": user_prompt,
                "images": []
            }
            # 清除其他状态
            self.waiting_edit_image.pop(key, None)
            self.waiting_inpaint_image.pop(key, None)
            
            tip = f"✨ 多图编辑模式已开启（使用FAL seedream/v4/edit）\n✏ 请发送至少2张图片，然后发送 '{self.end_prefix}' 结束上传并开始处理。\n当前提示词：{user_prompt}"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理多图编辑结束指令
        if content.startswith(self.end_prefix):
            # 立即设置事件阻断，防止指令继续传播
            e_context.action = EventAction.BREAK_PASS
            
            key = self.get_waiting_key(msg)
            waiting_blend_info = self.waiting_blend.get(key)
            if waiting_blend_info:
                images = waiting_blend_info.get("images", [])
                prompt = waiting_blend_info.get("prompt", "多图编辑")
                if len(images) >= 2:
                    logger.info(f"stability: 开始多图编辑，用户 {key}，{len(images)} 张图片")
                    self._handle_blend_service_async(images, prompt, e_context)
                    self.waiting_blend.pop(key, None)
                else:
                    tip = f"✨ 多图编辑模式\n✏ 您需要发送至少2张图片才能开始多图编辑。当前已发送 {len(images)} 张。请继续发送图片或重新开始。"
                    reply = Reply(type=ReplyType.TEXT, content=tip)
                    e_context["reply"] = reply
            return

        # 处理FAL图片编辑指令 (/p)
        if content.startswith(self.fal_edit_prefix):
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，FAL图片编辑服务当前不可用，请联系管理员检查配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            user_prompt = content[len(self.fal_edit_prefix):].strip()
            if not user_prompt:
                tip = f"欢迎使用seedream/v4/edit图片编辑！\n正确的编辑指令是：{self.fal_edit_prefix} + 要编辑的提示词\n\n例如：\n{self.fal_edit_prefix} 给模特穿上衣服和鞋子\n{self.fal_edit_prefix} 把背景改成蓝色"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            key = self.get_waiting_key(msg)
            self.waiting_fal_edit[key] = {
                "timestamp": time.time(),
                "prompt": user_prompt,
                "type": "fal_edit"
            }
            # 清除其他状态
            self.waiting_edit_image.pop(key, None)
            self.waiting_inpaint_image.pop(key, None)
            self.waiting_blend.pop(key, None)
            self.waiting_video.pop(key, None)
            
            tip = f"💡已开启seedream/v4/edit图片编辑模式，您接下来第一张图片会进行编辑。\n当前的提示词为：\n{user_prompt}"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理图生视频指令
        if content.startswith(self.fal_img_prefix):
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，图生视频服务当前不可用，请联系管理员检查配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            user_prompt = content[len(self.fal_img_prefix):].strip()
            if not user_prompt:
                tip = f"欢迎使用Kling2.6图生视频（10秒）！\n正确的指令格式是：{self.fal_img_prefix} + 空格 + 视频描述提示词\n\n例如：\n{self.fal_img_prefix} 让猫咪在草地上奔跑\n{self.fal_img_prefix} 人物向前走动，背景模糊"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            key = self.get_waiting_key(msg)
            self.waiting_video[key] = {
                "timestamp": time.time(),
                "prompt": user_prompt,
                "type": "img2video"
            }
            # 清除其他状态
            self.waiting_edit_image.pop(key, None)
            self.waiting_inpaint_image.pop(key, None)
            self.waiting_blend.pop(key, None)
            self.waiting_fal_edit.pop(key, None)
            
            tip = f"💡已开启Kling2.6图生视频模式（10秒），您接下来第一张图片会生成视频。\n当前的提示词为：\n{user_prompt}"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理文生视频指令
        if content.startswith(self.fal_text_prefix):
            # 立即设置事件阻断，防止指令继续传播
            e_context.action = EventAction.BREAK_PASS
            
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，文生视频服务当前不可用，请联系管理员检查配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                return

            user_prompt = content[len(self.fal_text_prefix):].strip()
            if not user_prompt:
                tip = f"💡欢迎使用Kling2.6文生视频（10秒），指令格式为:\n\n{self.fal_text_prefix}+ 空格 + 视频描述\n例如：{self.fal_text_prefix} 一只猫在草地上奔跑"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                return
            
            tip = "💡已开启Kling2.6文生视频模式（10秒），将根据您的描述生成视频。"
            self._send_reply(tip, e_context)
            self._handle_text2video_async(user_prompt, e_context)
            return

        # 处理图生高清视频指令
        if content.startswith(self.fal_img_hd_prefix):
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，图生高清视频服务当前不可用，请联系管理员检查配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            user_prompt = content[len(self.fal_img_hd_prefix):].strip()
            if not user_prompt:
                tip = f"欢迎使用Sora2-Pro图生高清视频（25秒）！\n正确的指令格式是：{self.fal_img_hd_prefix} + 空格 + 视频描述提示词\n\n例如：\n{self.fal_img_hd_prefix} 让画面动起来，云朵飘动\n{self.fal_img_hd_prefix} 人物转身微笑，镜头推进"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            key = self.get_waiting_key(msg)
            self.waiting_video[key] = {
                "timestamp": time.time(),
                "prompt": user_prompt,
                "type": "img2video_hd"
            }
            # 清除其他状态
            self.waiting_edit_image.pop(key, None)
            self.waiting_inpaint_image.pop(key, None)
            self.waiting_blend.pop(key, None)
            self.waiting_fal_edit.pop(key, None)
            
            tip = f"💡已开启Sora2-Pro图生高清视频模式（25秒），您接下来第一张图片会生成高清视频。\n当前的提示词为：\n{user_prompt}"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理文生高清视频指令
        if content.startswith(self.fal_text_hd_prefix):
            # 立即设置事件阻断，防止指令继续传播
            e_context.action = EventAction.BREAK_PASS
            
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                tip = "抱歉，文生高清视频服务当前不可用，请联系管理员检查配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                return

            user_prompt = content[len(self.fal_text_hd_prefix):].strip()
            if not user_prompt:
                tip = f"💡欢迎使用Sora2-Pro文生高清视频（25秒），指令格式为:\n\n{self.fal_text_hd_prefix}+ 空格 + 视频描述\n例如：{self.fal_text_hd_prefix} 一只猫在草地上奔跑"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                return
            
            tip = "💡已开启Sora2-Pro文生高清视频模式（25秒），将根据您的描述生成高清视频。"
            self._send_reply(tip, e_context)
            self._handle_text2video_hd_async(user_prompt, e_context)
            return

        # 处理测试视频指令
        if content == "测试视频":
            # 立即设置事件阻断，防止指令继续传播
            e_context.action = EventAction.BREAK_PASS
            
            # 使用插件目录下的tmp/test.mp4
            tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
            test_video_path = os.path.join(tmp_dir, 'test.mp4')
            
            logger.info(f"[测试视频] 检查测试视频文件路径: {test_video_path}")
            
            if os.path.exists(test_video_path):
                tip = "🎬 开始发送测试视频..."
                self._send_reply(tip, e_context)
                self._send_test_video(test_video_path, e_context)
            else:
                tip = f"❌ 测试视频文件不存在: {test_video_path}"
                self._send_reply(tip, e_context)
            return

        # 处理veo3图生视频指令
        if content.startswith(self.veo3_prefix):
            if not self.veo3_api_key:
                tip = "抱歉，veo3图生视频服务当前不可用，请联系管理员检查veo3 API配置。"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

            user_prompt = content[len(self.veo3_prefix):].strip()
            if not user_prompt:
                tip = f"欢迎使用veo3图生视频！\n正确的指令格式是：{self.veo3_prefix} + 空格 + 视频描述提示词\n\n例如：\n{self.veo3_prefix} 图像中的人物跑起来\n{self.veo3_prefix} 让画面动起来，背景飘雪"
                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            key = self.get_waiting_key(msg)
            self.waiting_video[key] = {
                "timestamp": time.time(),
                "prompt": user_prompt,
                "type": "veo3_img2video"
            }
            # 清除其他状态
            self.waiting_edit_image.pop(key, None)
            self.waiting_inpaint_image.pop(key, None)
            self.waiting_blend.pop(key, None)
            self.waiting_fal_edit.pop(key, None)
            
            tip = f"💡已开启veo3图生视频模式（8秒），您接下来第一张图片会生成视频。\n当前的提示词为：\n{user_prompt}"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

    def _handle_image_message(self, e_context: EventContext, user_id: str):
        """处理图片消息"""
        msg: ChatMessage = e_context["context"]["msg"]
        context = e_context["context"]
        
        # 检查是否有待处理的任务
        key = self.get_waiting_key(msg)
        has_rmbg_task = self.params_cache[user_id]['rmbg_quota'] > 0
        has_edit_task = key in self.waiting_edit_image
        has_inpaint_task = key in self.waiting_inpaint_image
        has_blend_task = key in self.waiting_blend
        has_fal_edit_task = key in self.waiting_fal_edit
        has_video_task = key in self.waiting_video and self.waiting_video[key].get("type") in ["img2video", "img2video_hd", "veo3_img2video"]
        
        if not (has_rmbg_task or has_edit_task or has_inpaint_task or has_blend_task or has_fal_edit_task or has_video_task):
            logger.debug("stability: 当前用户无待处理任务，跳过")
            return

        logger.info("stability: 开始处理图片")
        try:
            # 兼容不同平台的图片准备方式
            if hasattr(context.get("msg"), 'prepare'):
                context.get("msg").prepare()
            image_path = context.content
            logger.info(f"stability: 获取到图片路径 {image_path}")
        except Exception as e:
            logger.error(f"stability: 图片准备失败: {e}")
            self._send_reply("图片处理失败，请重试", e_context)
            return

        # 处理不同类型的任务
        delete_file_immediately = True  # 标记是否立即删除文件
        
        if has_rmbg_task:
            self.params_cache[user_id]['rmbg_quota'] = 0
            self._call_rmbg_service(image_path, user_id, e_context)
        elif has_edit_task:
            waiting_info = self.waiting_edit_image[key]
            prompt = waiting_info.get("prompt", "请描述您要编辑图片的内容。")
            self._handle_edit_image_async(image_path, prompt, e_context)
            self.waiting_edit_image.pop(key, None)
            delete_file_immediately = False  # 异步任务会处理文件删除
        elif has_inpaint_task:
            waiting_info = self.waiting_inpaint_image[key]
            prompt = waiting_info.get("prompt", "请描述您要对图片进行的修改。")
            self._handle_inpaint_image_async(image_path, prompt, e_context)
            self.waiting_inpaint_image.pop(key, None)
            delete_file_immediately = False  # 异步任务会处理文件删除
        elif has_fal_edit_task:
            waiting_info = self.waiting_fal_edit[key]
            prompt = waiting_info.get("prompt", "编辑图片")
            self._handle_fal_edit_async(image_path, prompt, e_context)
            self.waiting_fal_edit.pop(key, None)
            delete_file_immediately = False  # 异步任务会处理文件删除
        elif has_video_task:
            waiting_info = self.waiting_video[key]
            prompt = waiting_info.get("prompt", "")
            video_type = waiting_info.get("type", "img2video")
            if video_type == "img2video_hd":
                self._handle_img2video_hd_async(image_path, prompt, e_context)
            elif video_type == "veo3_img2video":
                self._handle_veo3_img2video_async(image_path, prompt, e_context)
            else:
                self._handle_img2video_async(image_path, prompt, e_context)
            self.waiting_video.pop(key, None)
            delete_file_immediately = False  # 异步任务会处理文件删除
        elif has_blend_task:
            # 保存图片到临时文件用于多图编辑
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                with open(image_path, 'rb') as img_file:
                    tmp_file.write(img_file.read())
                tmp_file_path = tmp_file.name
            
            self.waiting_blend[key]["images"].append(tmp_file_path)
            num_images = len(self.waiting_blend[key]["images"])
            tip = f"✅ 已收到第 {num_images} 张图片。\n请继续发送图片，或发送 '{self.end_prefix}' 开始多图编辑。"
            reply = Reply(type=ReplyType.TEXT, content=tip)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

        # 只有同步任务才立即删除文件，异步任务由任务本身负责删除
        if delete_file_immediately:
            try:
                os.remove(image_path)
                logger.info(f"文件 {image_path} 已删除")
            except Exception as e:
                logger.error(f"删除文件失败: {e}")

    def _call_jimeng_service(self, jimeng_prompt, e_context):
        """调用Bytedance Seedream v4文生图服务"""
        logger.info(f"calling seedream v4 service with prompt: {jimeng_prompt}")

        tip = f'欢迎使用Seedream v4画图.\n💡图片正在生成中，请耐心等待。\n当前使用的提示词为：\n{jimeng_prompt}'
        self._send_reply(tip, e_context)

        try:
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                reply = Reply(ReplyType.TEXT, "抱歉，Seedream v4画图服务当前不可用，请联系管理员检查FAL API配置。")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            # 使用fal_client调用seedream v4模型
            client = fal_client.SyncClient(key=self.fal_api_key)
            
            # 构建请求参数
            request_data = {
                "prompt": jimeng_prompt,
                "image_size": {
                    "height": 2048,
                    "width": 2048
                },
                "num_images": 1,
                "max_images": 1,
                "enable_safety_checker": False
            }
            
            # 调用fal-ai/bytedance/seedream/v4/text-to-image模型
            result = client.subscribe(
                "fal-ai/bytedance/seedream/v4/text-to-image",
                arguments=request_data,
                with_logs=True
            )
            
            logger.info(f"[seedream-v4] API响应: {result}")
            
            # 处理返回结果
            if isinstance(result, dict) and "images" in result:
                images = result.get("images", [])
                if images and len(images) > 0:
                    # 遍历所有生成的图片URL并发送
                    for image_info in images:
                        url = image_info.get('url')
                        if url and url.startswith("http"):
                            logger.info(f"seedream v4 image url = {url}")
                            self._send_reply(url, e_context, ReplyType.IMAGE_URL)
                    
                    reply = Reply(ReplyType.TEXT, "Seedream v4图片生成完毕。")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                else:
                    reply = Reply(ReplyType.TEXT, "Seedream v4生成图片失败，未获取到图片URL")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
            else:
                logger.error(f"[seedream-v4] API响应格式不正确: {result}")
                reply = Reply(ReplyType.TEXT, f"Seedream v4服务响应格式错误: {str(result)}")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                
        except Exception as e:
            logger.error(f"seedream v4 service exception: {e}")
            reply = Reply(ReplyType.TEXT, f"Seedream v4服务出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def _call_qwen_service(self, qwen_prompt, e_context):
        """调用qwen画图服务"""
        logger.info(f"calling qwen service with prompt: {qwen_prompt}")

        tip = f'欢迎使用qwen画图.\n💡图片正在生成中，请耐心等待。\n当前使用的提示词为：\n{qwen_prompt}'
        self._send_reply(tip, e_context)

        try:
            # 使用fal_client调用qwen-image模型
            client = fal_client.SyncClient(key=self.fal_api_key)
            
            # 构建请求参数
            request_data = {
                "prompt": qwen_prompt,
                "image_size": "landscape_4_3",
                "num_inference_steps": 30,
                "guidance_scale": 2.5,
                "num_images": 1,
                "enable_safety_checker": False,
                "output_format": "png",
                "negative_prompt": "blurry, ugly"
            }
            
            # 调用fal-ai/qwen-image模型
            result = client.subscribe(
                "fal-ai/qwen-image",
                arguments=request_data,
                with_logs=True
            )
            
            logger.info(f"[qwen] API响应: {result}")
            
            # 处理返回结果
            if isinstance(result, dict) and "images" in result:
                images = result.get("images", [])
                if images and len(images) > 0:
                    # 遍历所有生成的图片URL并发送
                    for image_info in images:
                        url = image_info.get('url')
                        if url and url.startswith("http"):
                            logger.info(f"qwen image url = {url}")
                            self._send_reply(url, e_context, ReplyType.IMAGE_URL)
                    
                    reply = Reply(ReplyType.TEXT, "qwen图片生成完毕。")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                else:
                    reply = Reply(ReplyType.TEXT, "qwen生成图片失败，未获取到图片URL")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
            else:
                logger.error(f"[qwen] API响应格式不正确: {result}")
                reply = Reply(ReplyType.TEXT, f"qwen服务响应格式错误: {str(result)}")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                
        except Exception as e:
            logger.error(f"qwen service exception: {e}")
            reply = Reply(ReplyType.TEXT, f"qwen服务出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def _call_hunyuan_service(self, hunyuan_prompt, e_context):
        """调用hunyuan画图服务"""
        logger.info(f"calling hunyuan service with prompt: {hunyuan_prompt}")

        tip = f'欢迎使用hunyuan画图.\n💡图片正在生成中，请耐心等待。\n当前使用的提示词为：\n{hunyuan_prompt}'
        self._send_reply(tip, e_context)

        try:
            # 使用fal_client调用hunyuan-image模型
            client = fal_client.SyncClient(key=self.fal_api_key)
            
            # 构建请求参数
            request_data = {
                "prompt": hunyuan_prompt,
                "image_size": "square_hd",
                "num_inference_steps": 28,
                "guidance_scale": 7.5,
                "num_images": 1,
                "enable_safety_checker": False,
                "output_format": "png",
                "enable_prompt_expansion": True
            }
            
            # 调用fal-ai/hunyuan-image/v3/text-to-image模型
            result = client.subscribe(
                "fal-ai/hunyuan-image/v3/text-to-image",
                arguments=request_data,
                with_logs=True
            )
            
            logger.info(f"[hunyuan] API响应: {result}")
            
            # 处理返回结果
            if isinstance(result, dict) and "images" in result:
                images = result.get("images", [])
                if images and len(images) > 0:
                    # 遍历所有生成的图片URL并发送
                    for image_info in images:
                        url = image_info.get('url')
                        if url and url.startswith("http"):
                            logger.info(f"hunyuan image url = {url}")
                            self._send_reply(url, e_context, ReplyType.IMAGE_URL)
                    
                    reply = Reply(ReplyType.TEXT, "hunyuan图片生成完毕。")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                else:
                    reply = Reply(ReplyType.TEXT, "hunyuan生成图片失败，未获取到图片URL")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
            else:
                logger.error(f"[hunyuan] API响应格式不正确: {result}")
                reply = Reply(ReplyType.TEXT, f"hunyuan服务响应格式错误: {str(result)}")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                
        except Exception as e:
            logger.error(f"hunyuan service exception: {e}")
            reply = Reply(ReplyType.TEXT, f"hunyuan服务出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def _call_rmbg_service(self, image_path, user_id, e_context):
        """调用去背景服务"""
        logger.info(f"calling remove bg service")

        try:
            response = requests.post(
                f"{self.rmbg_url}",
                headers={
                    "accept": "image/*",
                    "Authorization": f"Bearer {self.api_key}"
                },
                files={
                    "image": open(image_path, "rb")
                },
                data={
                    "output_format": "png"
                },
                timeout=self.total_timeout
            )

            if response.status_code == 200:
                # 转换为base64格式发送，兼容飞书等平台
                image_data = response.content
                image_b64 = base64.b64encode(image_data).decode()
                data_url = f"data:image/png;base64,{image_b64}"
                
                self._send_reply(data_url, e_context, ReplyType.IMAGE_URL)
            else:
                reply = Reply(ReplyType.TEXT, "服务暂不可用,可能是图片分辨率太高(仅支持分辨率小于2048*2048的图片)")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        except Exception as e:
            logger.error(f"rmbg service exception: {e}")
            reply = Reply(ReplyType.TEXT, f"去背景服务出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def _handle_edit_image_async(self, image_path, prompt, e_context):
        """异步处理垫图请求"""
        tip = f"🎨 gpt-image-1.5垫图请求已进入队列，预计需要30-150秒完成。请稍候...\n提示词：{prompt}"
        self._send_reply(tip, e_context)
        
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_edit_image_sync, args=(image_path, prompt, e_context))
        thread.start()

    def _handle_edit_image_sync(self, image_path, prompt, e_context):
        """同步处理垫图请求"""
        try:
            # 构建API请求
            url = f"{self.openai_image_api_base}/images/edits"
            headers = {
                "Authorization": f"Bearer {self.openai_image_api_key}"
            }
            
            with open(image_path, 'rb') as img_file:
                files = {
                    'image': img_file,
                    'model': (None, self.image_model),
                    'prompt': (None, prompt)
                }
                
                response = requests.post(url, headers=headers, files=files, timeout=1200)
                
                if response.status_code != 200:
                    error_message = self._parse_api_error(response)
                    self._send_reply(error_message, e_context)
                    return
                
                result = response.json()
                if "data" in result and len(result["data"]) > 0:
                    image_data = result["data"][0]
                    if "b64_json" in image_data and image_data["b64_json"]:
                        image_b64 = image_data["b64_json"]
                        # 创建data URL格式，兼容飞书等平台
                        data_url = f"data:image/png;base64,{image_b64}"
                        
                        # 发送完成提示
                        self._send_reply("🖼️ 您的图片已编辑完成！", e_context)
                        
                        # 直接发送图片
                        self._send_reply(data_url, e_context, ReplyType.IMAGE_URL)
                    else:
                        self._send_reply("图片编辑失败，API没有返回图片数据", e_context)
                else:
                    self._send_reply("图片编辑失败，API返回格式不正确", e_context)
        except Exception as e:
            logger.error(f"edit image service exception: {e}")
            self._send_reply(f"图片编辑服务出错: {str(e)}", e_context)
        finally:
            # 删除原始图片文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"原始图片文件已删除: {image_path}")
            except Exception as e:
                logger.error(f"删除原始图片文件失败: {image_path}, error: {e}")

    def _handle_inpaint_image_async(self, image_path, prompt, e_context):
        """异步处理Gemini修图请求"""
        # 检查客户端可用性
        if not GEMINI_NEW_SDK and not self.gemini_client:
            self._send_reply("Gemini修图服务当前不可用", e_context)
            return
        if GEMINI_NEW_SDK and not self.gemini_new_client:
            self._send_reply("Gemini修图服务当前不可用", e_context)
            return
            
        tip = f"🎨 Gemini修图服务({self.gemini_model_name})请求已提交，请稍候...\n提示词：{prompt}"
        self._send_reply(tip, e_context)
        
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_inpaint_image_sync, args=(image_path, prompt, e_context))
        thread.start()

    def _handle_inpaint_image_sync(self, image_path, prompt, e_context):
        """同步处理Gemini修图请求"""
        try:
            # 加载图片
            with open(image_path, 'rb') as img_file:
                image_bytes = img_file.read()
            
            pil_image = Image.open(io.BytesIO(image_bytes))
            
            # 根据SDK版本选择不同的调用方式
            if GEMINI_NEW_SDK and self.gemini_new_client:
                # 使用新版SDK (google.genai) - 支持图像生成
                logger.info(f"[Gemini修图] 使用新版SDK，模型: {self.gemini_model_name}")
                response = self.gemini_new_client.models.generate_content(
                    model=self.gemini_model_name,
                    contents=[prompt, pil_image],
                    config=genai_types_new.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"]
                    )
                )
            else:
                # 使用旧版SDK (google.generativeai)
                logger.info(f"[Gemini修图] 使用旧版SDK，模型: {self.gemini_model_name}")
                safety_settings = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                generation_config = {
                    "response_modalities": ["TEXT", "IMAGE"]
                }
                response = self.gemini_client.generate_content(
                    contents=[prompt, pil_image],
                    safety_settings=safety_settings,
                    generation_config=generation_config
                )
            
            # 处理安全检查
            if (hasattr(response, 'candidates') and response.candidates and
                hasattr(response.candidates[0], 'finish_reason')):
                finish_reason_str = str(response.candidates[0].finish_reason)
                if 'SAFETY' in finish_reason_str.upper():
                    self._send_reply("由于图像安全策略限制，无法处理该图像。请尝试使用其他图片或修改提示词。", e_context)
                    return

            # 处理响应 - 支持多张图片
            edited_images = []  # 存储所有图片数据
            text_parts_content = []

            if (hasattr(response, 'candidates') and response.candidates and
                response.candidates[0].content and
                hasattr(response.candidates[0].content, 'parts') and
                response.candidates[0].content.parts):
                
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts_content.append(part.text)
                    
                    # 新版SDK的图片数据格式
                    if hasattr(part, 'inline_data') and part.inline_data:
                        if hasattr(part.inline_data, 'data') and part.inline_data.data:
                            img_data = part.inline_data.data
                            # 新版SDK可能返回bytes或base64字符串
                            if isinstance(img_data, str):
                                img_data = base64.b64decode(img_data)
                            edited_images.append(img_data)

            # 发送响应
            sent_something = False

            # 发送文本部分
            if text_parts_content:
                full_text_response = "\n".join(text_parts_content).strip()
                self._send_reply(full_text_response, e_context)
                sent_something = True

            # 发送图片部分 - 支持多张图片
            if edited_images:
                logger.info(f"[Gemini修图] 收到 {len(edited_images)} 张图片")
                
                # 如果有多张图片，先发送提示信息
                if len(edited_images) > 1:
                    tip = f"🖼️ Gemini修图完成！共生成了 {len(edited_images)} 张图片，正在依次发送..."
                    self._send_reply(tip, e_context)
                
                # 依次发送每张图片
                for i, img_bytes in enumerate(edited_images, 1):
                    try:
                        # 转换为base64格式发送
                        image_b64 = base64.b64encode(img_bytes).decode()
                        data_url = f"data:image/png;base64,{image_b64}"
                        
                        # 如果是多张图片，为每张图片添加序号提示
                        if len(edited_images) > 1:
                            image_tip = f"📷 图片 {i}/{len(edited_images)}"
                            self._send_reply(image_tip, e_context)
                        
                        self._send_reply(data_url, e_context, ReplyType.IMAGE_URL)
                        logger.info(f"[Gemini修图] 第 {i} 张图片发送成功")
                        
                        # 在多张图片之间添加短暂延迟，避免消息过于密集
                        if i < len(edited_images):
                            time.sleep(0.5)
                            
                    except Exception as e:
                        logger.error(f"[Gemini修图] 发送第 {i} 张图片失败: {e}")
                        self._send_reply(f"⚠️ 第 {i} 张图片发送失败: {str(e)}", e_context)
                
                sent_something = True
                
                # 发送完成提示
                if len(edited_images) > 1:
                    completion_tip = f"✅ 所有 {len(edited_images)} 张图片已发送完成！"
                    self._send_reply(completion_tip, e_context)
            else:
                logger.warning(f"[Gemini修图] 未收到图片，模型可能不支持图像生成。请检查模型名称是否正确。当前模型: {self.gemini_model_name}")

            if not sent_something:
                self._send_reply(f"Gemini修图失败，API没有返回图片。\n当前模型 {self.gemini_model_name} 可能不支持图像生成。\n建议使用支持图像生成的模型，如：gemini-2.0-flash-exp 或 gemini-2.5-flash-image-preview", e_context)

        except Exception as e:
            logger.error(f"Gemini inpaint service exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._send_reply(f"Gemini修图服务出错: {str(e)}", e_context)
        finally:
            # 删除原始图片文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"原始图片文件已删除: {image_path}")
            except Exception as e:
                logger.error(f"删除原始图片文件失败: {image_path}, error: {e}")

    def _handle_blend_service_async(self, image_paths, prompt, e_context):
        """异步处理多图编辑请求"""
        tip = f"🎨 FAL多图编辑请求已进入队列，请稍候...\n提示词：{prompt}"
        self._send_reply(tip, e_context)
        
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_blend_service_sync, args=(image_paths, prompt, e_context))
        thread.start()

    def _handle_blend_service_sync(self, image_paths, prompt, e_context):
        """使用FAL seedream/v4/edit进行多图编辑"""
        try:
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                self._send_reply("FAL多图编辑服务当前不可用，请检查FAL API配置", e_context)
                return

            # 上传所有图片到FAL
            image_urls = []
            client = fal_client.SyncClient(key=self.fal_api_key)
            
            for i, image_path in enumerate(image_paths):
                try:
                    # 上传图片并获取URL
                    image_url = client.upload_file(image_path)
                    if not image_url:
                        self._send_reply(f"图片 {i+1} 上传失败，多图编辑终止", e_context)
                        return
                    
                    image_urls.append(image_url)
                    logger.info(f"上传图片 {i+1}/{len(image_paths)}: {image_url}")
                except Exception as e:
                    logger.error(f"上传图片失败 {image_path}: {e}")
                    self._send_reply(f"上传图片 {i+1} 失败，多图编辑终止", e_context)
                    return

            logger.info(f"开始FAL多图编辑，图片数量: {len(image_urls)}, 提示词: {prompt}")

            # 调用fal-ai/bytedance/seedream/v4/edit进行多图编辑
            result = client.subscribe(
                "fal-ai/bytedance/seedream/v4/edit",
                arguments={
                    "prompt": prompt,
                    "image_urls": image_urls,
                    "image_size": {
                        "height": 1280,
                        "width": 1280
                    },
                    "num_images": 1,
                    "max_images": 1,
                    "enable_safety_checker": False
                },
                with_logs=True
            )
            
            logger.info(f"[FAL多图编辑] API响应: {result}")
            
            # 处理返回结果
            edited_image_urls = []
            if isinstance(result, dict):
                # 检查多种可能的返回格式
                if "images" in result and isinstance(result["images"], list) and len(result["images"]) > 0:
                    for img_item in result["images"]:
                        if isinstance(img_item, dict) and "url" in img_item:
                            edited_image_urls.append(img_item["url"])
                        elif isinstance(img_item, str) and img_item.startswith("http"):
                            edited_image_urls.append(img_item)
                elif "image" in result and isinstance(result["image"], dict) and "url" in result["image"]:
                    edited_image_urls.append(result["image"]["url"])
                elif "url" in result and result["url"].startswith("http"):
                    edited_image_urls.append(result["url"])

            # 发送编辑后的图片
            if edited_image_urls:
                logger.info(f"[FAL多图编辑] 收到 {len(edited_image_urls)} 张图片")
                
                # 如果有多张图片，先发送提示信息
                if len(edited_image_urls) > 1:
                    tip = f"🖼️ FAL多图编辑完成！共生成了 {len(edited_image_urls)} 张图片，正在依次发送..."
                    self._send_reply(tip, e_context)
                else:
                    self._send_reply("🖼️ 您的多图编辑已完成！", e_context)
                
                # 依次下载并发送每张图片
                for i, image_url in enumerate(edited_image_urls, 1):
                    try:
                        # 如果是多张图片，为每张图片添加序号提示
                        if len(edited_image_urls) > 1:
                            image_tip = f"📷 图片 {i}/{len(edited_image_urls)}"
                            self._send_reply(image_tip, e_context)
                        
                        # 下载并发送图片
                        self._download_and_send_image(image_url, e_context, f"多图编辑-图片{i}")
                        logger.info(f"[FAL多图编辑] 第 {i} 张图片发送成功")
                        
                        # 在多张图片之间添加短暂延迟，避免消息过于密集
                        if i < len(edited_image_urls):
                            time.sleep(0.5)
                            
                    except Exception as e:
                        logger.error(f"[FAL多图编辑] 发送第 {i} 张图片失败: {e}")
                        self._send_reply(f"⚠️ 第 {i} 张图片发送失败: {str(e)}", e_context)
                
                # 发送完成提示
                if len(edited_image_urls) > 1:
                    completion_tip = f"✅ 所有 {len(edited_image_urls)} 张图片已发送完成！"
                    self._send_reply(completion_tip, e_context)
            else:
                logger.error(f"[FAL多图编辑] 未能从API响应中获取图片URL，完整响应: {result}")
                self._send_reply("FAL多图编辑失败，API没有返回图片URL。", e_context)

        except Exception as e:
            logger.error(f"FAL多图编辑服务异常: {e}")
            self._send_reply(f"FAL多图编辑服务出错: {str(e)}", e_context)
        finally:
            # 清理临时图片文件
            for path in image_paths:
                try:
                    os.remove(path)
                    logger.info(f"多图编辑cleanup，文件 {path} 已删除")
                except Exception as e:
                    logger.error(f"多图编辑cleanup，删除文件 {path} 失败: {e}")

    def _parse_api_error(self, response):
        """解析API错误信息"""
        try:
            error_json = response.json()
            if "error" in error_json and "code" in error_json["error"]:
                if error_json["error"]["code"] == "moderation_blocked" or "safety" in error_json["error"]["message"].lower():
                    return "触发了图片的安全审查，请尝试使用其他图片或修改提示词。"
                else:
                    return f"API请求失败: {error_json['error']['message']}"
            else:
                return f"API请求失败: {response.text}"
        except:
            return f"API请求失败: {response.text}"

    def _send_reply(self, reply_content, e_context: EventContext, reply_type=ReplyType.TEXT):
        """发送回复消息"""
        if isinstance(reply_content, Reply):
            if not reply_content.type and reply_type:
                reply_content.type = reply_type
            reply = reply_content
        else:
            reply = Reply(reply_type, reply_content)
        
        channel = e_context['channel']
        context = e_context['context']
        
        # reply的包装步骤
        rd = channel._decorate_reply(context, reply)
        # reply的发送步骤
        return channel._send_reply(context, rd)

    def _img_to_png(self, file_path):
        """将文件路径转换为PNG格式的BytesIO对象"""
        try:
            image = io.BytesIO()
            idata = Image.open(file_path)
            idata = idata.convert("RGBA")
            idata.save(image, format="PNG")
            image.seek(0)
            return image
        except Exception as e:
            logger.error(f"img_to_png error: {e}")
            return False

    def _img_to_png_from_bytes(self, content):
        """将字节内容转换为PNG格式的BytesIO对象"""
        try:
            image = io.BytesIO()
            idata = Image.open(io.BytesIO(content))
            idata = idata.convert("RGBA")
            idata.save(image, format="PNG")
            image.seek(0)
            return image
        except Exception as e:
            logger.error(f"img_to_png_from_bytes error: {e}")
            return False

    # ============ FAL 编辑相关方法 ============

    def _handle_fal_edit_async(self, image_path, prompt, e_context):
        """异步处理FAL图片编辑请求"""
        notice = "您的图片编辑请求已经收到，请稍候..."
        self._send_reply(notice, e_context)
        
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_fal_edit_sync, args=(image_path, prompt, e_context))
        thread.start()

    def _handle_fal_edit_sync(self, image_path, prompt, e_context):
        """同步处理FAL图片编辑请求"""
        logger.info(f"[fal_edit] 开始处理图片编辑任务，提示词: {prompt}")
        
        try:
            # 读取图片文件
            with open(image_path, 'rb') as img_file:
                image_bytes = img_file.read()

            # 保存图片到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                tmp_file.write(image_bytes)
                tmp_file_path = tmp_file.name

            try:
                # 使用fal_client上传图片并调用编辑API
                client = fal_client.SyncClient(key=self.fal_api_key)
                image_url = client.upload_file(tmp_file_path)
                if not image_url:
                    self._send_reply("图片上传失败", e_context)
                    return

                logger.info(f"[fal_edit] 图片上传成功: {image_url}")

                # 调用seedream/v4/edit模型进行图片编辑
                result = client.subscribe(
                    f"fal-ai/{self.fal_edit_model}",
                    arguments={
                        "prompt": prompt,
                        "image_urls": [image_url],  # seedream需要使用image_urls数组
                        "image_size": {
                            "height": 1280,
                            "width": 1280
                        },
                        "num_images": 1,
                        "max_images": 1,
                        "enable_safety_checker": False
                    },
                    with_logs=True
                )
                
                logger.info(f"[fal_edit] API响应: {result}")
                
                # 处理返回结果
                edited_image_url = None
                if isinstance(result, dict):
                    # 检查多种可能的返回格式
                    if "images" in result and isinstance(result["images"], list) and len(result["images"]) > 0:
                        edited_image_url = result["images"][0].get("url")
                    elif "image" in result and isinstance(result["image"], dict):
                        edited_image_url = result["image"].get("url")
                    elif "url" in result:
                        edited_image_url = result["url"]
                
                if edited_image_url and edited_image_url.startswith("http"):
                    self._download_and_send_image(edited_image_url, e_context, "图片编辑")
                else:
                    logger.error(f"[fal_edit] 未能从API响应中获取图片URL，完整响应: {result}")
                    self._send_reply("API返回的响应格式不正确，未找到编辑后的图片", e_context)
                    
            finally:
                # 删除临时文件
                if tmp_file_path and os.path.exists(tmp_file_path):
                    try:
                        os.remove(tmp_file_path)
                        logger.info(f"[fal_edit] 临时文件已删除: {tmp_file_path}")
                    except Exception as e_rem:
                        logger.warning(f"[fal_edit] 删除临时文件失败: {tmp_file_path}, error: {e_rem}")
            
        except Exception as e:
            logger.error(f"[fal_edit] 图片编辑API调用异常: {e}")
            self._send_reply(f"图片编辑服务出错: {str(e)}", e_context)
        finally:
            # 删除原始图片文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"原始图片文件已删除: {image_path}")
            except Exception as e:
                logger.error(f"删除原始图片文件失败: {image_path}, error: {e}")

    # ============ 视频生成相关方法 ============

    def _handle_img2video_async(self, image_path, prompt, e_context):
        """异步处理图生视频请求"""
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_img2video_sync, args=(image_path, prompt, e_context))
        thread.start()

    def _handle_img2video_sync(self, image_path, prompt, e_context):
        """同步处理图生视频请求 - 使用Kling2.6模型"""
        logger.info(f"[img2video-kling2.6] 开始处理图生视频任务，提示词: {prompt}")
        
        try:
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                self._send_reply("图生视频服务当前不可用，请检查FAL API配置", e_context)
                return

            # 读取图片文件
            with open(image_path, 'rb') as img_file:
                image_data = img_file.read()
            
            logger.info(f"[img2video-kling2.6] 图片已读取，大小: {len(image_data)} 字节")
            
            # 保存图片到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                tmp_file.write(image_data)
                tmp_file_path = tmp_file.name

            try:
                # 使用fal_client上传图片并调用Kling视频生成API
                client = fal_client.SyncClient(key=self.fal_api_key)
                image_url = client.upload_file(tmp_file_path)
                if not image_url:
                    self._send_reply("图片上传失败，图生视频终止", e_context)
                    return
                
                logger.info(f"[img2video-kling2.6] 图片上传成功: {image_url}")
                
                self._send_reply("图生视频任务已提交，正在处理中...", e_context)

                # 调用fal-ai/kling-video/v2.6/pro/image-to-video进行视频生成
                result = client.subscribe(
                    f"fal-ai/{self.fal_kling_img_model}",
                    arguments={
                        "prompt": prompt if prompt else "根据这张图片生成一个动态视频",
                        "image_url": image_url,
                        "duration": "10",
                        "negative_prompt": "blur, distort, and low quality",
                        "generate_audio": False
                    },
                    with_logs=True
                )
                
                logger.info(f"[img2video-kling2.6] API响应: {result}")
                
                # 处理返回结果
                video_url = None
                if isinstance(result, dict):
                    if "video" in result and isinstance(result["video"], dict):
                        video_url = result["video"].get("url")
                    elif "url" in result:
                        video_url = result["url"]
                
                if video_url and video_url.startswith("http"):
                    logger.info(f"[img2video-kling2.6] 视频生成成功: {video_url}")
                    self._download_and_send_video(video_url, e_context, "图生视频-Kling2.6")
                else:
                    logger.error(f"[img2video-kling2.6] 未能从API响应中获取视频URL，完整响应: {result}")
                    self._send_reply("图生视频失败，API没有返回视频URL", e_context)
                    
            finally:
                # 删除临时文件
                if tmp_file_path and os.path.exists(tmp_file_path):
                    try:
                        os.remove(tmp_file_path)
                        logger.info(f"[img2video-kling2.6] 临时文件已删除: {tmp_file_path}")
                    except Exception as e_rem:
                        logger.warning(f"[img2video-kling2.6] 删除临时文件失败: {tmp_file_path}, error: {e_rem}")
            
        except Exception as e:
            logger.error(f"[img2video-kling2.6] 图生视频API调用异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._send_reply(f"图生视频服务出错: {str(e)}", e_context)
        finally:
            # 删除原始图片文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"原始图片文件已删除: {image_path}")
            except Exception as e:
                logger.error(f"删除原始图片文件失败: {image_path}, error: {e}")

    def _handle_text2video_async(self, prompt, e_context):
        """异步处理文生视频请求"""
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_text2video_sync, args=(prompt, e_context))
        thread.start()

    def _handle_text2video_sync(self, prompt, e_context):
        """同步处理文生视频请求 - 使用Kling2.6模型"""
        logger.info(f"[text2video-kling2.6] 开始处理文生视频任务，提示词: {prompt}")
        
        try:
            if not FAL_AVAILABLE or not self.fal_api_key or self.fal_api_key == "your_fal_api_key_here":
                self._send_reply("文生视频服务当前不可用，请检查FAL API配置", e_context)
                return

            # 使用fal_client调用Kling文生视频API
            client = fal_client.SyncClient(key=self.fal_api_key)
            
            self._send_reply("文生视频任务已提交，正在处理中...", e_context)

            # 调用fal-ai/kling-video/v2.6/pro/text-to-video进行视频生成
            result = client.subscribe(
                f"fal-ai/{self.fal_kling_text_model}",
                arguments={
                    "prompt": prompt,
                    "duration": "10",
                    "aspect_ratio": "16:9",
                    "negative_prompt": "blur, distort, and low quality",
                    "cfg_scale": 0.5,
                    "generate_audio": False
                },
                with_logs=True
            )
            
            logger.info(f"[text2video-kling2.6] API响应: {result}")
            
            # 处理返回结果
            video_url = None
            if isinstance(result, dict):
                if "video" in result and isinstance(result["video"], dict):
                    video_url = result["video"].get("url")
                elif "url" in result:
                    video_url = result["url"]
            
            if video_url and video_url.startswith("http"):
                logger.info(f"[text2video-kling2.6] 视频生成成功: {video_url}")
                self._download_and_send_video(video_url, e_context, "文生视频-Kling2.6")
            else:
                logger.error(f"[text2video-kling2.6] 未能从API响应中获取视频URL，完整响应: {result}")
                self._send_reply("文生视频失败，API没有返回视频URL", e_context)
            
        except Exception as e:
            logger.error(f"[text2video-kling2.6] 文生视频API调用异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._send_reply(f"文生视频服务出错: {str(e)}", e_context)

    def _handle_img2video_hd_async(self, image_path, prompt, e_context):
        """异步处理图生高清视频请求"""
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_img2video_hd_sync, args=(image_path, prompt, e_context))
        thread.start()

    def _handle_img2video_hd_sync(self, image_path, prompt, e_context):
        """同步处理图生高清视频请求 - 使用Sora2-Pro模型，25秒"""
        logger.info(f"[img2video-sora2-pro] 开始处理图生高清视频任务，提示词: {prompt}")
        
        try:
            import mimetypes
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders
            import uuid
            
            # 读取图片文件
            with open(image_path, 'rb') as img_file:
                image_data = img_file.read()
            
            logger.info(f"[img2video-sora2-pro] 图片已读取，大小: {len(image_data)} 字节")
            
            # 构建multipart/form-data请求
            boundary = f'----WebKitFormBoundary{uuid.uuid4().hex[:16]}'
            
            # 构建form-data body
            body_parts = []
            
            # 添加model字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="model"')
            body_parts.append('')
            body_parts.append('sora-2-pro')
            
            # 添加prompt字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="prompt"')
            body_parts.append('')
            body_parts.append(prompt if prompt else "根据这张图片生成一个动态视频")
            
            # 添加size字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="size"')
            body_parts.append('')
            body_parts.append('1280x720')
            
            # 添加seconds字段（25秒）
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="seconds"')
            body_parts.append('')
            body_parts.append('25')
            
            # 添加watermark字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="watermark"')
            body_parts.append('')
            body_parts.append('')
            
            # 添加图片文件
            filename = os.path.basename(image_path)
            ext = os.path.splitext(image_path)[1].lower()
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            content_type = mime_types.get(ext, 'image/jpeg')
            
            body_parts.append(f'--{boundary}')
            body_parts.append(f'Content-Disposition: form-data; name="input_reference"; filename="{filename}"')
            body_parts.append(f'Content-Type: {content_type}')
            body_parts.append('')
            
            # 将文本部分组合
            body_text = '\r\n'.join(body_parts) + '\r\n'
            
            # 构建完整的body（文本 + 二进制图片数据 + 结束边界）
            body = body_text.encode('utf-8') + image_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
            
            # 发送请求到 api.tu-zi.com
            conn = http.client.HTTPSConnection("api.tu-zi.com")
            
            headers = {
                'Authorization': f'Bearer {self.veo3_api_key}',
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Content-Length': str(len(body))
            }
            
            # 发送POST请求
            conn.request("POST", "/v1/videos", body, headers)
            res = conn.getresponse()
            data = res.read()
            response_text = data.decode("utf-8")
            conn.close()
            
            logger.info(f"[img2video-sora2-pro] API响应状态: {res.status}, 内容: {response_text[:500]}")
            
            # 解析响应获取task_id
            task_id = ""
            try:
                result = json.loads(response_text)
                task_id = result.get("id", "")
                logger.info(f"[img2video-sora2-pro] 解析到的task_id: {task_id}")
            except Exception as e:
                logger.error(f"[img2video-sora2-pro] 解析响应失败: {e}")
            
            if not task_id:
                logger.error(f"[img2video-sora2-pro] 未能获取到task_id，响应: {response_text}")
                self._send_reply(f"图生高清视频请求失败: {response_text[:200]}", e_context)
                return
            
            logger.info(f"[img2video-sora2-pro] 任务已提交，task_id: {task_id}")
            self._send_reply("图生高清视频任务已提交（Sora2-Pro 25秒），正在处理中...", e_context)
            
            # 轮询查询任务状态
            max_retries = self.veo3_retry_times
            interval = 10  # 10秒查询一次
            
            for retry in range(1, max_retries + 1):
                logger.info(f"[img2video-sora2-pro] 查询任务状态 [{retry}/{max_retries}]")
                time.sleep(interval)
                
                # 查询任务状态
                conn = http.client.HTTPSConnection("api.tu-zi.com")
                headers = {'Authorization': f'Bearer {self.veo3_api_key}'}
                conn.request("GET", f"/v1/videos/{task_id}", '', headers)
                res = conn.getresponse()
                data = res.read()
                response_text = data.decode("utf-8")
                conn.close()
                
                try:
                    result_data = json.loads(response_text)
                    status = result_data.get("status", "unknown")
                    logger.info(f"[img2video-sora2-pro] 任务状态: {status}, 响应: {response_text[:500]}")
                    
                    if status == "completed":
                        # 获取视频URL
                        video_url = result_data.get("video_url")
                        
                        if video_url:
                            logger.info(f"[img2video-sora2-pro] 视频生成成功: {video_url}")
                            self._download_and_send_video(video_url, e_context, "图生高清视频-Sora2-Pro")
                            return
                        else:
                            self._send_reply("图生高清视频完成但未找到视频URL", e_context)
                            return
                    
                    elif status in ["failed", "error"]:
                        error_msg = result_data.get("error", result_data.get("message", "未知错误"))
                        logger.error(f"[img2video-sora2-pro] 视频生成失败: {error_msg}")
                        self._send_reply(f"图生高清视频失败: {error_msg}", e_context)
                        return
                    
                except Exception as e:
                    logger.warning(f"[img2video-sora2-pro] 解析响应异常: {e}, 响应内容: {response_text[:500]}")
            
            # 超过重试次数
            self._send_reply(f"图生高清视频超时，已尝试{max_retries}次查询", e_context)
            
        except Exception as e:
            logger.error(f"[img2video-sora2-pro] 图生高清视频API调用异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._send_reply(f"图生高清视频服务出错: {str(e)}", e_context)
        finally:
            # 删除原始图片文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"原始图片文件已删除: {image_path}")
            except Exception as e:
                logger.error(f"删除原始图片文件失败: {image_path}, error: {e}")

    def _handle_text2video_hd_async(self, prompt, e_context):
        """异步处理文生高清视频请求"""
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_text2video_hd_sync, args=(prompt, e_context))
        thread.start()

    def _handle_text2video_hd_sync(self, prompt, e_context):
        """同步处理文生高清视频请求 - 使用Sora2-Pro模型，25秒"""
        logger.info(f"[text2video-sora2-pro] 开始处理文生高清视频任务，提示词: {prompt}")
        
        try:
            import uuid
            
            # 构建multipart/form-data请求
            boundary = f'----WebKitFormBoundary{uuid.uuid4().hex[:16]}'
            
            # 构建form-data body
            body_parts = []
            
            # 添加model字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="model"')
            body_parts.append('')
            body_parts.append('sora-2-pro')
            
            # 添加prompt字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="prompt"')
            body_parts.append('')
            body_parts.append(prompt)
            
            # 添加size字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="size"')
            body_parts.append('')
            body_parts.append('1280x720')
            
            # 添加seconds字段（25秒）
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="seconds"')
            body_parts.append('')
            body_parts.append('25')
            
            # 添加watermark字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="watermark"')
            body_parts.append('')
            body_parts.append('')
            
            # 结束边界
            body_parts.append(f'--{boundary}--')
            body_parts.append('')
            
            # 组合body
            body = '\r\n'.join(body_parts)
            
            # 发送请求到 api.tu-zi.com
            conn = http.client.HTTPSConnection("api.tu-zi.com")
            
            headers = {
                'Authorization': f'Bearer {self.veo3_api_key}',
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Content-Length': str(len(body))
            }
            
            # 发送POST请求
            conn.request("POST", "/v1/videos", body.encode('utf-8'), headers)
            res = conn.getresponse()
            data = res.read()
            response_text = data.decode("utf-8")
            conn.close()
            
            logger.info(f"[text2video-sora2-pro] API响应状态: {res.status}, 内容: {response_text[:500]}")
            
            # 解析响应获取task_id
            task_id = ""
            try:
                result = json.loads(response_text)
                task_id = result.get("id", "")
                logger.info(f"[text2video-sora2-pro] 解析到的task_id: {task_id}")
            except Exception as e:
                logger.error(f"[text2video-sora2-pro] 解析响应失败: {e}")
            
            if not task_id:
                logger.error(f"[text2video-sora2-pro] 未能获取到task_id，响应: {response_text}")
                self._send_reply(f"文生高清视频请求失败: {response_text[:200]}", e_context)
                return
            
            logger.info(f"[text2video-sora2-pro] 任务已提交，task_id: {task_id}")
            self._send_reply("文生高清视频任务已提交（Sora2-Pro 25秒），正在处理中...", e_context)
            
            # 轮询查询任务状态
            max_retries = self.veo3_retry_times
            interval = 10  # 10秒查询一次
            
            for retry in range(1, max_retries + 1):
                logger.info(f"[text2video-sora2-pro] 查询任务状态 [{retry}/{max_retries}]")
                time.sleep(interval)
                
                # 查询任务状态
                conn = http.client.HTTPSConnection("api.tu-zi.com")
                headers = {'Authorization': f'Bearer {self.veo3_api_key}'}
                conn.request("GET", f"/v1/videos/{task_id}", '', headers)
                res = conn.getresponse()
                data = res.read()
                response_text = data.decode("utf-8")
                conn.close()
                
                try:
                    result_data = json.loads(response_text)
                    status = result_data.get("status", "unknown")
                    logger.info(f"[text2video-sora2-pro] 任务状态: {status}, 响应: {response_text[:500]}")
                    
                    if status == "completed":
                        # 获取视频URL
                        video_url = result_data.get("video_url")
                        
                        if video_url:
                            logger.info(f"[text2video-sora2-pro] 视频生成成功: {video_url}")
                            self._download_and_send_video(video_url, e_context, "文生高清视频-Sora2-Pro")
                            return
                        else:
                            self._send_reply("文生高清视频完成但未找到视频URL", e_context)
                            return
                    
                    elif status in ["failed", "error"]:
                        error_msg = result_data.get("error", result_data.get("message", "未知错误"))
                        logger.error(f"[text2video-sora2-pro] 视频生成失败: {error_msg}")
                        self._send_reply(f"文生高清视频失败: {error_msg}", e_context)
                        return
                    
                except Exception as e:
                    logger.warning(f"[text2video-sora2-pro] 解析响应异常: {e}, 响应内容: {response_text[:500]}")
            
            # 超过重试次数
            self._send_reply(f"文生高清视频超时，已尝试{max_retries}次查询", e_context)
            
        except Exception as e:
            logger.error(f"[text2video-sora2-pro] 文生高清视频API调用异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._send_reply(f"文生高清视频服务出错: {str(e)}", e_context)

    def _handle_veo3_img2video_async(self, image_path, prompt, e_context):
        """异步处理veo3图生视频请求"""
        # 启动异步任务
        import threading
        thread = threading.Thread(target=self._handle_veo3_img2video_sync, args=(image_path, prompt, e_context))
        thread.start()

    def _handle_veo3_img2video_sync(self, image_path, prompt, e_context):
        """同步处理veo3图生视频请求"""
        logger.info(f"[veo3-img2video] 开始处理veo3图生视频任务，提示词: {prompt}")
        
        try:
            import uuid
            
            # 读取图片文件
            with open(image_path, 'rb') as img_file:
                image_data = img_file.read()
            
            logger.info(f"[veo3-img2video] 图片已读取，大小: {len(image_data)} 字节")
            
            # 构建multipart/form-data请求
            boundary = f'----WebKitFormBoundary{uuid.uuid4().hex[:16]}'
            
            # 构建form-data body
            body_parts = []
            
            # 添加model字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="model"')
            body_parts.append('')
            body_parts.append('veo3')
            
            # 添加prompt字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="prompt"')
            body_parts.append('')
            body_parts.append(prompt if prompt else "根据这张图片生成一个动态视频")
            
            # 添加seconds字段（8秒）
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="seconds"')
            body_parts.append('')
            body_parts.append('8')
            
            # 添加size字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="size"')
            body_parts.append('')
            body_parts.append('1280x720')
            
            # 添加watermark字段
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="watermark"')
            body_parts.append('')
            body_parts.append('false')
            
            # 添加图片文件
            filename = os.path.basename(image_path)
            ext = os.path.splitext(image_path)[1].lower()
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            content_type = mime_types.get(ext, 'image/jpeg')
            
            body_parts.append(f'--{boundary}')
            body_parts.append(f'Content-Disposition: form-data; name="input_reference"; filename="{filename}"')
            body_parts.append(f'Content-Type: {content_type}')
            body_parts.append('')
            
            # 将文本部分组合
            body_text = '\r\n'.join(body_parts) + '\r\n'
            
            # 构建完整的body（文本 + 二进制图片数据 + 结束边界）
            body = body_text.encode('utf-8') + image_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
            
            # 发送请求到 api.tu-zi.com
            conn = http.client.HTTPSConnection("api.tu-zi.com")
            
            headers = {
                'Authorization': f'Bearer {self.veo3_api_key}',
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Content-Length': str(len(body))
            }
            
            # 发送POST请求
            conn.request("POST", "/v1/videos", body, headers)
            res = conn.getresponse()
            data = res.read()
            response_text = data.decode("utf-8")
            conn.close()
            
            logger.info(f"[veo3-img2video] API响应状态: {res.status}, 内容: {response_text[:500]}")
            
            # 解析响应获取task_id
            task_id = ""
            try:
                result = json.loads(response_text)
                task_id = result.get("id", "")
                logger.info(f"[veo3-img2video] 解析到的task_id: {task_id}")
            except Exception as e:
                logger.error(f"[veo3-img2video] 解析响应失败: {e}")
            
            if not task_id:
                logger.error(f"[veo3-img2video] 未能获取到task_id，响应: {response_text}")
                self._send_reply(f"veo3图生视频请求失败: {response_text[:200]}", e_context)
                return
            
            logger.info(f"[veo3-img2video] 任务已提交，task_id: {task_id}")
            self._send_reply("veo3图生视频任务已提交（8秒），正在处理中...", e_context)
            
            # 轮询查询任务状态
            max_retries = self.veo3_retry_times
            interval = 10  # 10秒查询一次
            
            for retry in range(1, max_retries + 1):
                logger.info(f"[veo3-img2video] 查询任务状态 [{retry}/{max_retries}]")
                time.sleep(interval)
                
                # 查询任务状态
                conn = http.client.HTTPSConnection("api.tu-zi.com")
                headers = {'Authorization': f'Bearer {self.veo3_api_key}'}
                conn.request("GET", f"/v1/videos/{task_id}", '', headers)
                res = conn.getresponse()
                data = res.read()
                response_text = data.decode("utf-8")
                conn.close()
                
                try:
                    result_data = json.loads(response_text)
                    status = result_data.get("status", "unknown")
                    logger.info(f"[veo3-img2video] 任务状态: {status}, 响应: {response_text[:500]}")
                    
                    if status == "completed":
                        # 获取视频URL
                        video_url = result_data.get("video_url")
                        
                        if video_url:
                            logger.info(f"[veo3-img2video] 视频生成成功: {video_url}")
                            self._download_and_send_video(video_url, e_context, "veo3图生视频")
                            return
                        else:
                            self._send_reply("veo3图生视频完成但未找到视频URL", e_context)
                            return
                    
                    elif status in ["failed", "error"]:
                        error_msg = result_data.get("error", result_data.get("message", "未知错误"))
                        logger.error(f"[veo3-img2video] 视频生成失败: {error_msg}")
                        self._send_reply(f"veo3图生视频失败: {error_msg}", e_context)
                        return
                    
                except Exception as e:
                    logger.warning(f"[veo3-img2video] 解析响应异常: {e}, 响应内容: {response_text[:500]}")
            
            # 超过重试次数
            self._send_reply(f"veo3图生视频超时，已尝试{max_retries}次查询", e_context)
            
        except Exception as e:
            logger.error(f"[veo3-img2video] 图生视频API调用异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._send_reply(f"veo3图生视频服务出错: {str(e)}", e_context)
        finally:
            # 删除原始图片文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"原始图片文件已删除: {image_path}")
            except Exception as e:
                logger.error(f"删除原始图片文件失败: {image_path}, error: {e}")

    # ============ 下载和发送辅助方法 ============

    def _download_and_send_image(self, image_url, e_context, task_name="图片处理"):
        """下载图片并发送给用户"""
        try:
            response = requests.get(image_url, timeout=120)
            if response.status_code == 200:
                image_data = response.content
                logger.info(f"[{task_name}] 图片下载成功，大小: {len(image_data)} 字节")
                
                # 转换为base64格式发送，兼容飞书等平台
                image_b64 = base64.b64encode(image_data).decode()
                data_url = f"data:image/png;base64,{image_b64}"
                
                self._send_reply(data_url, e_context, ReplyType.IMAGE_URL)
                return True
            else:
                raise Exception(f"图片下载失败，状态码: {response.status_code}")
        except Exception as e:
            logger.error(f"[{task_name}] 图片下载或发送失败: {e}")
            self._send_reply(f"{task_name}完成但图片下载失败: {str(e)}", e_context)
            return False

    def _download_and_send_video(self, video_url, e_context, task_name="视频处理"):
        """下载视频并发送给用户"""
        video_tmp_path = None
        cover_path = None
        try:
            # 获取临时视频路径
            video_tmp_path = self._get_tmp_video_path()
            
            # 下载视频
            response = requests.get(video_url, timeout=600, stream=True)
            if response.status_code == 200:
                with open(video_tmp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logger.info(f"[{task_name}] 视频下载成功: {video_tmp_path}, 大小: {os.path.getsize(video_tmp_path)} 字节")
                
                # 生成封面
                cover_path = self._get_video_cover(video_tmp_path)
                
                # 发送视频
                self._send_video_with_custom_logic(video_tmp_path, cover_path, e_context)
                logger.info(f"[{task_name}] 视频发送成功")
                
            else:
                raise Exception(f"视频下载失败，状态码: {response.status_code}")
                
        except Exception as e:
            logger.error(f"[{task_name}] 视频下载或发送失败: {e}")
            self._send_reply(f"{task_name}完成但视频下载失败: {str(e)}", e_context)
        finally:
            # 清理临时文件
            if video_tmp_path and os.path.exists(video_tmp_path):
                try:
                    os.remove(video_tmp_path)
                    logger.info(f"[{task_name}] 临时视频文件已删除: {video_tmp_path}")
                except Exception as e_rem:
                    logger.warning(f"[{task_name}] 删除临时视频文件失败: {video_tmp_path}, error: {e_rem}")
            
            if cover_path and os.path.exists(cover_path):
                try:
                    os.remove(cover_path)
                    logger.info(f"[{task_name}] 临时封面文件已删除: {cover_path}")
                except Exception as e_rem:
                    logger.warning(f"[{task_name}] 删除临时封面文件失败: {cover_path}, error: {e_rem}")

    def _get_tmp_video_path(self):
        """获取临时视频文件路径"""
        tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        filename = f"video_{uuid.uuid4().hex}.mp4"
        return os.path.join(tmp_dir, filename)

    def _get_video_cover(self, video_path):
        """智能获取视频封面，优先提取视频帧，失败时使用默认封面"""
        try:
            return self._extract_video_frame_as_cover(video_path)
        except Exception as e:
            logger.warning(f"视频帧提取失败，使用默认封面: {e}")
            return self._generate_cover_image_file()

    def _extract_video_frame_as_cover(self, video_path):
        """从视频文件中提取第一帧作为封面"""
        import subprocess
        
        tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        
        cover_filename = f"frame_cover_{uuid.uuid4().hex}.jpg"
        cover_path = os.path.join(tmp_dir, cover_filename)
        
        # 使用ffmpeg提取视频第一帧
        cmd = [
            'ffmpeg', '-i', video_path, 
            '-vf', 'scale=640:360',  # 缩放到标准尺寸
            '-vframes', '1',         # 只提取1帧
            '-q:v', '2',             # 高质量
            '-y',                    # 覆盖输出文件
            cover_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and os.path.exists(cover_path):
            logger.info(f"视频帧封面提取成功: {cover_path}")
            return cover_path
        else:
            logger.warning(f"ffmpeg提取失败: {result.stderr}")
            raise Exception(f"ffmpeg提取失败: {result.stderr}")

    def _generate_cover_image_file(self):
        """生成默认视频封面"""
        tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        
        cover_filename = "fallback_cover.png"
        cover_path = os.path.join(tmp_dir, cover_filename)
        
        # 如果已经存在，直接返回
        if os.path.exists(cover_path):
            return cover_path

        # 生成一个简单、标准的封面图片
        img = Image.new('RGB', (480, 270), color=(240, 240, 240))  # 浅灰色背景
        draw = ImageDraw.Draw(img)
        
        # 绘制播放按钮图标
        center_x, center_y = 240, 135
        
        # 画一个圆形背景
        draw.ellipse([center_x-40, center_y-40, center_x+40, center_y+40], 
                    fill=(100, 100, 100), outline=(80, 80, 80), width=2)
        
        # 画播放三角形
        triangle_points = [
            (center_x-15, center_y-20),
            (center_x-15, center_y+20), 
            (center_x+20, center_y)
        ]
        draw.polygon(triangle_points, fill=(255, 255, 255))
        
        # 保存为PNG格式
        img.save(cover_path, format='PNG', optimize=True)
        logger.info(f"标准封面已生成: {cover_path}")
        return cover_path

    def _send_video_with_custom_logic(self, video_path, cover_path, e_context):
        """自定义视频发送逻辑"""
        try:
            # 读取视频文件
            with open(video_path, "rb") as f:
                video_data = f.read()
            
            # 获取视频时长，默认5秒
            duration_seconds = 5
            if MEDIAINFO_AVAILABLE:
                try:
                    media_info = MediaInfo.parse(video_path)
                    if media_info.tracks and media_info.tracks[0].duration:
                        duration_ms = media_info.tracks[0].duration
                        if duration_ms > 0:
                            duration_seconds = int(duration_ms / 1000)
                            if duration_seconds > 60:  # 限制最大60秒
                                duration_seconds = 5
                except Exception as e:
                    logger.warning(f"获取视频时长失败，使用默认值: {e}")
            
            logger.info(f"视频时长: {duration_seconds}秒")
            
            # 异步任务中直接发送视频，而不是设置e_context
            video_stream = io.BytesIO(video_data)
            video_stream.seek(0)
            reply = Reply(ReplyType.VIDEO, video_stream)
            
            # 直接发送视频消息
            self._send_reply(reply, e_context)
            
        except Exception as e:
            logger.error(f"自定义视频发送失败: {e}")
            self._send_reply(f"视频发送失败: {str(e)}", e_context)

    def _send_test_video(self, video_path, e_context):
        """发送测试视频"""
        try:
            logger.info(f"[测试视频] 开始发送测试视频: {video_path}")
            
            # 读取视频文件
            with open(video_path, "rb") as f:
                video_data = f.read()
            
            logger.info(f"[测试视频] 视频文件大小: {len(video_data)} 字节")
            
            # 发送视频文件
            video_stream = io.BytesIO(video_data)
            video_stream.seek(0)
            reply = Reply(ReplyType.VIDEO, video_stream)
            
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            
            logger.info("[测试视频] 测试视频发送完成")
            
        except Exception as e:
            logger.error(f"[测试视频] 测试视频发送失败: {e}")
            self._send_reply(f"测试视频发送失败: {str(e)}", e_context)
        