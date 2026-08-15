# -*- coding: utf-8 -*-
"""LLM客户端（阶段2）。

tech spec 2.x：核心AI引擎选型 DeepSeek API / 通义千问 API，两者均提供
OpenAI兼容的 /chat/completions 接口，因此这里只实现一个OpenAI兼容客户端，
通过 config.yaml 的 llm 段切换供应商（预留多模型切换能力，对应风险表
"LLM API稳定性"一项）。

- 文本模型：复盘点评/周报/自由对话（DeepSeek不支持视觉，默认走文本模型）
- 视觉模型：HUD KDA读数、战绩截图OCR（如 qwen-vl 系列，走 vision 段配置）

纯标准库实现（urllib），不引入openai sdk依赖。
未配置API key时 from_config() 返回 None，上层进入降级模式（规则输出，
不编造AI点评）。
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


class LLMError(RuntimeError):
    """LLM调用失败（网络/鉴权/响应格式）。"""


class LLMClient:
    """OpenAI兼容 chat completions 客户端。"""

    def __init__(self, base_url: str, model: str, api_key: str,
                 timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict[str, Any],
                    vision: bool = False,
                    section: str | None = None) -> Optional["LLMClient"]:
        """从config.yaml的llm段构造。未配置key/model时返回None（降级模式）。

        config.yaml 结构：
        llm:
          base_url: "https://api.deepseek.com/v1"
          model: "deepseek-chat"
          api_key_env: "COACH_LLM_API_KEY"
          vision:
            base_url: "https://ws-xxxxx.<region>.maas.aliyuncs.com/compatible-mode/v1"
            model: "qwen3-vl-plus"
            api_key_env: "COACH_VLM_API_KEY"   # 缺省回落到llm.api_key_env
          vision_fallback:                     # 可选：vision主力失败时兜底
            base_url: "https://api.openai.com/v1"
            model: "gpt-4o-mini"
            api_key_env: "OPENAI_API_KEY"

        section: 显式指定要读取的子段名（如 "vision_fallback"），优先于vision参数；
        不传就沿用vision=True/False的老行为（读"vision"或顶层）。
        """
        llm_cfg = (config or {}).get("llm") or {}
        section_name = section if section is not None else ("vision" if vision else None)
        if section_name:
            v = llm_cfg.get(section_name) or {}
            base_url = v.get("base_url") or llm_cfg.get("base_url")
            model = v.get("model")
            key_env = v.get("api_key_env") or llm_cfg.get("api_key_env") or ""
            timeout_sec = v.get("timeout_sec") or llm_cfg.get("timeout_sec")
        else:
            base_url = llm_cfg.get("base_url")
            model = llm_cfg.get("model")
            key_env = llm_cfg.get("api_key_env") or ""
            timeout_sec = llm_cfg.get("timeout_sec")
        api_key = os.environ.get(key_env, "") if key_env else ""
        if not (base_url and model and api_key):
            return None
        return cls(base_url=base_url, model=model, api_key=api_key,
                   timeout=int(timeout_sec or 120))

    # ------------------------------------------------------------------
    # 调用
    # ------------------------------------------------------------------

    def chat(self, messages: list[dict[str, Any]], temperature: float = 0.7,
             max_tokens: int = 2000) -> str:
        """发送对话，返回助手文本。失败抛LLMError。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise LLMError(f"LLM HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise LLMError(f"LLM调用失败: {e}") from e
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"LLM响应格式异常: {json.dumps(body)[:500]}") from e

    def chat_text(self, system: str, user: str,
                  temperature: float = 0.7) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return self.chat(messages, temperature=temperature)

    def chat_image(self, prompt: str, image_path: str | Path,
                   temperature: float = 0.0) -> str:
        """图片+文字（OpenAI vision消息格式，qwen-vl兼容模式可用）。"""
        p = Path(image_path)
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }]
        return self.chat(messages, temperature=temperature, max_tokens=500)


class VisionClient:
    """视觉客户端外壳：主视觉模型失败时自动切换到备用视觉模型。

    背景：项目一度只配了通义千问(DashScope)一个视觉源，中间踩过账号未开通/
    模型未购买(AccessDenied.Unpurchased)之类的坑，导致视觉功能整个不可用。
    加一个独立厂商的兜底（默认OpenAI gpt-4o-mini）之后，Qwen那边出问题时
    HUD/KDA读数和OCR不会跟着全部瘫痪。

    对外接口只有 chat_image()，跟 LLMClient.chat_image 签名一致，
    ocr_adapter.py / video_utils.py 等调用方完全不需要改代码。
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient | None = None):
        self.primary = primary
        self.fallback = fallback

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Optional["VisionClient"]:
        primary = LLMClient.from_config(config, section="vision")
        fallback = LLMClient.from_config(config, section="vision_fallback")
        if primary is None and fallback is None:
            return None
        if primary is None:
            # 只配了兜底、没配主力：直接把兜底当主力用，别浪费这个key
            return cls(primary=fallback, fallback=None)
        return cls(primary=primary, fallback=fallback)

    def chat_image(self, prompt: str, image_path: str | Path,
                   temperature: float = 0.0) -> str:
        try:
            return self.primary.chat_image(prompt, image_path, temperature=temperature)
        except LLMError as primary_err:
            if self.fallback is None:
                raise
            try:
                return self.fallback.chat_image(prompt, image_path, temperature=temperature)
            except LLMError as fallback_err:
                raise LLMError(
                    f"主视觉模型({self.primary.model})失败: {primary_err}；"
                    f"兜底视觉模型({self.fallback.model})也失败: {fallback_err}"
                ) from fallback_err


def extract_json(text: str) -> Any:
    """从LLM输出里提取第一个JSON对象/数组（容忍```json围栏和前后废话）。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(s)):
            if s[i] == opener:
                depth += 1
            elif s[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start:i + 1])
                    except json.JSONDecodeError:
                        break
        # 尝试下一种括号
    raise ValueError(f"未能从LLM输出中解析JSON: {text[:200]}")
