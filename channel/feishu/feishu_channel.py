"""
飞书通道接入

@author Saboteur7
@Date 2023/11/19
"""

# -*- coding=utf-8 -*-
import uuid

import requests
import web
from channel.feishu.feishu_message import FeishuMessage
from bridge.context import Context
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.singleton import singleton
from config import conf
from common.expired_dict import ExpiredDict
from bridge.context import ContextType
from channel.chat_channel import ChatChannel, check_prefix
from common import utils
import json
import os

URL_VERIFICATION = "url_verification"


@singleton
class FeiShuChanel(ChatChannel):
    feishu_app_id = conf().get('feishu_app_id')
    feishu_app_secret = conf().get('feishu_app_secret')
    feishu_token = conf().get('feishu_token')

    def __init__(self):
        super().__init__()
        # 历史消息id暂存，用于幂等控制
        self.receivedMsgs = ExpiredDict(60 * 60 * 7.1)
        logger.info("[FeiShu] app_id={}, app_secret={} verification_token={}".format(
            self.feishu_app_id, self.feishu_app_secret, self.feishu_token))
        # 无需群校验和前缀
        conf()["group_name_white_list"] = ["ALL_GROUP"]
        conf()["single_chat_prefix"] = [""]

    def startup(self):
        urls = (
            '/', 'channel.feishu.feishu_channel.FeishuController'
        )
        app = web.application(urls, globals(), autoreload=False)
        port = conf().get("feishu_port", 9891)
        web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", port))

    def send(self, reply: Reply, context: Context):
        msg = context.get("msg")
        is_group = context["isgroup"]
        if msg:
            access_token = msg.access_token
        else:
            access_token = self.fetch_access_token()
        headers = {
            "Authorization": "Bearer " + access_token,
            "Content-Type": "application/json",
        }
        msg_type = "text"
        logger.info(f"[FeiShu] start send reply message, type={context.type}, content={reply.content}")
        reply_content = reply.content
        content_key = "text"
        if reply.type == ReplyType.IMAGE_URL:
            # 图片上传
            reply_content = self._upload_image_url(reply.content, access_token)
            if not reply_content:
                logger.warning("[FeiShu] upload file failed")
                return
            msg_type = "image"
            content_key = "image_key"
        if is_group:
            # 群聊中直接回复
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{msg.msg_id}/reply"
            data = {
                "msg_type": msg_type,
                "content": json.dumps({content_key: reply_content})
            }
            res = requests.post(url=url, headers=headers, json=data, timeout=(5, 10))
        else:
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            params = {"receive_id_type": context.get("receive_id_type") or "open_id"}
            data = {
                "receive_id": context.get("receiver"),
                "msg_type": msg_type,
                "content": json.dumps({content_key: reply_content})
            }
            res = requests.post(url=url, headers=headers, params=params, json=data, timeout=(5, 10))
        res = res.json()
        if res.get("code") == 0:
            logger.info(f"[FeiShu] send message success")
        else:
            logger.error(f"[FeiShu] send message failed, code={res.get('code')}, msg={res.get('msg')}")


    def fetch_access_token(self) -> str:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
        headers = {
            "Content-Type": "application/json"
        }
        req_body = {
            "app_id": self.feishu_app_id,
            "app_secret": self.feishu_app_secret
        }
        data = bytes(json.dumps(req_body), encoding='utf8')
        response = requests.post(url=url, data=data, headers=headers)
        if response.status_code == 200:
            res = response.json()
            if res.get("code") != 0:
                logger.error(f"[FeiShu] get tenant_access_token error, code={res.get('code')}, msg={res.get('msg')}")
                return ""
            else:
                return res.get("tenant_access_token")
        else:
            logger.error(f"[FeiShu] fetch token error, res={response}")


    def _upload_image_url(self, img_url, access_token):
        logger.debug(f"[FeiShu] start process image, img_url={img_url[:100]}...")
        
        # 检查是否是base64 data URL
        if img_url.startswith("data:image/"):
            # 处理base64格式的图片
            return self._upload_base64_image(img_url, access_token)
        else:
            # 处理普通URL图片
            response = requests.get(img_url)
            suffix = utils.get_path_suffix(img_url)
            temp_name = str(uuid.uuid4()) + "." + suffix
            if response.status_code == 200:
                # 将图片内容保存为临时文件
                with open(temp_name, "wb") as file:
                    file.write(response.content)

                # upload
                return self._upload_file_to_feishu(temp_name, access_token)
            else:
                logger.error(f"[FeiShu] download image failed, status_code={response.status_code}")
                return None

    def _upload_base64_image(self, data_url, access_token):
        """处理base64格式的图片数据"""
        try:
            import base64
            # 解析data URL: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...
            header, image_data = data_url.split(',', 1)
            # 获取图片格式
            if 'png' in header:
                suffix = 'png'
            elif 'jpeg' in header or 'jpg' in header:
                suffix = 'jpg'
            else:
                suffix = 'png'  # 默认为png
            
            # 解码base64数据
            image_bytes = base64.b64decode(image_data)
            
            # 创建临时文件
            temp_name = str(uuid.uuid4()) + "." + suffix
            with open(temp_name, "wb") as file:
                file.write(image_bytes)
            
            logger.info(f"[FeiShu] base64 image saved to temp file: {temp_name}")
            
            # 上传文件
            return self._upload_file_to_feishu(temp_name, access_token)
            
        except Exception as e:
            logger.error(f"[FeiShu] process base64 image failed: {e}")
            return None

    def _upload_file_to_feishu(self, temp_file_path, access_token):
        """上传文件到飞书"""
        upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
        data = {
            'image_type': 'message'
        }
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            with open(temp_file_path, "rb") as file:
                upload_response = requests.post(upload_url, files={"image": file}, data=data, headers=headers)
                logger.info(f"[FeiShu] upload file response: {upload_response.status_code}")
                
                # 删除临时文件
                os.remove(temp_file_path)
                
                if upload_response.status_code == 200:
                    result = upload_response.json()
                    if result.get("code") == 0:
                        return result.get("data", {}).get("image_key")
                    else:
                        logger.error(f"[FeiShu] upload failed: {result}")
                        return None
                else:
                    logger.error(f"[FeiShu] upload request failed: {upload_response.text}")
                    return None
        except Exception as e:
            logger.error(f"[FeiShu] upload file failed: {e}")
            # 确保删除临时文件
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return None



class FeishuController:
    # 类常量
    FAILED_MSG = '{"success": false}'
    SUCCESS_MSG = '{"success": true}'
    MESSAGE_RECEIVE_TYPE = "im.message.receive_v1"

    def GET(self):
        return "Feishu service start success!"

    def POST(self):
        try:
            channel = FeiShuChanel()

            request = json.loads(web.data().decode("utf-8"))
            logger.debug(f"[FeiShu] receive request: {request}")

            # 1.事件订阅回调验证
            if request.get("type") == URL_VERIFICATION:
                varify_res = {"challenge": request.get("challenge")}
                return json.dumps(varify_res)

            # 2.消息接收处理
            # token 校验
            header = request.get("header")
            if not header or header.get("token") != channel.feishu_token:
                return self.FAILED_MSG

            # 处理消息事件
            event = request.get("event")
            if header.get("event_type") == self.MESSAGE_RECEIVE_TYPE and event:
                if not event.get("message") or not event.get("sender"):
                    logger.warning(f"[FeiShu] invalid message, msg={request}")
                    return self.FAILED_MSG
                msg = event.get("message")

                # 幂等判断
                if channel.receivedMsgs.get(msg.get("message_id")):
                    logger.warning(f"[FeiShu] repeat msg filtered, event_id={header.get('event_id')}")
                    return self.SUCCESS_MSG
                channel.receivedMsgs[msg.get("message_id")] = True

                is_group = False
                chat_type = msg.get("chat_type")
                if chat_type == "group":
                    if not msg.get("mentions") and msg.get("message_type") == "text":
                        # 群聊中未@不响应
                        return self.SUCCESS_MSG
                    if msg.get("mentions")[0].get("name") != conf().get("feishu_bot_name") and msg.get("message_type") == "text":
                        # 不是@机器人，不响应
                        return self.SUCCESS_MSG
                    # 群聊
                    is_group = True
                    receive_id_type = "chat_id"
                elif chat_type == "p2p":
                    receive_id_type = "open_id"
                else:
                    logger.warning("[FeiShu] message ignore")
                    return self.SUCCESS_MSG
                # 构造飞书消息对象
                feishu_msg = FeishuMessage(event, is_group=is_group, access_token=channel.fetch_access_token())
                if not feishu_msg:
                    return self.SUCCESS_MSG

                context = self._compose_context(
                    feishu_msg.ctype,
                    feishu_msg.content,
                    channel=channel,
                    isgroup=is_group,
                    msg=feishu_msg,
                    receive_id_type=receive_id_type,
                    no_need_at=True
                )
                if context:
                    channel.produce(context)
                logger.info(f"[FeiShu] query={feishu_msg.content}, type={feishu_msg.ctype}")
            return self.SUCCESS_MSG

        except Exception as e:
            logger.error(e)
            return self.FAILED_MSG

    def _compose_context(self, ctype: ContextType, content, **kwargs):
        context = Context(ctype, content)
        context.kwargs = kwargs
        if "origin_ctype" not in context:
            context["origin_ctype"] = ctype

        # 获取channel实例
        channel = kwargs.get("channel")
        
        cmsg = context["msg"]
        context["session_id"] = cmsg.from_user_id
        context["receiver"] = cmsg.other_user_id

        if ctype == ContextType.TEXT:
            # 1.文本请求
            # 图片生成处理
            img_match_prefix = check_prefix(content, conf().get("image_create_prefix"))
            if img_match_prefix:
                content = content.replace(img_match_prefix, "", 1)
                context.type = ContextType.IMAGE_CREATE
                
                # 先发送画图提示消息
                prompt_content = content.strip()
                tip_message = f"🎨 正在使用 gpt-image-1 为您绘画，请稍候...\n提示词：{prompt_content}"
                
                # 创建提示回复并立即发送
                tip_reply = Reply(ReplyType.TEXT, tip_message)
                tip_context = Context(ContextType.TEXT, tip_message)
                tip_context.kwargs = kwargs
                tip_context["session_id"] = cmsg.from_user_id
                tip_context["receiver"] = cmsg.other_user_id
                
                # 使用channel实例发送提示消息
                if channel:
                    channel.send(tip_reply, tip_context)
                
            else:
                context.type = ContextType.TEXT
            context.content = content.strip()

        elif context.type == ContextType.VOICE:
            # 2.语音请求
            if "desire_rtype" not in context and conf().get("voice_reply_voice"):
                context["desire_rtype"] = ReplyType.VOICE

        return context
