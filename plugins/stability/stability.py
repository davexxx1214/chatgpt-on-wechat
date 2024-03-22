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
from langdetect import detect
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
            self.rmbg_url = self.config.get("rmbg_url","")
            self.rmbg_prefix = self.config.get("rmbg_prefix", "去背景")
            self.api_key = self.config.get("api_key", "")
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

            logger.info('Added new user to params_cache. user id = ' + user_id)

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

            elif content.startswith(self.rmbg_prefix):
                self.params_cache[user_id]['rmbg_quota'] = 1
                tip = f"💡已经开启图片消除背景服务，请再发送一张图片进行处理"
                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.doodle_prefix):
                # Call new function to handle search operation
                pattern = self.doodle_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了doodle的指令
                    doodle_prompt = content[len(self.doodle_prefix):].strip()
                    if self.is_chinese(doodle_prompt):
                        doodle_prompt = self.translate_to_english(doodle_prompt)
                    logger.info(f"doodle_prompt = : {doodle_prompt}")

                    self.params_cache[user_id]['doodle_prompt'] = doodle_prompt
                    self.params_cache[user_id]['doodle_quota'] = 1
                    tip = f"💡已经开启涂鸦修图模式，请将涂鸦后的图片发送给我。(仅支持微信里的红色涂鸦)"

                else:
                    tip = f"💡欢迎使用涂鸦修图服务，指令格式为:\n\n{self.upscale_prefix}+ 空格 + 涂鸦替换成的内容（用英文效果更好）。\n例如：涂鸦修图 3D cute monsters "

                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.upscale_prefix):
                # Call new function to handle search operation
                pattern = self.upscale_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了upscale的指令
                    upscale_prompt = content[len(self.upscale_prefix):].strip()
                    if self.is_chinese(upscale_prompt):
                        upscale_prompt = self.translate_to_english(upscale_prompt)
                    logger.info(f"upscale_prompt = : {upscale_prompt}")

                    self.params_cache[user_id]['upscale_prompt'] = upscale_prompt
                    self.params_cache[user_id]['upscale_quota'] = 1
                    tip = f"💡已经开启图片高清化服务，请再发送一张图片进行处理(分辨率低于1024*1024)"

                else:
                    tip = f"💡欢迎使用图片高清化服务，高清化指令格式为:\n\n{self.upscale_prefix}+ 空格 + 有侧重点的详细描述\n\n(注意:仅支持分辨率低于1024*1024的图片)"

                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

        elif context.type == ContextType.IMAGE:
            if self.params_cache[user_id]['inpaint_quota'] < 1 and self.params_cache[user_id]['upscale_quota'] < 1 and self.params_cache[user_id]['repair_quota'] < 1 and self.params_cache[user_id]['doodle_quota'] < 1 and self.params_cache[user_id]['rmbg_quota'] < 1:
                logger.info("on_handle_context: 当前用户识图配额不够，不进行识别")
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
            
            if self.params_cache[user_id]['doodle_quota'] > 0:
                self.params_cache[user_id]['doodle_quota'] = 0
                self.call_doodle_service(image_path, user_id, e_context)

            if self.params_cache[user_id]['rmbg_quota'] > 0:
                self.params_cache[user_id]['rmbg_quota'] = 0
                self.call_rmbg_service(image_path, user_id, e_context)

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
            headers={"authorization": f"Bearer {self.api_key}"},
            files={"image": open(image_path, "rb")},
            data={
                "prompt": prompt,
                "mode": "search",
                "search_prompt": search_prompt,
                "output_format": "jpeg",
            },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "stability" + str(uuid.uuid4()) + ".jpg" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_jpeg(response.content)
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
            rc= "服务暂不可用,可能是某些关键字没有通过安全审查"
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
                "Accept": "image/png",
                "Authorization": f"Bearer {self.api_key}"
            },
            files={
                "image": open(image_path, "rb")
            },
            data={
                "width": 1024,
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
            headers={"authorization": f"Bearer {self.api_key}"},

            files={
                'image': open(image_path, 'rb'),
                'mask': open("./mask.png", 'rb'),
            },
            data={
                "prompt": doodle_prompt,
                "mode": "mask",
                "output_format": "jpeg",
            },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "doodle" + str(uuid.uuid4()) + ".jpg" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE

            image = self.img_to_jpeg(response.content)
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
            rc= "服务暂不可用,可能是某些关键字没有通过安全审查"
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

            image = self.img_to_jpeg(response.content)
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
        


    def call_upscale_service(self, image_path, user_id, e_context):
        logger.info(f"calling upscale service")

        upscale_prompt = self.params_cache[user_id]['upscale_prompt']        

        response = requests.post(
            f"{self.upscale_url}",
            headers={
                "authorization": f"Bearer {self.api_key}"
            },
            files={
                "image": open(image_path, "rb")
            },
            data={
                "prompt": upscale_prompt,
                "output_format": "jpeg",
            },
        )

        if response.json().get('errors') is not None:
            rc= "图片高清化失败,可能是图片分辨率太高"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] upscale service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

        elif response.json().get('id') is not None:
            task_id = response.json().get('id')
            logger.info(f"task id = {task_id}")
            status, msg, imgcontent = self.get_upscale_result(task_id)
            rt = ReplyType.TEXT
            rc = msg
            if not status:
                rt = ReplyType.ERROR
                rc = msg

            if status and imgcontent:
                rt = ReplyType.IMAGE
                image = self.img_to_jpeg(imgcontent)
                rc = image
                

            if not rc:
                rt = ReplyType.ERROR
                rc = "图片高清化失败"

            reply = Reply(rt, rc)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

        else:
            rc= "服务暂不可用,可能是某些关键字没有通过安全审查"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] upscale service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    # 轮询获取任务结果
    def get_upscale_result(self, task_id):
        start_time = time.time()  # 记录开始时间
        total_timeout = 60 * self.total_timeout  # 总超时时间

        try:
            headers = {
                'Accept': "image/*",  # Use 'application/json' to receive base64 encoded JSON
                'authorization': f"Bearer {self.api_key}"
            }
            url = f"{self.upscale_url}/result/{task_id}"
            status_code = -1

            while  status_code != 200 and status_code != 403:
                # 检查是否已经超过总超时时间
                if (time.time() - start_time) > total_timeout:
                    logger.debug("❌ 超过最大等待时间")
                    return False, "❌ 请求失败：超过最大等待时间", ""
                
                time.sleep(5)
                response = requests.get(url, headers=headers, timeout=60) # 注意单次请求也设了超时时间
                status_code = response.status_code
                logger.info(f"正在查询任务，id = {task_id}, status code = {status_code}")


            if status_code == 200:
                imgpath = TmpDir().path() + "upscale" + str(uuid.uuid4()) + ".jpg" 
                with open(imgpath, 'wb') as file:
                    file.write(response.content)
                logger.info(f"imgpath = {imgpath}")
                msg = "图片高清化成功"
                return True, msg, response.content
            elif status_code == 403:
                return False, "请求失败，可能是某些关键字没有通过安全审查", ""
            else:
                return False, "❌ 请求失败：服务异常", ""
        
        except Exception as e:
            logger.exception(e)
            return False, "❌ 请求失败", ""

    def is_chinese(self, text):
        try:
            lang = detect(text)
            return lang == 'zh-cn' or lang == 'zh-tw'
        except:
            return False

    def translate_to_english(self, text):
        
        return ts.translate_text(text, translator='alibaba')

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
    