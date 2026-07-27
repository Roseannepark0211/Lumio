"""Telegram Bot Service — 轮询 Bot API，接收用户发送的内容，写入 Inbox。"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from .utils.signal import QObject, Signal

from .models import InboxItem, TelegramDevice
from .utils.config import load_config, save_config
from .utils.database import get_engine, get_session_factory
from .utils.url_parser import parse_url

logger = logging.getLogger(__name__)

_MEDIA_DIR = Path.home() / ".lumio" / "inbox_media"


def _get_api_base() -> str:
    cfg = load_config()
    return cfg.get("telegram_api_base", "https://api.telegram.org").rstrip("/")


def _build_api_url(token: str, method: str) -> str:
    base = _get_api_base()
    return f"{base}/bot{token}/{method}"


class TelegramService(QObject):
    """Telegram Bot 轮询服务。"""

    sync_started = Signal()
    sync_stopped = Signal()
    item_received = Signal(str)      # inbox_item_id
    device_linked = Signal(str, str) # telegram_user_id, telegram_username
    device_unlinked = Signal(str)    # telegram_user_id

    def __init__(self, inbox_manager, parent=None):
        super().__init__(parent)
        self._inbox = inbox_manager
        self._running = False
        self._thread: threading.Thread | None = None
        self._offset = 0
        # 媒体组缓冲：{media_group_id: {"messages": [...], "timer": Timer}}
        self._media_groups: dict[str, dict] = {}
        self._media_group_lock = threading.Lock()
        self._migrate()

    # ── 数据库迁移 ──────────────────────────────────────────────────

    def _migrate(self):
        engine = get_engine()
        try:
            TelegramDevice.__table__.create(engine, checkfirst=True)
        except Exception as e:
            logger.debug("TG migrate: %s", e)

    # ── Token 验证 ──────────────────────────────────────────────────

    @staticmethod
    def validate_token(token: str, proxy: str = "") -> dict:
        """验证 Bot Token。返回 {"ok": True, "username": "..."} 或 {"ok": False, "error": "..."}。"""
        try:
            resp = _api_call(token, "getMe", proxy=proxy)
            if resp.get("ok"):
                return {"ok": True, "username": resp["result"]["username"]}
            return {"ok": False, "error": resp.get("description", "Unknown error")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 配对码 ──────────────────────────────────────────────────────

    def generate_pair_code(self) -> str:
        """生成配对码。"""
        code = f"{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
        # 保存到 config
        cfg = load_config()
        cfg["telegram_pair_code"] = code
        save_config(cfg)
        return code

    def get_bound_device(self) -> TelegramDevice | None:
        """获取已绑定的设备。"""
        session = get_session_factory()()
        try:
            device = session.query(TelegramDevice).first()
            if device:
                session.expunge(device)
            return device
        finally:
            session.close()

    def unlink_device(self, telegram_user_id: int) -> None:
        """解除绑定。"""
        session = get_session_factory()()
        try:
            session.query(TelegramDevice).filter_by(telegram_user_id=telegram_user_id).delete()
            session.commit()
            self.device_unlinked.emit(str(telegram_user_id))
        finally:
            session.close()

    # ── 轮询控制 ────────────────────────────────────────────────────

    def start_polling(self) -> None:
        if self._running:
            return
        # 修复双线程竞态：如果旧线程还在跑（stop_polling 的 5s join 超时未退出），
        # 等它真正退出再启新线程，避免两个线程并发处理同一批 updates
        if self._thread and self._thread.is_alive():
            logger.info("TG start_polling: 等待旧轮询线程退出...")
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                logger.warning("TG start_polling: 旧线程 15s 未退出，放弃启动新线程避免竞态")
                return
        cfg = load_config()
        token = cfg.get("telegram_bot_token", "")
        if not token:
            logger.warning("Telegram Bot Token 未配置")
            return
        self._offset = cfg.get("telegram_offset", 0)
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self.sync_started.emit()
        logger.info("Telegram 轮询已启动")

    def stop_polling(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            # join 时间从 5s 提升到 15s，给正在下载的大文件更多时间完成
            # （_download_tg_file 的 timeout 是 120s，但 _handle_update 内部检查
            # _running 后会尽快退出，实际等待通常 <10s）
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                logger.warning("TG stop_polling: 轮询线程 15s 后仍在运行（可能在下载大文件）")
        self.sync_stopped.emit()
        logger.info("Telegram 轮询已停止")

    def restart_polling(self) -> None:
        """重启轮询线程，让新的 config（token/proxy）立即生效。

        用于 Settings 页面修改 token/proxy 后无需重启 Lumio 即可应用。
        """
        was_running = self._running
        if was_running:
            self.stop_polling()
        # start_polling 内部会从 config 重新读取 token/offset
        cfg = load_config()
        if cfg.get("telegram_bot_token"):
            self.start_polling()
            logger.info("Telegram 轮询已重启（应用新配置）")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 轮询循环 ────────────────────────────────────────────────────

    def _poll_loop(self):
        # NOTE: config（token/proxy/interval）在循环内每次重新读取，
        # 这样用户在 Settings 页面修改代理/token 后无需重启即可生效。
        # 历史 bug：_poll_loop 启动时只读一次 config，若用户在轮询启动后
        # 才配置 http_proxy，轮询线程会一直用空 proxy，导致中国大陆访问
        # api.telegram.org 全部失败且无日志（offset 卡住不推进）。
        while self._running:
            try:
                cfg = load_config()
                token = cfg.get("telegram_bot_token", "")
                proxy = cfg.get("http_proxy", "")
                interval = cfg.get("telegram_poll_interval", 10)
                if not token:
                    logger.warning("TG poll: telegram_bot_token 为空，跳过")
                else:
                    self._poll_once(token, proxy)
            except Exception as e:
                logger.warning("TG poll error: %s", e)
            # 可中断等待
            for _ in range(int(interval) * 2):
                if not self._running:
                    return
                time.sleep(0.5)

    def _poll_once(self, token: str, proxy: str = "") -> None:
        resp = _api_call(token, "getUpdates", params={
            "offset": self._offset,
            "timeout": 5,
            "allowed_updates": '["message"]',
        }, proxy=proxy)

        if not resp.get("ok"):
            desc = resp.get("description", "unknown")
            # 区分 transient 错误（网络/代理偶发）和真正的 API 错误（401/409 等）
            # transient 错误下次轮询会自动恢复，降级为 INFO 避免 WARNING 日志噪音
            desc_lower = desc.lower()
            is_transient = any(k in desc_lower for k in
                               ("connection", "timeout", "reset", "aborted", "ssl", "proxy"))
            log_fn = logger.info if is_transient else logger.warning
            log_fn("TG getUpdates failed: %s (offset=%d, proxy=%s)",
                   desc, self._offset, proxy or "无")
            return

        last_ok_offset = self._offset
        for update in resp.get("result", []):
            # 优雅停止：处理完当前消息后检查 _running，下一条不再处理
            # 这样关闭开关/退出 Lumio 时，当前正在处理的消息能跑完，但不会继续处理后续消息
            if not self._running:
                logger.info("TG poll: _running=False, stop processing remaining updates")
                break
            update_id = update.get("update_id", 0)
            try:
                self._handle_update(token, update, proxy)
            except Exception as e:
                logger.warning("TG update %d failed: %s", update_id, e)
            # 无论成功失败都推进 offset，避免毒消息阻塞
            if update_id >= last_ok_offset:
                last_ok_offset = update_id + 1

        # 保存 offset
        if last_ok_offset > self._offset:
            self._offset = last_ok_offset
            cfg = load_config()
            cfg["telegram_offset"] = self._offset
            save_config(cfg)

    # ── 消息处理 ────────────────────────────────────────────────────

    def _handle_update(self, token: str, update: dict, proxy: str) -> None:
        msg = update.get("message")
        if not msg:
            return

        user_id = msg.get("from", {}).get("id", 0)
        username = msg.get("from", {}).get("username", "")
        chat_id = msg.get("chat", {}).get("id", 0)
        text = msg.get("text", "")
        caption = msg.get("caption", "")
        message_id = msg.get("message_id", 0)

        # 提取转发来源
        forward_from = ""
        fwd = msg.get("forward_from", {})
        if fwd:
            forward_from = fwd.get("username", "") or fwd.get("first_name", "")
        fwd_origin = msg.get("forward_origin", {})
        if fwd_origin and not forward_from:
            forward_from = fwd_origin.get("sender_user_name", "") or str(fwd_origin.get("sender_user_id", ""))

        # 命令处理
        if text.startswith("/"):
            self._handle_command(token, chat_id, user_id, username, text, proxy)
            return

        # 非命令消息：检查是否已绑定
        if not self._is_linked(user_id):
            _send_message(token, chat_id,
                "请先绑定设备后再使用 Lumio Inbox。\n\n"
                "使用 /link 进行绑定。", proxy)
            return

        # 统一内容提取
        content = text or caption or ""

        # 生成唯一 URL
        unique_url = f"telegram://message/{chat_id}/{message_id}"

        # 提取消息时间戳
        msg_date = msg.get("date", 0)
        post_time = ""
        if msg_date:
            post_time = datetime.fromtimestamp(msg_date, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

        # 媒体组检测：同一 media_group_id 的消息聚合后统一处理
        media_group_id = msg.get("media_group_id")
        if media_group_id:
            self._buffer_media_group(token, media_group_id, msg, chat_id, user_id, unique_url, content, forward_from, proxy, post_time)
            return

        # 判断内容类型
        item_id = None
        content_type = ""

        # 有媒体：优先处理媒体（URL 作为补充信息存入 content）
        if msg.get("photo"):
            item_id = self._process_photo(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "image"
        elif msg.get("video"):
            item_id = self._process_video(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "video"
        elif msg.get("video_note"):
            item_id = self._process_video_note(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "video"
        elif msg.get("animation"):
            item_id = self._process_animation(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "video"
        elif msg.get("sticker"):
            item_id = self._process_sticker(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "image"
        elif msg.get("voice"):
            item_id = self._process_voice(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "file"
        elif msg.get("audio"):
            item_id = self._process_audio(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "file"
        elif msg.get("document"):
            item_id = self._process_document(token, user_id, msg, unique_url, content, forward_from, proxy, post_time)
            content_type = "file"
        elif content and self._looks_like_url(content):
            # 纯链接消息
            url_match = re.search(r'https?://\S+', content)
            if url_match:
                item_id = self._process_url(user_id, url_match.group(), unique_url, content, forward_from, post_time)
                content_type = "link"
        elif content and content.strip():
            # 纯文本笔记
            item_id = self._process_note(user_id, content.strip(), unique_url, forward_from, post_time)
            content_type = "note"

        if item_id:
            logger.info("TG saved: type=%s id=%s url=%s", content_type, item_id, unique_url)
            self.item_received.emit(item_id)
            feedback = {
                "link": "已保存链接 📎",
                "image": "图片已保存 🖼",
                "video": "视频已保存 🎥",
                "file": "文件已保存 📁",
                "note": "已保存笔记 📝",
            }
            _send_message(token, chat_id, feedback.get(content_type, "已保存到 Lumio Inbox 📥"), proxy)
        elif content_type:
            # 识别了类型但处理失败（下载失败等）
            logger.warning("TG %s failed: msg_id=%d", content_type, message_id)
            _send_message(token, chat_id,
                f"内容识别为 {content_type}，但保存失败（可能下载超时）。请重试。", proxy)
        else:
            # 真正未识别的消息类型
            logger.warning("TG unrecognized: msg_id=%d text=%s caption=%s photo=%s video=%s video_note=%s animation=%s doc=%s",
                           message_id, bool(text), bool(caption),
                           bool(msg.get("photo")), bool(msg.get("video")),
                           bool(msg.get("video_note")), bool(msg.get("animation")),
                           bool(msg.get("document")))
            _send_message(token, chat_id,
                "无法识别该内容类型。\n\n"
                "请发送链接、文件或文本。", proxy)

        # 处理引用消息（reply_to_message）中的媒体
        # Telegram 的 quote/reply 机制：被引用消息的完整内容（含媒体）通过
        # reply_to_message 字段暴露。Bot API 不会自动处理这部分，需要单独提取。
        # 典型场景：用户回复一条带图片/视频的消息，bot 只处理了回复文本，
        # 漏掉了被引用消息里的媒体。
        reply_to = msg.get("reply_to_message")
        if reply_to:
            reply_media_types = [k for k in
                                 ("photo", "video", "video_note", "animation",
                                  "document", "audio", "voice", "sticker")
                                 if reply_to.get(k)]
            if reply_media_types:
                logger.info("TG reply_to_message has media: msg_id=%d reply_msg_id=%d types=%s",
                            message_id, reply_to.get("message_id", 0), reply_media_types)
                self._process_reply_to_message(token, reply_to, user_id, chat_id, proxy, post_time)

    def _process_reply_to_message(self, token: str, reply_msg: dict, user_id: int,
                                   chat_id: int, proxy: str, post_time: str = "") -> None:
        """处理被引用消息（reply_to_message）中的媒体。

        Telegram 的 quote/reply 机制：当用户回复或转发带引用的消息时，被引用消息
        的完整内容（包括媒体）通过 reply_to_message 字段暴露。Bot API 不会自动
        处理这部分，需要单独提取并保存。

        引用消息的 file_id 在私聊中可直接用 getFile 下载。
        """
        reply_msg_id = reply_msg.get("message_id", 0)
        reply_from_obj = reply_msg.get("from", {})
        # 跳过 bot 自己发的消息（避免把 bot 的保存确认反馈当引用媒体处理）
        if reply_from_obj.get("is_bot"):
            logger.debug("TG reply_to is bot message, skip: reply_msg_id=%d", reply_msg_id)
            return
        reply_from = reply_from_obj.get("username", "") or reply_from_obj.get("first_name", "")
        reply_caption = reply_msg.get("caption", "")
        # 用独立的 unique_url 避免和主消息冲突（InboxItem.url 是 unique）
        reply_unique_url = f"telegram://reply/{chat_id}/{reply_msg_id}"

        # 引用消息本身可能是相册的一部分（有 media_group_id）
        # 这种情况复杂，暂不聚合，按单条处理并记录日志
        if reply_msg.get("media_group_id"):
            logger.info("TG reply_to is part of media_group: reply_msg_id=%d group=%s (处理为单条)",
                        reply_msg_id, reply_msg.get("media_group_id"))

        item_id = None
        content_type = ""

        if reply_msg.get("photo"):
            item_id = self._process_photo(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "image"
        elif reply_msg.get("video"):
            item_id = self._process_video(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "video"
        elif reply_msg.get("video_note"):
            item_id = self._process_video_note(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "video"
        elif reply_msg.get("animation"):
            item_id = self._process_animation(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "video"
        elif reply_msg.get("document"):
            item_id = self._process_document(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "file"
        elif reply_msg.get("audio"):
            item_id = self._process_audio(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "file"
        elif reply_msg.get("voice"):
            item_id = self._process_voice(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "file"
        elif reply_msg.get("sticker"):
            item_id = self._process_sticker(token, user_id, reply_msg, reply_unique_url, reply_caption, reply_from, proxy, post_time)
            content_type = "image"

        if item_id:
            logger.info("TG reply media saved: type=%s id=%s reply_msg_id=%d", content_type, item_id, reply_msg_id)
            self.item_received.emit(item_id)
            _send_message(token, chat_id, f"已保存引用消息的{content_type} 📎", proxy)
        else:
            logger.warning("TG reply media process failed: reply_msg_id=%d type=%s", reply_msg_id, content_type)

    def _handle_command(self, token: str, chat_id: int, user_id: int, username: str, text: str, proxy: str) -> None:
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]

        if cmd == "/start":
            if self._is_linked(user_id):
                device = self._get_device(user_id)
                name = device.telegram_username if device else "unknown"
                _send_message(token, chat_id,
                    f"欢迎回来，Lumio Inbox。\n\n"
                    f"你的设备已连接（@{name}）\n"
                    f"你可以直接发送内容进行保存。", proxy)
            else:
                _send_message(token, chat_id,
                    "欢迎使用 Lumio Inbox。\n\n"
                    "你尚未绑定设备。\n\n"
                    "请使用 /link 进行设备配对。", proxy)

        elif cmd == "/link":
            if self._is_linked(user_id):
                device = self._get_device(user_id)
                name = device.telegram_username if device else "unknown"
                _send_message(token, chat_id,
                    f"你的设备已绑定（@{name}）。\n\n"
                    f"如需更换设备，请先使用 /unlink。", proxy)
                return
            if len(parts) < 2:
                _send_message(token, chat_id,
                    "请提供配对码。\n\n"
                    "示例：\n"
                    "/link ABCD-1234", proxy)
                return
            code = parts[1].strip()
            self._do_link(token, chat_id, user_id, username, code, proxy)

        elif cmd == "/unlink":
            if self._is_linked(user_id):
                self.unlink_device(user_id)
                _send_message(token, chat_id,
                    "设备已成功解绑。\n\n"
                    "你的数据不会被删除，但同步已停止。", proxy)
            else:
                _send_message(token, chat_id, "当前没有已绑定设备。", proxy)

        elif cmd == "/status":
            device = self._get_device(user_id)
            if device:
                last = device.last_sync_at or device.linked_at
                last_str = last.strftime("%Y-%m-%d %H:%M") if last else "—"
                _send_message(token, chat_id,
                    f"📊 Lumio Inbox 状态\n\n"
                    f"设备状态：已绑定\n"
                    f"设备名称：@{device.telegram_username or '未知'}\n"
                    f"用户ID：{device.telegram_user_id}\n\n"
                    f"同步状态：正常\n"
                    f"最后同步时间：{last_str}", proxy)
            else:
                _send_message(token, chat_id,
                    "📊 Lumio Inbox 状态\n\n"
                    "设备状态：未绑定\n"
                    "请使用 /link 绑定设备", proxy)

        elif cmd == "/help":
            _send_message(token, chat_id,
                "📌 Lumio Inbox 使用说明\n\n"
                "发送任意内容即可自动保存：\n\n"
                "✔ 链接\n"
                "✔ 视频\n"
                "✔ 文件\n"
                "✔ 文本\n\n"
                "命令列表：\n"
                "/start  启动系统\n"
                "/link   绑定设备\n"
                "/unlink 解绑设备\n"
                "/status 状态查询\n"
                "/help   帮助信息", proxy)

        else:
            _send_message(token, chat_id,
                f"未知命令：{cmd}\n\n"
                f"请输入 /help 查看可用命令。", proxy)

    def _do_link(self, token: str, chat_id: int, user_id: int, username: str, code: str, proxy: str) -> None:
        cfg = load_config()
        expected_code = cfg.get("telegram_pair_code", "")
        if not expected_code:
            _send_message(token, chat_id,
                "配对码无效或已过期。\n\n"
                "请重新在桌面端生成配对码。", proxy)
            return
        if code != expected_code:
            _send_message(token, chat_id,
                "配对码无效或已过期。\n\n"
                "请重新在桌面端生成配对码。", proxy)
            return

        session = get_session_factory()()
        try:
            # 更新或创建设备记录
            device = session.query(TelegramDevice).filter_by(telegram_user_id=user_id).first()
            if device:
                device.telegram_username = username
                device.linked_at = datetime.now(timezone.utc)
            else:
                device = TelegramDevice(
                    telegram_user_id=user_id,
                    telegram_username=username,
                    pair_code=code,
                )
                session.add(device)
            session.commit()
            self.device_linked.emit(str(user_id), username)
        finally:
            session.close()

        # 配对码不清除，保留供重新绑定使用
        _send_message(token, chat_id,
            f"设备绑定成功 🎉\n\n"
            f"已连接设备：@{username}\n\n"
            f"现在可以开始使用 Lumio Inbox。", proxy)

    # ── 媒体组聚合 ────────────────────────────────────────────────────

    def _buffer_media_group(self, token: str, group_id: str, msg: dict,
                            chat_id: int, user_id: int, unique_url: str,
                            content: str, forward_from: str, proxy: str, post_time: str = "") -> None:
        """缓冲同一 media_group_id 的消息，延迟 2 秒后统一处理。"""
        with self._media_group_lock:
            if group_id not in self._media_groups:
                self._media_groups[group_id] = {"messages": [], "timer": None}

            self._media_groups[group_id]["messages"].append({
                "msg": msg, "chat_id": chat_id, "user_id": user_id,
                "unique_url": unique_url, "content": content,
                "forward_from": forward_from, "proxy": proxy, "post_time": post_time,
            })

            # 重置定时器（每次新消息到达刷新 2 秒等待）
            if self._media_groups[group_id]["timer"]:
                self._media_groups[group_id]["timer"].cancel()

            timer = threading.Timer(2.0, self._flush_media_group, args=[token, group_id])
            timer.daemon = True
            timer.start()
            self._media_groups[group_id]["timer"] = timer

    def _flush_media_group(self, token: str, group_id: str) -> None:
        """聚合处理一个媒体组：下载所有文件到一个文件夹，创建一个 InboxItem。"""
        with self._media_group_lock:
            group = self._media_groups.pop(group_id, None)
        if not group:
            return

        messages = group["messages"]
        if not messages:
            return

        first = messages[0]
        caption = first["content"]
        forward_from = first["forward_from"]
        proxy = first["proxy"]
        post_time = first.get("post_time", "")

        # 创建组文件夹
        _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        group_dir = _MEDIA_DIR / f"album_{group_id}"
        group_dir.mkdir(parents=True, exist_ok=True)

        # 逐个下载并按序号命名（失败重试一次）
        downloaded = 0
        for idx, entry in enumerate(messages):
            msg = entry["msg"]
            file_path = None

            for attempt in range(2):
                if msg.get("video"):
                    fid = msg["video"]["file_id"]
                    raw_path = self._download_tg_file(token, fid, proxy, suffix=".mp4")
                    if raw_path:
                        file_path = group_dir / f"{idx + 1}.mp4"
                        Path(raw_path).rename(file_path)
                        break
                elif msg.get("photo"):
                    photos = msg["photo"]
                    photo = max(photos, key=lambda p: p.get("file_size", 0))
                    fid = photo["file_id"]
                    raw_path = self._download_tg_file(token, fid, proxy, suffix=".jpg")
                    if raw_path:
                        file_path = group_dir / f"{idx + 1}.jpg"
                        Path(raw_path).rename(file_path)
                        break
                elif msg.get("document"):
                    doc = msg["document"]
                    fid = doc["file_id"]
                    suffix = Path(doc.get("file_name", "")).suffix or ".bin"
                    raw_path = self._download_tg_file(token, fid, proxy, suffix=suffix)
                    if raw_path:
                        file_path = group_dir / f"{idx + 1}{suffix}"
                        Path(raw_path).rename(file_path)
                        break
                elif msg.get("audio"):
                    fid = msg["audio"]["file_id"]
                    raw_path = self._download_tg_file(token, fid, proxy, suffix=".mp3")
                    if raw_path:
                        file_path = group_dir / f"{idx + 1}.mp3"
                        Path(raw_path).rename(file_path)
                        break
                else:
                    logger.warning("TG media_group unsupported type: group=%s idx=%d", group_id, idx)
                    break

                if attempt == 0:
                    logger.info("TG media_group retry: group=%s idx=%d", group_id, idx)

            if file_path:
                downloaded += 1

        if downloaded == 0:
            logger.warning("TG media_group failed: group=%s no files downloaded", group_id)
            return

        # 创建一个 InboxItem，direct_url 指向文件夹
        unique_url = f"telegram://media_group/{group_id}"
        title = caption[:80] if caption else f"Album ({downloaded} files)"
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="image",
            title=title,
            author=forward_from or first["msg"].get("from", {}).get("username", ""),
            content=caption,
            post_time=post_time,
            platform="telegram",
        )
        self._update_item_file(item_id, str(group_dir))

        logger.info("TG media_group saved: group=%s files=%d id=%s", group_id, downloaded, item_id)
        self.item_received.emit(item_id)
        _send_message(token, first["chat_id"],
            f"已保存相册（{downloaded} 个文件）🖼", proxy)

    # ── 内容处理 ────────────────────────────────────────────────────

    def _is_linked(self, telegram_user_id: int) -> bool:
        return self._get_device(telegram_user_id) is not None

    def _get_device(self, telegram_user_id: int) -> TelegramDevice | None:
        session = get_session_factory()()
        try:
            device = session.query(TelegramDevice).filter_by(telegram_user_id=telegram_user_id).first()
            if device:
                session.expunge(device)
            return device
        finally:
            session.close()

    def _process_url(self, telegram_user_id: int, url: str, unique_url: str, content: str, forward_from: str, post_time: str = "") -> str | None:
        parsed = parse_url(url)
        platform = parsed.platform.value if parsed and parsed.platform.value != "unsupported" else ""
        author = forward_from or ""
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            platform=platform,
            title=content[:80] or url[:80],
            author=author,
            content=content,
            post_time=post_time,
        )
        if item_id:
            self._update_item_file(item_id, url)
        return item_id

    def _process_note(self, telegram_user_id: int, text: str, unique_url: str, forward_from: str, post_time: str = "") -> str | None:
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="note",
            title=text[:80],
            author=forward_from or "",
            content=text,
            post_time=post_time,
            platform="telegram",
        )
        return item_id

    def _process_photo(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        photos = msg.get("photo", [])
        if not photos:
            return None
        photo = max(photos, key=lambda p: p.get("file_size", 0))
        file_id = photo["file_id"]
        local_path = self._download_tg_file(token, file_id, proxy, suffix=".jpg")
        if not local_path:
            logger.warning("TG photo download failed: file_id=%s", file_id[:20])
            return None
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="image",
            title=content[:80] or "Telegram Photo",
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _process_video(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        video = msg.get("video")
        if not video:
            return None
        file_id = video["file_id"]
        local_path = self._download_tg_file(token, file_id, proxy, suffix=".mp4")
        if not local_path:
            logger.warning("TG video download failed: file_id=%s", file_id[:20])
            return None
        duration = video.get("duration", 0)
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="video",
            title=content[:80] or "Telegram Video",
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            duration=duration if duration else None,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _process_video_note(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        """处理圆视频（video_note）。"""
        vn = msg.get("video_note")
        if not vn:
            return None
        file_id = vn["file_id"]
        local_path = self._download_tg_file(token, file_id, proxy, suffix=".mp4")
        if not local_path:
            logger.warning("TG video_note download failed: file_id=%s", file_id[:20])
            return None
        duration = vn.get("duration", 0)
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="video",
            title=content[:80] or "Telegram Video Note",
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            duration=duration if duration else None,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _process_animation(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        """处理 GIF / 动图（animation）。"""
        anim = msg.get("animation")
        if not anim:
            return None
        file_id = anim["file_id"]
        suffix = ".mp4" if anim.get("mime_type", "").startswith("video") else ".gif"
        local_path = self._download_tg_file(token, file_id, proxy, suffix=suffix)
        if not local_path:
            logger.warning("TG animation download failed: file_id=%s", file_id[:20])
            return None
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="video",
            title=content[:80] or anim.get("file_name", "Telegram GIF"),
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            duration=anim.get("duration", 0) or None,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _process_sticker(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        """处理贴纸（sticker）。"""
        sticker = msg.get("sticker")
        if not sticker:
            return None
        file_id = sticker["file_id"]
        is_animated = sticker.get("is_animated", False)
        is_video = sticker.get("is_video", False)
        suffix = ".tgs" if is_animated else (".webm" if is_video else ".webp")
        local_path = self._download_tg_file(token, file_id, proxy, suffix=suffix)
        if not local_path:
            return None
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="image",
            title=content[:80] or "Telegram Sticker",
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _process_voice(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        """处理语音消息（voice）。"""
        voice = msg.get("voice")
        if not voice:
            return None
        file_id = voice["file_id"]
        local_path = self._download_tg_file(token, file_id, proxy, suffix=".ogg")
        if not local_path:
            return None
        duration = voice.get("duration", 0)
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="file",
            title=content[:80] or "Telegram Voice",
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            duration=duration if duration else None,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _process_audio(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        """处理音频文件（audio）。"""
        audio = msg.get("audio")
        if not audio:
            return None
        file_id = audio["file_id"]
        suffix = Path(audio.get("file_name", "")).suffix or ".mp3"
        local_path = self._download_tg_file(token, file_id, proxy, suffix=suffix)
        if not local_path:
            return None
        duration = audio.get("duration", 0)
        title = audio.get("title", "") or audio.get("file_name", "") or "Telegram Audio"
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="file",
            title=title[:80],
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            duration=duration if duration else None,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _process_document(self, token: str, telegram_user_id: int, msg: dict, unique_url: str, content: str, forward_from: str, proxy: str, post_time: str = "") -> str | None:
        doc = msg.get("document")
        if not doc:
            return None
        file_id = doc["file_id"]
        filename = doc.get("file_name", "document")
        suffix = Path(filename).suffix if "." in filename else ""
        local_path = self._download_tg_file(token, file_id, proxy, suffix=suffix)
        if not local_path:
            logger.warning("TG document download failed: file_id=%s", file_id[:20])
            return None
        item_id = self._inbox.add_item(
            url=unique_url,
            source="telegram",
            type_="file",
            title=filename,
            author=forward_from or msg.get("from", {}).get("username", ""),
            content=content,
            post_time=post_time,
            platform="telegram",
        )
        self._update_item_file(item_id, local_path)
        return item_id

    def _download_tg_file(self, token: str, file_id: str, proxy: str, suffix: str = "") -> str | None:
        """通过 Bot API 下载文件到本地。"""
        resp = _api_call(token, "getFile", params={"file_id": file_id}, proxy=proxy)
        if not resp.get("ok"):
            error = resp.get("description", "")
            if "file is too big" in error:
                logger.warning("TG file too big (>20MB): file_id=%s", file_id[:20])
            else:
                logger.warning("TG getFile failed: file_id=%s error=%s", file_id[:20], error)
            return None
        file_path = resp["result"]["file_path"]
        file_size = resp["result"].get("file_size", 0)
        base = _get_api_base()
        download_url = f"{base}/file/bot{token}/{file_path}"

        _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        local_path = _MEDIA_DIR / f"{uuid.uuid4().hex[:8]}{suffix}"

        try:
            proxies = {"https": proxy, "http": proxy} if proxy else None
            r = requests.get(download_url, stream=True, timeout=120, proxies=proxies)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return str(local_path)
        except Exception as e:
            logger.warning("TG file download failed: %s", e)
            return None

    def _update_item_file(self, item_id: str, local_path: str) -> None:
        """将下载的本地文件路径写入 InboxItem。"""
        session = get_session_factory()()
        try:
            item = session.query(InboxItem).get(item_id)
            if item:
                item.direct_url = local_path
                session.commit()
        finally:
            session.close()

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        return bool(re.search(r'https?://\S+', text.strip()))


# ── 辅助函数 ────────────────────────────────────────────────────────

def _api_call(token: str, method: str, params: dict = None, proxy: str = "") -> dict:
    url = _build_api_url(token, method)
    proxies = {"https": proxy, "http": proxy} if proxy else None
    # 连接超时 8s + 读取超时 20s（原 30s 太长，验证时用户会以为卡住）
    # 加一次重试：代理 long polling 偶发 ConnectionResetError(10054) 是正常的，
    # 重试一次可消除大部分 transient 错误，避免 WARNING 日志噪音。
    last_err = None
    for attempt in range(2):
        try:
            resp = requests.get(url, params=params or {}, timeout=(8, 20), proxies=proxies)
            return resp.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if attempt == 0:
                time.sleep(1.0)  # 短暂等待后重试
                continue
            # 重试仍失败：降级为 INFO（这是 transient 错误，下次轮询会自动恢复）
            logger.info("TG %s transient error (retry exhausted): %s", method, e)
            return {"ok": False, "description": str(e)}
        except Exception as e:
            return {"ok": False, "description": str(e)}
    return {"ok": False, "description": str(last_err) if last_err else "unknown"}


def _send_message(token: str, chat_id: int, text: str, proxy: str = "") -> None:
    resp = _api_call(token, "sendMessage", params={"chat_id": chat_id, "text": text}, proxy=proxy)
    if not resp.get("ok"):
        logger.warning("TG sendMessage failed: %s (chat_id=%d, proxy=%s)",
                       resp.get("description", "unknown"), chat_id, proxy or "无")
