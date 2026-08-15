# -*- coding: utf-8 -*-
"""配置加载工具（阶段2）。

优先用 PyYAML；未安装时降级到内置的极简YAML解析器（只支持本项目
config.yaml / coach_persona.yaml 用到的子集：嵌套dict、标量、行内列表、
"- "列表、注释）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"
PERSONA_PATH = BASE_DIR / "config" / "coach_persona.yaml"

# 本地密钥文件（项目根目录，与coach/同级）：纯文本 KEY=VALUE 格式，方便
# 不想用终端export的用户直接编辑。已在.gitignore中排除，切勿提交/分享。
SECRETS_PATH = BASE_DIR.parent / "secrets.local.txt"


def load_local_secrets(path: Path = SECRETS_PATH) -> None:
    """把secrets.local.txt里的KEY=VALUE行注入os.environ（不覆盖已有的环境变量）。

    找不到文件/文件为空时静默跳过——终端手动export的用法依然完全兼容。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and value != "your-key-here":
            os.environ.setdefault(key, value)


def _parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if s == "" or s in ("null", "~", "None"):
        return None
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_parse_scalar(x) for x in inner.split(",")] if inner else []
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        out: dict[str, Any] = {}
        for part in inner.split(","):
            if ":" in part:
                k, _, v = part.partition(":")
                out[k.strip()] = _parse_scalar(v)
        return out
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _strip_comment(line: str) -> str:
    """去掉行尾注释（不处理引号内#的极端情况——本项目配置无此用法）。"""
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            return line[:i]
    return line


def _mini_yaml(text: str) -> dict[str, Any]:
    """极简YAML解析（缩进嵌套dict + 标量 + "- "列表 + 行内列表）。"""
    root: dict[str, Any] = {}
    # 栈帧：(缩进, 容器dict, 该帧的占位key或None)
    stack: list[tuple[int, dict[str, Any], str | None]] = [(-1, root, None)]
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        content = line.strip()
        if content.startswith("- "):
            # 列表项：归属于最近的"key:"占位帧
            while len(stack) > 1 and indent <= stack[-1][0]:
                stack.pop()
            _, container, pending = stack[-1]
            if pending is None and len(stack) > 1 and not container:
                # 顶帧是空的dict候选帧 → 列表实际归属其下的占位帧
                _, container, pending = stack[-2]
            if pending is not None:
                if not isinstance(container.get(pending), list):
                    container[pending] = []
                container[pending].append(_parse_scalar(content[2:]))
            continue
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        _, container, _ = stack[-1]
        key, _, rest = content.partition(":")
        key, rest = key.strip(), rest.strip()
        if rest == "":
            # 占位：既可能展开为dict，也可能展开为列表
            child: dict[str, Any] = {}
            container[key] = child
            stack.append((indent, container, key))
            stack.append((indent, child, None))
        else:
            container[key] = _parse_scalar(rest)
    _fix_empty(root)
    return root


def _fix_empty(node: Any) -> None:
    """空dict占位（key:后无内容）转为None，与YAML语义一致。"""
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if isinstance(v, dict) and not v:
                node[k] = None
            else:
                _fix_empty(v)
    elif isinstance(node, list):
        for x in node:
            _fix_empty(x)


def load_yaml(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return _mini_yaml(text)


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        return load_yaml(CONFIG_PATH)
    return {}


def load_persona() -> dict[str, Any]:
    if PERSONA_PATH.exists():
        return load_yaml(PERSONA_PATH)
    return {}
