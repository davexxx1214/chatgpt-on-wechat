import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
from common.expired_dict import ExpiredDict
from common.tmp_dir import TmpDir
import time

import os
import requests
import uuid
import io
from PIL import Image
import cv2
import numpy as np
import requests
import translators as ts

@plugins.register(
    name="stability",
    desire_priority=2,
    desc="A plugin to call stabilityai API",
    version="0.0.1",
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
                # 使用父类的方法来加载配置
                self.config = super().load_config()

                if not self.config:
                    raise Exception("config.json not found")
            
            # 设置事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            # 从配置中提取所需的设置
            self.inpaint_url = self.config.get("inpaint_url","")
            self.inpaint_prefix = self.config.get("inpaint_prefix","修图")
            self.upscale_url = self.config.get("upscale_url","")
            self.upscale_prefix = self.config.get("upscale_prefix","图片高清化")
            self.repair_url = self.config.get("repair_url","")
            self.repair_prefix = self.config.get("repair_prefix","图片修复")
            self.doodle_url = self.config.get("doodle_url","")
            self.doodle_prefix = self.config.get("doodle_prefix", "涂鸦修图")
            self.erase_url = self.config.get("erase_url","")
            self.erase_prefix = self.config.get("erase_prefix", "图片擦除")
            self.rmbg_url = self.config.get("rmbg_url","")
            self.rmbg_prefix = self.config.get("rmbg_prefix", "去背景")
            self.sd3_url = self.config.get("sd3_url","")
            self.sd3_prefix = self.config.get("sd3_prefix", "sd3")
            self.sd3_mode = self.config.get("sd3_mode", "sd3")
            self.outpaint_url=self.config.get("outpaint_url","")
            self.outpaint_prefix = self.config.get("outpaint_prefix", "扩图")
            self.api_key = self.config.get("api_key", "")
            self.glif_prefix = self.config.get("glif_prefix", "glif")
            self.flux_prefix = self.config.get("flux_prefix", "flux")
            self.glif_api_key = self.config.get("glif_api_key", "")
            self.glif_id = self.config.get("glif_id", "")
            self.recraft_prefix = self.config.get("recraft_prefix", "recraft")
            self.recraft_api_key = self.config.get("recraft_api_key", "")
            self.jimeng_prefix = self.config.get("jimeng_prefix", "jimeng")
            self.jimeng_api_key = self.config.get("jimeng_api_key", "")
            self.jimeng_url = self.config.get("jimeng_url", "")
            self.total_timeout = self.config.get("total_timeout", 5)

            self.params_cache = ExpiredDict(500)
            # 初始化成功日志
            logger.info("[stability] inited.")
        except Exception as e:
            # 初始化失败日志
            logger.warn(f"stability init failed: {e}")
    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT, ContextType.SHARING,ContextType.FILE,ContextType.IMAGE]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        user_id = msg.from_user_id
        content = context.content

        # 将用户信息存储在params_cache中
        if user_id not in self.params_cache:
            self.params_cache[user_id] = {}
            self.params_cache[user_id]['inpaint_quota'] = 0
            self.params_cache[user_id]['search_prompt'] = None
            self.params_cache[user_id]['prompt'] = None
            self.params_cache[user_id]['upscale_quota'] = 0
            self.params_cache[user_id]['upscale_prompt'] = None
            self.params_cache[user_id]['repair_quota'] = 0 
            self.params_cache[user_id]['doodle_quota'] = 0
            self.params_cache[user_id]['rmbg_quota'] = 0
            self.params_cache[user_id]['outpaint_quota'] = 0
            self.params_cache[user_id]['erase_quota'] = 0

            logger.debug('Added new user to params_cache. user id = ' + user_id)

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.inpaint_prefix):
                # Call new function to handle search operation
                pattern = self.inpaint_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了修图的指令
                    query = content[len(self.inpaint_prefix):].strip()
                    pattern = r"把(.*?)替换成([^，。,.!?;:\s]*).*"
                    match = re.search(pattern, query)
                    if match: ##   匹配上了中文的描述
                        search_prompt = match[1].strip()
                        prompt = match[2].strip()
                        
                        logger.info(f"search_prompt={search_prompt}")
                        logger.info(f"prompt={prompt}" )

                        search_prompt = self.translate_to_english(search_prompt)
                        logger.info(f"translate search_prompt to : {search_prompt}")
                        prompt = self.translate_to_english(prompt)
                        logger.info(f"translate search_prompt to : {prompt}")
                        self.params_cache[user_id]['search_prompt'] = search_prompt
                        self.params_cache[user_id]['prompt'] = prompt
                        self.params_cache[user_id]['inpaint_quota'] = 1
                        tip = f"💡已经开启修图服务，请再发送一张图片进行处理"

                    else:
                        pattern = re.compile(r'replace (.*?) to (.*?)$')
                        logger.info(f"query={query}")
                        match = pattern.search(query)
                        if match is None:
                            tip = f"❌错误的命令\n\n💡修图指令格式为:\n\n{self.inpaint_prefix}+ 空格 + 把xxx替换成yyy\n{self.inpaint_prefix}+ 空格 + replace xxx to yyy\n例如:修图 把狗替换成猫\n或者:修图 replace water to sand"
                        else:  ##   匹配上了英文的描述
                            search_prompt, prompt = match.groups()
                            logger.info(f"search_prompt={search_prompt}")
                            logger.info(f"prompt={prompt}" )
                            self.params_cache[user_id]['search_prompt'] = search_prompt
                            self.params_cache[user_id]['prompt'] = prompt
                            self.params_cache[user_id]['inpaint_quota'] = 1
                            tip = f"💡已经开启修图服务，请再发送一张图片进行处理"
                else:
                    tip = f"💡欢迎使用修图服务，修图指令格式为:\n\n{self.inpaint_prefix}+ 空格 + 把xxx替换成yyy\n{self.inpaint_prefix}+ 空格 + replace xxx to yyy\n例如:修图 把狗替换成猫\n或者:修图 replace water to sand"

                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.repair_prefix):
                self.params_cache[user_id]['repair_quota'] = 1
                tip = f"💡已经开启图片修复服务，请再发送一张图片进行处理(分辨率小于1024*1024)"
                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.outpaint_prefix):
                self.params_cache[user_id]['outpaint_quota'] = 1
                tip = f"💡已经开启图片扩展服务，请再发送一张图片进行处理"
                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.rmbg_prefix):
                self.params_cache[user_id]['rmbg_quota'] = 1
                tip = f"💡已经开启图片消除背景服务，请再发送一张图片进行处理"
                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.sd3_prefix):
                pattern = self.sd3_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了sd3的指令
                    sd3_prompt = content[len(self.sd3_prefix):].strip()
                    sd3_prompt = self.translate_to_english(sd3_prompt)
                    logger.info(f"sd3_prompt = : {sd3_prompt}")
                    self.call_sd3_service(sd3_prompt, e_context)
                else:
                    tip = f"💡欢迎使用sd3正式版绘图，指令格式为:\n\n{self.sd3_prefix}+ 空格 + 图片描述"
                    reply = Reply(type=ReplyType.TEXT, content= tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.glif_prefix):
                pattern = self.glif_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了glif的指令
                    glif_prompt = content[len(self.glif_prefix):].strip()
                    logger.info(f"glif_prompt = : {glif_prompt}")
                    glif_prompt = self.translate_to_english(glif_prompt)
                    self.call_glif_service(glif_prompt, e_context)
                else:
                    tip = f"💡欢迎使用gif生成器，指令格式为:\n\n{self.glif_prefix}+ 空格 + 主题(英文更佳)\n例如：{self.glif_prefix} a smiling cat"
                    reply = Reply(type=ReplyType.TEXT, content= tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                
            elif content.startswith(self.flux_prefix):
                pattern = self.flux_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了glif的指令
                    flux_prompt = content[len(self.flux_prefix):].strip()
                    logger.info(f"flux_prompt = : {flux_prompt}")
                    flux_prompt = self.translate_to_english(flux_prompt)
                    self.call_flux_service(flux_prompt, e_context)
                else:
                    tip = f"💡欢迎使用flux绘图，指令格式为:\n\n{self.flux_prefix}+ 空格 + 主题(英文更佳)\n例如：{self.flux_prefix} a smiling cat"
                    reply = Reply(type=ReplyType.TEXT, content= tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.recraft_prefix):
                pattern = self.recraft_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了recraft的指令
                    recraft_prompt = content[len(self.recraft_prefix):].strip()
                    logger.info(f"recraft_prompt = : {recraft_prompt}")
                    recraft_prompt = self.translate_to_english(recraft_prompt)
                    self.call_recraft_service(recraft_prompt, e_context)
                else:
                    tip = f"💡欢迎使用Recraft V3绘图，指令格式为:\n\n{self.recraft_prefix}+ 空格 + 主题(英文更佳)\n例如：{self.recraft_prefix} a smiling cat"
                    reply = Reply(type=ReplyType.TEXT, content= tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.doodle_prefix):
                # Call new function to handle search operationd
                pattern = self.doodle_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了doodle的指令
                    doodle_prompt = content[len(self.doodle_prefix):].strip()
                    doodle_prompt = self.translate_to_english(doodle_prompt)
                    logger.info(f"doodle_prompt = : {doodle_prompt}")

                    self.params_cache[user_id]['doodle_prompt'] = doodle_prompt
                    self.params_cache[user_id]['doodle_quota'] = 1
                    tip = f"💡已经开启涂鸦修图模式，请将涂鸦后的图片发送给我。(仅支持微信里的红色涂鸦)"

                else:
                    tip = f"💡欢迎使用涂鸦修图服务，指令格式为:\n\n{self.doodle_prefix}+ 空格 + 涂鸦替换成的内容（用英文效果更好）。\n例如：涂鸦修图 3D cute monsters "

                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.erase_prefix):
                self.params_cache[user_id]['erase_quota'] = 1
                tip = f"💡已经开启图片擦除服务，可以帮您擦除图片中的指定物品。请将涂鸦以后的图片发送给我。(仅支持微信里的红色涂鸦)"
                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.upscale_prefix):
                self.params_cache[user_id]['upscale_quota'] = 1
                tip = f"💡已经开启图片高清化服务，请再发送一张图片进行处理(分辨率小于1536*1536)"
                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.jimeng_prefix):
                pattern = self.jimeng_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了jimeng的指令
                    jimeng_prompt = content[len(self.jimeng_prefix):].strip()
                    logger.info(f"jimeng_prompt = : {jimeng_prompt}")
                    self.call_jimeng_service(jimeng_prompt, e_context)
                else:
                    tip = f"💡欢迎使用即梦AI绘图，指令格式为:\n\n{self.jimeng_prefix}+ 空格 + 主题(支持中文)\n例如：{self.jimeng_prefix} 一只可爱的猫"
                    reply = Reply(type=ReplyType.TEXT, content= tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS

        elif context.type == ContextType.IMAGE:
            if (self.params_cache[user_id]['inpaint_quota'] < 1 and 
                self.params_cache[user_id]['upscale_quota'] < 1 and 
                self.params_cache[user_id]['repair_quota'] < 1 and 
                self.params_cache[user_id]['doodle_quota'] < 1 and 
                self.params_cache[user_id]['rmbg_quota'] < 1 and 
                self.params_cache[user_id]['outpaint_quota'] < 1 and
                self.params_cache[user_id]['erase_quota'] < 1):
                # 进行下一步的操作                
                logger.debug("on_handle_context: 当前用户识图配额不够，不进行识别")
                return

            logger.info("on_handle_context: 开始处理图片")
            context.get("msg").prepare()
            image_path = context.content
            logger.info(f"on_handle_context: 获取到图片路径 {image_path}")

            if self.params_cache[user_id]['inpaint_quota'] > 0:
                self.params_cache[user_id]['inpaint_quota'] = 0
                self.call_inpaint_service(image_path, user_id, e_context)

            if self.params_cache[user_id]['upscale_quota'] > 0:
                self.params_cache[user_id]['upscale_quota'] = 0
                self.call_upscale_service(image_path, user_id, e_context)

            if self.params_cache[user_id]['repair_quota'] > 0:
                self.params_cache[user_id]['repair_quota'] = 0
                self.call_repair_service(image_path, user_id, e_context)
            
            if self.params_cache[user_id]['erase_quota'] > 0:
                self.params_cache[user_id]['erase_quota'] = 0
                self.call_erase_service(image_path, e_context)

            if self.params_cache[user_id]['doodle_quota'] > 0:
                self.params_cache[user_id]['doodle_quota'] = 0
                self.call_doodle_service(image_path, user_id, e_context)

            if self.params_cache[user_id]['rmbg_quota'] > 0:
                self.params_cache[user_id]['rmbg_quota'] = 0
                self.call_rmbg_service(image_path, user_id, e_context)

            if self.params_cache[user_id]['outpaint_quota'] > 0:
                self.params_cache[user_id]['outpaint_quota'] = 0
                self.call_outpaint_service(image_path, user_id, e_context)

            # 删除文件
            os.remove(image_path)
            logger.info(f"文件 {image_path} 已删除")

    def call_inpaint_service(self, image_path, user_id, e_context):
        self.handle_stability(image_path, user_id, e_context)

    def handle_stability(self, image_path, user_id, e_context):
        logger.info(f"handle_stability")

        search_prompt = self.params_cache[user_id]['search_prompt']
        prompt = self.params_cache[user_id]['prompt']
        

        response = requests.post(
            f"{self.inpaint_url}",
            headers={
                "authorization": f"Bearer {self.api_key}",
                "accept": "image/*"},
            files={"image": open(image_path, "rb")},
            data={
                "prompt": prompt,
                "search_prompt": search_prompt,
                "output_format": "png",
            },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "stability" + str(uuid.uuid4()) + ".png" 
            logger.info(f"handle stability result, imagePath = {imgpath}")
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_png(imgpath)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_repair_service(self, image_path, user_id, e_context):
        logger.info(f"calling repair service")

        response = requests.post(
            f"{self.repair_url}",
            headers={
                "Accept": "image/*",
                "Authorization": f"Bearer {self.api_key}"
            },
            files={
                "image": open(image_path, "rb")
            },
            data={
                "prompt": "Add more details to make the image more high-definition",
                "output_format": "png"
            }
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "repair" + str(uuid.uuid4()) + ".png" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_jpeg(response.content)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] repair service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            rc= "服务暂不可用,可能是图片分辨率太高"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_doodle_service(self, image_path, user_id, e_context):
        logger.info(f"calling doodle service")
   
        doodle_prompt = self.params_cache[user_id]['doodle_prompt']

        self.create_red_mask(image_path)

        response = requests.post(
            f"{self.doodle_url}",
            headers={"authorization": f"Bearer {self.api_key}", "accept": "image/*"},

            files={
                'image': open(image_path, 'rb'),
                'mask': open("./mask.png", 'rb'),
            },
            data={
                "prompt": doodle_prompt,
                "output_format": "png",
            },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "doodle" + str(uuid.uuid4()) + ".png" 
            logger.info(f"get doodle result, imagePath = {imgpath}")
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_png(imgpath)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] doodle service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] doodle service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_erase_service(self, image_path, e_context):
        logger.info(f"calling erase service")
        self.create_red_mask(image_path, "erase_mask.png")

        response = requests.post(
            f"{self.erase_url}",
            headers={"authorization": f"Bearer {self.api_key}", "accept": "image/*"},

            files={
                'image': open(image_path, 'rb'),
                'mask': open("./erase_mask.png", 'rb'),
            },
            data={
                "output_format": "png",
            },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "erase" + str(uuid.uuid4()) + ".png" 
            logger.info(f"get erase result, imagePath = {imgpath}")
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_png(imgpath)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] erase service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] doodle service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_rmbg_service(self, image_path, user_id, e_context):
        logger.info(f"calling remove bg service")
   
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
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "rmgb" + str(uuid.uuid4()) + ".png" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_png(imgpath)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] rmbg service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            rc= "服务暂不可用,可能是图片分辨率太高(仅支持分辨率小于2048*2048的图片)"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] rmbg service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_outpaint_service(self, image_path, user_id, e_context):
        logger.info(f"calling outpainting service")
   
        response = requests.post(
            f"{self.outpaint_url}",
            headers={
                "accept": "image/*",
                "Authorization": f"Bearer {self.api_key}"
            },
            files={
                "image": open(image_path, "rb")
            },
            data={
                "left": 512,
                "down": 512,
                "right":512,
                "up":512,
                "output_format": "png"
             },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "outpaint" + str(uuid.uuid4()) + ".png" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_png(imgpath)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] rmbg service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] rmbg service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_sd3_service(self, sd3_prompt,e_context):
        logger.info(f"calling sd3 service")
        response = requests.post(
            f"{self.sd3_url}",
            headers={
                "accept": "image/*",
                "Authorization": f"Bearer {self.api_key}"
            },
            files={
               "none": ''
            },
            data={
                "prompt": sd3_prompt,
                "model": self.sd3_mode,
                "output_format": "png"
             },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "sd3" + str(uuid.uuid4()) + ".png" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_png(imgpath)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] sd3 service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] sd3 service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS


    def call_glif_service(self, glif_prompt,e_context):
        logger.info(f"calling glif service")

        tip = f'您的GIF正在生成中，请耐心等待1-2分钟。\n当前使用的提示词为：\n{glif_prompt}'
        self.send_reply(tip, e_context)

        response = requests.post(
            "https://simple-api.glif.app",
            headers={
                "Authorization": f"Bearer {self.glif_api_key}"
            },
            json={"id": f"{self.glif_id}", 
                  "inputs": {
                    "prompt": f"{glif_prompt}",
                    "creativity": "Medium",
                    "format": "Animated GIF (Low quality - Low res)"
                  }
            } 
        )

        if response.status_code == 200:
            response_data = response.json()
            image_url = response_data.get('output')
            if image_url is not None:
                logger.info("glif image url = " + image_url)
                rt = ReplyType.TEXT
                rc = '您的GIF已经准备好，点击图片下载即可保存GIF，点击文件可查看效果'
                self.send_reply(rc, e_context, rt)
                
                rt = ReplyType.IMAGE_URL
                rc = image_url
                self.send_reply(rc, e_context, rt)

                downloaded_path = self.download_gif(image_url)
                rt = ReplyType.FILE
                rc = downloaded_path
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rt = ReplyType.TEXT
                rc = "gif罢工了~"
                reply = Reply(rt, rc)
                logger.error("[stability] glif service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] glif service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_flux_service(self, flux_prompt,e_context):
        logger.info(f"calling glif service")

        tip = f'欢迎使用Flux.\n💡您的提示词已经自动翻译成英文，图片正在生成中，请耐心等待1-2分钟。\n当前使用的提示词为：\n{flux_prompt}'
        self.send_reply(tip, e_context)

        response = requests.post(
            "https://simple-api.glif.app",
            headers={
                "Authorization": f"Bearer {self.glif_api_key}"
            },
            json={"id": "clzgvha5a00041aepvz2h4zi4", 
                  "inputs": {
                    "input": f"{flux_prompt}",
                    "ar":"1:1",
                    "schnell":"schnell",
                    "choise":"yes"
                  }
            } 
        )

        if response.status_code == 200:
            response_data = response.json()
            image_url = response_data.get('output')
            if image_url is not None:
                logger.info("flux image url = " + image_url)
                rt = ReplyType.IMAGE_URL
                rc = image_url
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rt = ReplyType.TEXT
                rc = "flux罢工了~"
                reply = Reply(rt, rc)
                logger.error("[stability] glif service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] flux service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_recraft_service(self, recraft_prompt,e_context):
        logger.info(f"calling recraft service")

        tip = f'欢迎使用Recraft V3.\n💡您的提示词已经自动翻译成英文，图片正在生成中，请耐心等待1-2分钟。\n当前使用的提示词为：\n{recraft_prompt}'
        self.send_reply(tip, e_context)

        response = requests.post(
            "https://external.api.recraft.ai/v1/images/generations",
            headers={
                "Authorization": f"Bearer {self.recraft_api_key}"
            },
            json={"prompt": f"{recraft_prompt}"} 
        )

        if response.status_code == 200:
            response_data = response.json()
            image_url = response_data.get('data', [{}])[0].get('url')
            if image_url is not None:
                logger.info("recraft image url = " + image_url)
                rt = ReplyType.IMAGE_URL
                rc = image_url
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rt = ReplyType.TEXT
                rc = "recraft罢工了~"
                reply = Reply(rt, rc)
                logger.error("[stability] recraft service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc= error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] recraft service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def call_jimeng_service(self, jimeng_prompt, e_context):
        logger.info(f"calling jimeng service")

        tip = f'欢迎使用即梦AI.\n💡图片正在生成中，请耐心等待。\n当前使用的提示词为：\n{jimeng_prompt}'
        self.send_reply(tip, e_context)

        response = requests.post(
            f"{self.jimeng_url}/v1/images/generations",
            headers={
                "Authorization": f"Bearer {self.jimeng_api_key}"
            },
            json={"prompt": f"{jimeng_prompt}"} 
        )

        if response.status_code == 200:
            response_data = response.json()
            data_list = response_data.get('data', [])
            if data_list:
                # 遍历所有生成的图片URL并发送
                for item in data_list:
                    url = item.get('url')
                    if url:
                        logger.info("jimeng image url = " + url)
                        rt = ReplyType.IMAGE_URL
                        rc = url
                        self.send_reply(rc, e_context, rt)
                
                rt = ReplyType.TEXT
                rc = "即梦图片生成完毕。"
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            else:
                rt = ReplyType.TEXT
                rc = "jimeng生成图片失败~"
                reply = Reply(rt, rc)
                logger.error("[stability] jimeng service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            error = str(response.json())
            rc = error
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] jimeng service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def download_gif(self, url):
        try:
            # 创建临时目录
            imgpath = TmpDir().path() + "gif" + str(uuid.uuid4()) + ".gif"      
            # 下载 GIF 图片
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(imgpath, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                print(f"GIF image downloaded and saved to: {imgpath}")
                return imgpath
            else:
                print(f"Failed to download image. Status code: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"An error occurred: {e}")
            return None
        
    def send_reply(self, reply, e_context: EventContext, reply_type=ReplyType.TEXT):
        if isinstance(reply, Reply):
            if not reply.type and reply_type:
                reply.type = reply_type
        else:
            reply = Reply(reply_type, reply)
        channel = e_context['channel']
        context = e_context['context']
        # reply的包装步骤
        rd = channel._decorate_reply(context, reply)
        # reply的发送步骤
        return channel._send_reply(context, rd)

    def call_upscale_service(self, image_path, user_id, e_context):
        logger.info(f"calling upscale service")

        response = requests.post(
            f"{self.upscale_url}",
            headers={
                "Accept": "image/*",
                "Authorization": f"Bearer {self.api_key}"
            },
            files={
                "image": open(image_path, "rb")
            },
            data={
                "output_format": "png"
            }
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "upscale" + str(uuid.uuid4()) + ".png" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_jpeg(response.content)
            if image is False:
                rc= "服务暂不可用"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[stability] upscale service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = image
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            rc= "服务暂不可用,可能是图片分辨率太高"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def translate_to_english(self, text):
        logger.info(f"translate text = {text}")
        return ts.translate_text(text, translator='google')

    def img_to_jpeg(self, content):
        try:
            image = io.BytesIO()
            idata = Image.open(io.BytesIO(content))
            idata = idata.convert("RGB")
            idata.save(image, format="JPEG")
            return image
        except Exception as e:
            logger.error(e)
            return False
        
    def img_to_gif(self, file_path):
        try:
            image = io.BytesIO()  # 创建一个 BytesIO 对象来存储图像数据
            idata = Image.open(file_path)  # 使用文件路径打开图像

            # 根据需要进行其他处理，这里我们保持原始模式，直接保存为 GIF
            idata.save(image, format="GIF")  # 指定保存格式为GIF
            image.seek(0)  # 将指针移动到流的开头
            return image
        except Exception as e:
            logger.error(e)
            return False
        
    def img_to_png(self, file_path):
        try:
            image = io.BytesIO()
            idata = Image.open(file_path)  # 使用文件路径打开图像
            idata = idata.convert("RGBA")  # 转换为RGBA模式以保持PNG的透明度
            idata.save(image, format="PNG")  # 指定保存格式为PNG
            image.seek(0)
            return image
        except Exception as e:
            logger.error(e)
            return False
        
    def convert_rgb_to_hsv(self, rgb_color):
        bgr_color = np.uint8([[rgb_color[::-1]]])
        hsv_color = cv2.cvtColor(bgr_color, cv2.COLOR_BGR2HSV)
        return hsv_color[0][0]

    def create_red_mask(self, image_path, save_path='mask.png'):
        # 给定的RGB颜色样本列表
        rgb_samples = [
            (245, 51, 15), (242, 53, 15), (244, 52, 15),
            (243, 52, 15), (242, 53, 15), (244, 51, 18)
        ]

        # 将RGB颜色样本转换到HSV空间
        hsv_samples = [self.convert_rgb_to_hsv(rgb) for rgb in rgb_samples]

        # HSV范围值
        h_values, s_values, v_values = zip(*hsv_samples)
        h_range = (max(0, min(h_values) - 10), min(179, max(h_values) + 10))
        s_range = (max(0, min(s_values) - 50), min(255, max(s_values) + 50))
        v_range = (max(0, min(v_values) - 50), min(255, max(v_values) + 50))

        lower_red = np.array([h_range[0], s_range[0], v_range[0]])
        upper_red = np.array([h_range[1], s_range[1], v_range[1]])

        # 读取图片
        image = cv2.imread(image_path)  
        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv_image, lower_red, upper_red)

        # 保存掩膜图片
        cv2.imwrite(save_path, mask)
    