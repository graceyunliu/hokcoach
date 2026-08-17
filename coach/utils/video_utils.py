# -*- coding: utf-8 -*-
"""视频分析工具（阶段0核心产出的正式归位处）。

死亡事件提取采用 tech spec 4.1.1（v1.2，AGE-44修订）方案：
    HUD KDA计数器60-90秒间隔粗采样 → 命中窗口后二分加密定位。
不做全视频scdet扫描（阶段0实测在实际算力下超时不可行，见 阶段0验证结论.md）。

管线分工：
- 本模块负责：采样调度、ffmpeg单帧解码+HUD区域裁剪、二分定位算法（含同一
  粗采样窗口内计数器跳变≥2的拆分定位）、HUD不可见帧的邻近重采。
- 计数器读数（从HUD裁剪图读出K/D/A三个数字）由调用方注入 ``kda_reader``
  （VLM或轻量OCR均可，阶段2接入LLM配置后提供默认实现）。读不出时返回None
  即视为该帧HUD不可见。

minimap英雄坐标提取：颜色阈值法（AGE-45：MVP不用YOLOv8），阶段2迁移。

HUD/minimap裁剪坐标与采样参数从 config.yaml 的 `video:` 节读取（AGE-49），
不再硬编码；config缺失/不完整时回落到验证素材（1290×2796竖屏录屏，解码帧
为横向）上标定出的默认值，保证脱离config也能跑（如单测、脚本直接调用）。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from utils import config_utils

# (K, D, A) 读数；None 表示该帧HUD不可见/读取失败
KDA = tuple[int, int, int]
KdaReader = Callable[[Path], Optional[KDA]]

# 复活倒计时读数：剩余秒数（int）；None 表示该帧未显示倒计时（未死亡/已复活）。
# 用作AGE-131第三特征（respawn-HUD共现），而非独立计数信号——见
# extract_death_location 中 respawn_reader 参数的说明。
RespawnReader = Callable[[Path], Optional[int]]

# 验证素材上标定出的兜底值（config.yaml缺失/字段不全时使用）。
_FALLBACK_HUD_CROP = {"x": 1650, "y": 0, "w": 650, "h": 140}
_FALLBACK_MINIMAP_CROP = {"x": 0, "y": 0, "w": 420, "h": 320}
# TODO(AGE-131 follow-up)：复活倒计时HUD区域坐标尚未在真实录屏上标定，
# 这里先给一个占位裁剪区（沿用HUD计数器同一竖直条带下方，倒计时通常在
# 死亡/复活状态下于屏幕中上部弹出）。respawn_reader接入前必须先用真实
# 素材标定实际坐标，否则该特征会因为裁剪区不对而恒返回None，等价于禁用。
_FALLBACK_RESPAWN_CROP = {"x": 1650, "y": 140, "w": 650, "h": 120}
_FALLBACK_COARSE_INTERVAL = 75.0
_FALLBACK_PRECISION = 3.0


def _load_video_config() -> dict[str, Any]:
    """读取config.yaml的video节；文件缺失/字段缺失/解析出错都静默回落。"""
    try:
        return config_utils.load_config().get("video") or {}
    except Exception:
        return {}


def _crop_from_config(key: str, fallback: dict[str, int]) -> dict[str, int]:
    cfg = _load_video_config().get(key)
    if not isinstance(cfg, dict):
        return dict(fallback)
    try:
        return {k: int(cfg[k]) for k in ("x", "y", "w", "h")}
    except (KeyError, TypeError, ValueError):
        return dict(fallback)


def _number_from_config(key: str, fallback: float) -> float:
    cfg = _load_video_config().get(key)
    try:
        return float(cfg) if cfg is not None else fallback
    except (TypeError, ValueError):
        return fallback


# 模块加载时从config读取一次，作为各函数的默认参数值；调用方仍可显式传参覆盖。
DEFAULT_HUD_CROP = _crop_from_config("hud_crop", _FALLBACK_HUD_CROP)
DEFAULT_MINIMAP_CROP = _crop_from_config("minimap_crop", _FALLBACK_MINIMAP_CROP)
DEFAULT_RESPAWN_CROP = _crop_from_config("respawn_crop", _FALLBACK_RESPAWN_CROP)
DEFAULT_COARSE_INTERVAL = _number_from_config("coarse_interval_sec", _FALLBACK_COARSE_INTERVAL)
DEFAULT_PRECISION = _number_from_config("precision_sec", _FALLBACK_PRECISION)

# HUD不可见时在邻近时刻重采的偏移序列（秒）
_RESAMPLE_OFFSETS = (1.0, -1.0, 2.0, -2.0, 4.0, -4.0)

# 死亡前基线帧的采样偏移（秒，相对锚点向前）。AGE-131复查：只取单帧
# （原实现只取death_ts-2.0）不足以覆盖"长期存在但逐帧轻微抖动/间歇出现"
# 的噪点源——真实录屏残留的8/62误报正是这类。取多帧并集显著加宽黑名单，
# 且成本只是每次死亡多解码2帧。
_BASELINE_OFFSETS = (2.0, 4.0, 6.0)


def respawn_crop_is_calibrated(crop: dict[str, int]) -> bool:
    """判断复活倒计时裁剪区是否已用真实素材标定过（AGE-131方案3的开关）。

    未标定时（仍等于_FALLBACK_RESPAWN_CROP占位值，含config.yaml里那份
    同值占位）返回False，调用方必须整体跳过方案3——否则占位坐标下
    respawn_reader恒返回None，会把所有真实死亡X标记都误判成噪点，
    把召回率打到接近0（见extract_death_location中该特征的说明）。
    """
    return dict(crop) != _FALLBACK_RESPAWN_CROP


def video_duration(video_path: str) -> float:
    """用ffprobe读取视频时长（秒）。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def grab_hud_frame(video_path: str, ts: float, out_path: Path,
                   crop: dict[str, int] = DEFAULT_HUD_CROP) -> Path:
    """在时刻ts解码单帧并裁剪HUD计数器区域，写入out_path。

    -ss 放在 -i 之前走关键帧快速seek，单帧解码成本很低（这正是本方案
    相对全视频scdet扫描的成本优势所在）。
    """
    vf = f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{max(ts, 0):.3f}", "-i", video_path,
         "-frames:v", "1", "-vf", vf, str(out_path)],
        check=True,
    )
    return out_path


def _read_kda_at(video_path: str, ts: float, kda_reader: KdaReader,
                 workdir: Path, crop: dict[str, int],
                 duration: float) -> Optional[KDA]:
    """读取时刻ts的KDA；HUD不可见时在邻近时刻重采（tech spec 4.1.1已知局限(2)）。"""
    for offset in (0.0, *_RESAMPLE_OFFSETS):
        t = min(max(ts + offset, 0.0), max(duration - 0.1, 0.0))
        frame = workdir / f"hud_{t:.3f}.png"
        try:
            grab_hud_frame(video_path, t, frame, crop)
        except subprocess.CalledProcessError:
            continue
        kda = kda_reader(frame)
        if kda is not None:
            return kda
    return None


def _bisect_one_death(read: Callable[[float], Optional[KDA]],
                      lo: float, hi: float, target_deaths: int,
                      precision: float) -> tuple[float, float]:
    """在(lo, hi]内二分定位死亡数首次达到target_deaths的时刻，收敛到precision秒。

    read(lo).deaths < target_deaths <= read(hi).deaths 为前置条件。
    中点读取失败（重采后仍不可见）时按"未达到"处理向右收敛，保守不丢事件。
    """
    while hi - lo > precision:
        mid = (lo + hi) / 2.0
        kda = read(mid)
        if kda is not None and kda[1] >= target_deaths:
            hi = mid
        else:
            lo = mid
    return lo, hi


def extract_death_events(
    video_path: str,
    kda_reader: KdaReader,
    coarse_interval: float = DEFAULT_COARSE_INTERVAL,
    precision: float = DEFAULT_PRECISION,
    hud_crop: dict[str, int] = DEFAULT_HUD_CROP,
) -> list[dict[str, Any]]:
    """从回放视频提取死亡事件列表（tech spec 4.1.1 v1.2方案）。

    步骤：
    1. 以coarse_interval为间隔粗采样，只解码+裁剪HUD计数器区域；
    2. 相邻可读采样点间死亡计数递增 → 命中候选窗口；
    3. 窗口内对每一次递增分别二分定位（跳变≥2时拆分），收敛到precision秒。

    Args:
        video_path: 回放视频路径。
        kda_reader: HUD裁剪图 → (K, D, A) 或 None（HUD不可见）。
        coarse_interval: 粗采样间隔（秒），spec建议60-90。
        precision: 二分收敛窗口（秒）。
        hud_crop: HUD计数器裁剪区域（默认从config.yaml的video.hud_crop读取）。

    Returns:
        按时间升序的事件列表，每项:
        {"ts": 定位窗口中点秒, "window": (lo, hi),
         "kda_before": (K,D,A), "kda_after": (K,D,A),
         "kill_traded": 该次死亡同窗口内击杀数是否同步增加（"换头"信号）}
    """
    duration = video_duration(video_path)
    events: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="coach_hud_") as tmp:
        workdir = Path(tmp)

        def read(ts: float) -> Optional[KDA]:
            return _read_kda_at(video_path, ts, kda_reader, workdir,
                                hud_crop, duration)

        # 1. 粗采样（跳过不可读点，窗口自然拉宽到下一个可读点）
        samples: list[tuple[float, KDA]] = []
        ts = 0.0
        while ts < duration:
            kda = read(ts)
            if kda is not None:
                samples.append((ts, kda))
            ts += coarse_interval
        if not samples or samples[-1][0] < duration - coarse_interval / 2:
            kda = read(duration - 1.0)
            if kda is not None:
                samples.append((duration - 1.0, kda))

        # 2+3. 找死亡计数递增的窗口，逐次二分定位
        for (t0, kda0), (t1, kda1) in zip(samples, samples[1:]):
            d0, d1 = kda0[1], kda1[1]
            lo = t0
            for target in range(d0 + 1, d1 + 1):
                lo, hi = _bisect_one_death(read, lo, t1, target, precision)
                kda_before = read(lo) or kda0
                kda_after = read(hi) or kda1
                events.append({
                    "ts": (lo + hi) / 2.0,
                    "window": (lo, hi),
                    "kda_before": kda_before,
                    "kda_after": kda_after,
                    "kill_traded": kda_after[0] > kda_before[0],
                })
                lo = hi  # 下一次递增只可能在其后

    return events


# ---------------------------------------------------------------------------
# Minimap英雄位置检测（阶段0验证方案：HSV颜色阈值+连通域面积过滤，AGE-45）
# ---------------------------------------------------------------------------

# 英雄头像圆环连通域面积（阶段0实测：英雄200-700px，图标类干扰项15-45px）
_MIN_ICON_AREA = 120
_MAX_ICON_AREA = 1500

# 一方最多5名英雄（物理上限）。AGE-130验证发现：真实录屏上偶尔会出现
# 与常规缩略minimap不同的画面（如玩家点开放大地图查看战况），此时防御塔/
# 野怪buff图标的颜色+面积会大量落入英雄阈值区间，static_zones也未必能
# 覆盖（这类画面出现频率低、位置和常规minimap不对应）。单方命中数超过5
# 本身就说明这帧不是可靠的常规minimap读数——诚实原则下应按"该帧不可靠/
# 无法读取"处理，而不是猜测其中哪些是真英雄。
_MAX_HEROES_PER_SIDE = 5

_ROW_NAMES = ("上", "中", "下")
_COL_NAMES = ("左", "中", "右")


def region_label(cx: float, cy: float, w: int, h: int) -> str:
    """minimap坐标 → 3×3粗粒度区域名（"左上"/"中路"级别即可，见实现计划阶段0）。"""
    col = _COL_NAMES[min(int(cx / w * 3), 2)]
    row = _ROW_NAMES[min(int(cy / h * 3), 2)]
    if row == "中" and col == "中":
        return "地图中部(中路/河道)"
    return f"{col}{row}区域"


def grab_minimap_frame(video_path: str, ts: float, out_path: Path,
                       crop: dict[str, int] = DEFAULT_MINIMAP_CROP) -> Path:
    """在时刻ts解码单帧并裁剪minimap区域。"""
    vf = f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{max(ts, 0):.3f}", "-i", video_path,
         "-frames:v", "1", "-vf", vf, str(out_path)],
        check=True,
    )
    return out_path


def grab_respawn_frame(video_path: str, ts: float, out_path: Path,
                       crop: dict[str, int] = DEFAULT_RESPAWN_CROP) -> Path:
    """在时刻ts解码单帧并裁剪复活倒计时HUD区域（AGE-131第三特征用）。"""
    vf = f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{max(ts, 0):.3f}", "-i", video_path,
         "-frames:v", "1", "-vf", vf, str(out_path)],
        check=True,
    )
    return out_path


# ---------------------------------------------------------------------------
# 固定UI元素（防御塔/buff图标/地图装饰）排除区探测（AGE-130 / AGE-131修复）
# ---------------------------------------------------------------------------
#
# 阶段2真实录屏验证发现：颜色阈值法把minimap上颜色/面积恰好落入阈值区间的
# 固定UI元素（防御塔crown图标、野怪/buff菱形图标、地图装饰纹理等）也当成
# 了英雄图标或死亡X标记，导致大量误报（AGE-130/AGE-131）。这些元素与
# 英雄/死亡标记的关键区别是"位置持续性"：英雄会移动，死亡X标记只在死亡
# 后短暂窗口内出现后消失；而防御塔等UI元素在同一像素位置长期不变。
#
# 用同一视频内多个时间点探测同色系连通域，位置跨采样点重复出现则视为
# "固定不动"，作为该视频的排除区，供detect_hero_icons/detect_death_marker
# 过滤。这样不需要为每份录屏重新标定颜色/面积阈值。

_STATIC_MATCH_RADIUS = 10.0  # px：两次探测视为"同一位置"的容差


def _cluster_positions(points: list[tuple[float, float]],
                       radius: float = _STATIC_MATCH_RADIUS
                       ) -> list[tuple[float, float, int]]:
    """把(cx,cy)点按邻近程度聚类，返回[(簇质心x, 簇质心y, 命中次数)]。"""
    clusters: list[list[float]] = []  # 每项 [sum_x, sum_y, n]
    for x, y in points:
        for c in clusters:
            mx, my = c[0] / c[2], c[1] / c[2]
            if (x - mx) ** 2 + (y - my) ** 2 <= radius ** 2:
                c[0] += x
                c[1] += y
                c[2] += 1
                break
        else:
            clusters.append([x, y, 1])
    return [(c[0] / c[2], c[1] / c[2], int(c[2])) for c in clusters]


def find_static_red_blue_zones(
    video_path: str,
    probe_ts: Optional[list[float]] = None,
    crop: dict[str, int] = DEFAULT_MINIMAP_CROP,
    min_hits: int = 3,
) -> list[tuple[float, float]]:
    """探测minimap裁剪区域内跨多个时间点位置不变的红/蓝色斑块。

    这些"固定不动"的斑块（防御塔、buff/野怪图标、地图装饰等）是
    AGE-130（英雄图标误报）/AGE-131（死亡X标记误报）的常见误报源——
    英雄会移动，死亡X标记只在死亡后短暂出现，两者都不会在多个相隔较远
    的时间点稳定出现在同一像素位置。

    Args:
        video_path: 回放视频路径。
        probe_ts: 探测用的采样时刻；默认在视频时长内均匀取6个点。
        crop: minimap裁剪区域。
        min_hits: 同一位置至少命中多少次探测才判定为"固定不动"（默认3）。

    Returns:
        [(cx, cy), ...] 固定UI元素位置列表（裁剪坐标系），供
        detect_hero_icons/detect_death_marker的exclude_zones参数使用。
    """
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "静态区域探测需要 opencv-python 与 numpy："
            "pip install opencv-python numpy"
        ) from e

    duration = video_duration(video_path)
    if probe_ts is None:
        n = 6
        probe_ts = [duration * (i + 1) / (n + 1) for i in range(n)]

    all_points: list[tuple[float, float]] = []
    with tempfile.TemporaryDirectory(prefix="coach_static_") as tmp:
        for i, t in enumerate(probe_ts):
            frame = Path(tmp) / f"probe_{i}.png"
            try:
                grab_minimap_frame(video_path, t, frame, crop)
            except subprocess.CalledProcessError:
                continue
            img = cv2.imread(str(frame))
            if img is None:
                continue
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            red = cv2.inRange(hsv, np.array([0, 90, 90]), np.array([10, 255, 255])) | \
                  cv2.inRange(hsv, np.array([170, 90, 90]), np.array([180, 255, 255]))
            blue = cv2.inRange(hsv, np.array([95, 90, 90]), np.array([130, 255, 255]))
            for mask in (red, blue):
                n_comp, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
                for j in range(1, n_comp):
                    if int(stats[j, cv2.CC_STAT_AREA]) < 20:  # 噪点不参与聚类
                        continue
                    cx, cy = centroids[j]
                    all_points.append((float(cx), float(cy)))

    clusters = _cluster_positions(all_points)
    return [(cx, cy) for cx, cy, count in clusters if count >= min_hits]


def _in_zones(cx: float, cy: float, zones: list[tuple[float, float]],
             radius: float = _STATIC_MATCH_RADIUS) -> bool:
    return any((cx - zx) ** 2 + (cy - zy) ** 2 <= radius ** 2 for zx, zy in zones)


def detect_hero_icons(minimap_image: Path,
                      crop: dict[str, int] = DEFAULT_MINIMAP_CROP,
                      exclude_zones: Optional[list[tuple[float, float]]] = None
                      ) -> dict[str, list[dict[str, Any]]]:
    """在minimap裁剪图上检测敌方（红环）/己方（蓝环）英雄图标。

    阶段0验证结论：敌我用红/蓝圆环颜色编码，HSV阈值+连通域面积过滤即可
    可靠区分，无需YOLOv8。隐身/草丛内英雄本就不可见（预期内"证据不足"）。

    阶段2真实录屏验证（AGE-130）发现该方案会把防御塔/buff图标等固定UI
    元素误判为英雄，用exclude_zones（见find_static_red_blue_zones）排除
    这些已知固定位置的干扰源。
    """
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "minimap检测需要 opencv-python 与 numpy："
            "pip install opencv-python numpy"
        ) from e

    img = cv2.imread(str(minimap_image))
    if img is None:
        raise ValueError(f"无法读取图片: {minimap_image}")
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # 红色跨HSV色相环两端
    red = cv2.inRange(hsv, np.array([0, 90, 90]), np.array([10, 255, 255])) | \
          cv2.inRange(hsv, np.array([170, 90, 90]), np.array([180, 255, 255]))
    blue = cv2.inRange(hsv, np.array([95, 90, 90]), np.array([130, 255, 255]))

    zones = exclude_zones or []

    def _components(mask) -> list[dict[str, Any]]:
        n, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
        out = []
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if _MIN_ICON_AREA <= area <= _MAX_ICON_AREA:
                cx, cy = centroids[i]
                if _in_zones(cx, cy, zones):
                    continue  # 固定UI元素（防御塔/图标），非英雄
                out.append({
                    "cx": float(cx), "cy": float(cy), "area": area,
                    "region": region_label(cx, cy, crop["w"], crop["h"]),
                })
        if len(out) > _MAX_HEROES_PER_SIDE:
            # 超过物理上限：这帧大概率不是常规minimap画面，识别结果不可信，
            # 按"不可见"处理（丢弃）而非猜测其中5个是真的。
            return []
        return out

    return {"enemies": _components(red), "allies": _components(blue)}


def extract_minimap_positions(
    video_path: str,
    around_ts: float,
    window_sec: float = 15.0,
    sample_interval: float = 3.0,
    crop: dict[str, int] = DEFAULT_MINIMAP_CROP,
    static_zones: Optional[list[tuple[float, float]]] = None,
) -> list[dict[str, Any]]:
    """提取around_ts前window_sec内敌方英雄的minimap大致位置轨迹。

    Args:
        static_zones: 该视频的固定UI元素排除区（见find_static_red_blue_zones）。
            未传入时自动探测一次（AGE-130修复）；同一视频多次调用本函数时，
            建议调用方预先算好并传入，避免重复探测的解码开销。

    Returns:
        按时间升序，每项:
        {"ts": 秒, "enemies": [{"cx","cy","area","region"}...],
         "enemy_visible_count": int, "ally_visible_count": int}
        敌方图标不可见（隐身/草丛/无视野）时enemies为空——这本身是可靠的
        "视野缺失"信号（阶段0验证结论二）。
    """
    if static_zones is None:
        static_zones = find_static_red_blue_zones(video_path, crop=crop)

    duration = video_duration(video_path)
    start = max(around_ts - window_sec, 0.0)
    end = min(around_ts, duration - 0.1)
    positions: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="coach_mm_") as tmp:
        ts = start
        while ts <= end + 1e-6:
            frame = Path(tmp) / f"mm_{ts:.3f}.png"
            try:
                grab_minimap_frame(video_path, ts, frame, crop)
                icons = detect_hero_icons(frame, crop, exclude_zones=static_zones)
            except (subprocess.CalledProcessError, ValueError):
                ts += sample_interval
                continue
            positions.append({
                "ts": ts,
                "enemies": icons["enemies"],
                "enemy_visible_count": len(icons["enemies"]),
                "ally_visible_count": len(icons["allies"]),
            })
            ts += sample_interval
    return positions


def summarize_minimap_context(positions: list[dict[str, Any]],
                              death_ts: float) -> str | None:
    """把minimap轨迹压缩成一句给分类器/复盘prompt用的中文摘要。

    诚实原则：看不见就说看不见，不推测（tech spec 4.1.3规则6）。
    """
    if not positions:
        return None
    parts = []
    for p in positions:
        rel = int(round(death_ts - p["ts"]))
        if p["enemy_visible_count"] == 0:
            parts.append(f"死亡前{rel}秒：小地图上敌方英雄均不可见（无视野）")
        else:
            regions = "、".join(sorted({e["region"] for e in p["enemies"]}))
            parts.append(f"死亡前{rel}秒：可见敌方{p['enemy_visible_count']}人"
                         f"（{regions}）")
    # 只保留首/中/尾三个采样点，避免prompt冗长
    if len(parts) > 3:
        parts = [parts[0], parts[len(parts) // 2], parts[-1]]
    return "；".join(parts)


# ---------------------------------------------------------------------------
# 死亡位置"X"标记检测（AGE-46：独立于敌方轨迹的高优先级死亡地点数据源）
# ---------------------------------------------------------------------------
#
# 阶段0验证发现：玩家死亡后，系统会在minimap上直接画一个红色"X"标出死亡
# 地点，并伴随复活倒计时——这比"从死亡前敌方轨迹反推死亡地点"更直接可靠，
# 见 tech spec 4.1.2。本节实现该标记的读取，输出作为death_location的
# 首选数据源；死亡前15秒敌方轨迹（summarize_minimap_context）保留作为
# 辅助上下文（推断"谁/怎么打死的"仍需要它），两者互补而非互相替代。
#
# 识别依据：X标记与英雄头像圆环共用红色色相，但形状不同——头像是实心圆环，
# 连通域接近其外接矩形面积（extent高）；X是两条交叉笔画，连通域内有大片
# 背景镂空（extent低）。用extent（面积/外接矩形面积）区分两者，不依赖
# 额外模型。

_MARKER_MIN_AREA = 30
_MARKER_MAX_AREA = 500
# 实心圆形图标extent实测约0.7-0.9；X交叉笔画extent明显更低，阈值取0.45
_MARKER_MAX_EXTENT = 0.45


def _death_marker_candidates(minimap_image: Path,
                             crop: dict[str, int] = DEFAULT_MINIMAP_CROP
                             ) -> list[dict[str, Any]]:
    """返回单帧minimap裁剪图上所有满足X标记面积/extent条件的候选连通域
    （未做exclude_zones过滤、未挑选最优），按extent升序排列。

    AGE-131复盘发现：符合"低extent红色小块"条件的候选在minimap顶部区域
    经常不止一个（多个持续存在的UI噪点），只排除其中extent最低的一个
    不够——detect_death_marker会退而选中下一个同样是噪点的候选。本函数
    把全部候选暴露出来，供extract_death_location的死亡前基线帧一次性
    排除所有已知噪点位置，而不只是排除"最像"的那一个。
    """
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "死亡标记检测需要 opencv-python 与 numpy："
            "pip install opencv-python numpy"
        ) from e

    img = cv2.imread(str(minimap_image))
    if img is None:
        raise ValueError(f"无法读取图片: {minimap_image}")
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, np.array([0, 90, 90]), np.array([10, 255, 255])) | \
          cv2.inRange(hsv, np.array([170, 90, 90]), np.array([180, 255, 255]))

    n, _, stats, centroids = cv2.connectedComponentsWithStats(red)
    candidates: list[dict[str, Any]] = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if not (_MARKER_MIN_AREA <= area <= _MARKER_MAX_AREA):
            continue
        bbox_area = int(stats[i, cv2.CC_STAT_WIDTH]) * int(stats[i, cv2.CC_STAT_HEIGHT])
        if bbox_area == 0:
            continue
        extent = area / bbox_area
        if extent > _MARKER_MAX_EXTENT:
            continue  # 太"实心"，更像英雄头像圆环而非X
        cx, cy = centroids[i]
        candidates.append({"cx": float(cx), "cy": float(cy), "area": area,
                           "extent": round(extent, 3),
                           "region": region_label(cx, cy, crop["w"], crop["h"])})
    candidates.sort(key=lambda c: c["extent"])
    return candidates


def detect_death_marker(minimap_image: Path,
                        crop: dict[str, int] = DEFAULT_MINIMAP_CROP,
                        exclude_zones: Optional[list[tuple[float, float]]] = None
                        ) -> Optional[dict[str, Any]]:
    """在单帧minimap裁剪图上检测系统自动标记的死亡位置红色"X"。

    与detect_hero_icons共用红色HSV阈值，但用extent（连通域面积/外接矩形
    面积）区分"X"（低extent，笔画间镂空）与英雄圆环图标（高extent，实心）。

    阶段2真实录屏验证（AGE-131）发现：某些固定UI元素（技能指示器/图标
    残影等）的extent也恰好落在X标记的范围内，且长期停留在同一位置——
    用exclude_zones（见find_static_red_blue_zones，或extract_death_location
    中死亡锚点之前的基线帧）排除这些已知固定位置的候选。

    注意本函数是**单帧原语**，不是死亡计数器：它只回答"这一帧上有没有
    符合X标记特征的候选"。把它按固定间隔在整段视频上循环调用来数死亡
    次数，会得到AGE-131里那个71%误报率的结果——真正的死亡次数只能由
    HUD计数器给出（extract_death_events），定位请走extract_death_location
    的锚定窗口路径。

    Returns:
        命中时: {"cx","cy","area","extent","region"}（取排除固定区域后
        extent最低的候选）
        未命中: None
    """
    zones = exclude_zones or []
    for c in _death_marker_candidates(minimap_image, crop):
        if _in_zones(c["cx"], c["cy"], zones):
            continue  # 固定位置的长期存在UI元素，非本次死亡产生的X标记
        return c  # 候选已按extent升序排列，第一个未被排除的即最优
    return None


def extract_death_location(
    video_path: str,
    death_ts: float,
    crop: dict[str, int] = DEFAULT_MINIMAP_CROP,
    search_window: float = 6.0,
    sample_interval: float = 1.0,
    static_zones: Optional[list[tuple[float, float]]] = None,
    respawn_reader: Optional[RespawnReader] = None,
    respawn_crop: dict[str, int] = DEFAULT_RESPAWN_CROP,
    death_window: Optional[tuple[float, float]] = None,
    *,
    allow_unanchored: bool = False,
) -> Optional[dict[str, Any]]:
    """在死亡时刻之后的窗口内寻找系统自动画出的死亡"X"标记（AGE-46）。

    X标记在角色死亡的瞬间出现并伴随复活倒计时持续显示，故从死亡时刻起
    （而非之前）向后采样；search_window默认6秒足以覆盖标记出现的延迟。

    设计前提（AGE-131修复的方案1，本次复查强制化）：本函数只在**已经由
    extract_death_events的HUD计数器确认过的单次死亡事件**窗口内调用，
    不做独立全视频扫描——真正的"这一局死了几次"由计数器递增次数决定，
    本函数只负责在已知的每一次死亡窗口内定位地点。这也是respawn_reader
    （方案3）不会造成重复计数的前提：倒计时可能持续显示长达30-40秒、
    跨越多个采样点，但因为本函数每次调用对应恰好一个已计数的死亡事件、
    且一旦确认立即return，倒计时的多次出现只会被用来"确认同一个事件"，
    不会被误当成多个事件。

    这个前提以前只写在注释里，无法阻止调用方把本函数当独立扫描器循环
    调用（AGE-131的44/62误报复现脚本正是这么用的）。现在改为在签名上
    强制：生产调用必须传入counter确认过的``death_window``，否则报错；
    研究/复现脚本要跑无锚点扫描必须显式写``allow_unanchored=True``，
    使这条路径既不会被误用成默认路径，也可被grep审计。

    传入death_window还带来一层实质精度提升：counter二分只能把死亡时刻
    收敛到(lo, hi]（默认precision=3秒），而``death_ts``是该窗口中点。
    真实死亡最早可能发生在lo，所以搜索应从lo而不是中点开始，基线帧
    也必须取在lo之前——否则"死亡前基线"可能其实已经在死亡之后，把真正
    的X标记自己加进了排除区。

    AGE-131修复（真实录屏验证发现两类误报源+一层新增确认特征）：

    1. 长期存在的固定UI噪点（如某个技能/图标残影，整个死亡前就已经在
       同一位置满足X标记的面积/extent条件）——取死亡锚点之前的若干帧
       （此时死亡尚未发生，minimap上不可能有真正的X标记），把这些帧上
       *所有*满足条件的候选位置（而不仅仅是extent最低的那一个：验证中
       发现同一帧常常有不止一个候选）都加入排除区，供窗口内检测排除。
       本次复查把基线从单帧扩为_BASELINE_OFFSETS多帧并集：残留的8/62
       误报源是长期存在、但位置逐帧轻微抖动/间歇出现的噪点，单帧基线
       只能排掉它"这一帧"的位置，多帧并集才能覆盖其抖动范围。
       此外与调用方可传入的全局static_zones（见find_static_red_blue_zones）
       合并使用。
       代价（诚实记录）：排除区是_STATIC_MATCH_RADIUS半径的圆，基线帧越多
       黑名单覆盖的minimap面积越大（实测每次死亡约20-30个点、约占裁剪区
       7%）。真实死亡地点恰好落在某个噪点位置10px内时会被连带漏检——
       这是"宁可漏一个地点也不编一个地点"的取舍（诚实原则，tech spec
       4.1.3规则6）：漏检时本函数返回None，下游退回死亡前敌方轨迹推断，
       而误报会直接给出一个错误的死亡地点。
    2. 逐帧闪烁的瞬时噪点（画面纹理/特效碎片，位置逐帧跳变，不像真正
       X标记那样在整个显示期间停留在同一像素位置）——命中后不立即采信，
       改为在+1秒处复核，位置仍在容差范围内才确认为真正的标记；否则视为
       噪点，从该帧起继续向后搜索。
    3.（新增，方案3）复核结果仍有约7/10的抽样误报（见AGE-131评论），说明
       仅靠位置持续性不够——真正的死亡X标记必定与复活倒计时HUD同时出现，
       而minimap上的噪点源不会。传入respawn_reader时，标记只有在同一
       时刻（ts）复活倒计时HUD也能读到数值（不为None）时才会被采信，
       否则视为噪点继续向后搜索。respawn_reader为可选参数（默认None）：
       未接入实现前退化为只用特征1+2，向后兼容。

    Args:
        death_ts: counter二分定位出的死亡时刻（窗口中点）。
        respawn_reader: 复活倒计时HUD裁剪图 → 剩余秒数(int) 或 None
            （倒计时未显示）。典型实现见make_vlm_respawn_reader。
        respawn_crop: 复活倒计时HUD裁剪区域（默认从config.yaml的
            video.respawn_crop读取；真实坐标需先标定，见该常量定义处
            的TODO）。未标定（见respawn_crop_is_calibrated）时本函数会
            整体跳过特征3、只用1+2两层过滤——这是复查修复的安全防护：
            占位坐标下respawn_reader读不到倒计时会恒返回None，若不加这层
            防护，"未通过"会被当成"确认噪点"处理，导致所有真实死亡X标记
            都被拒绝（而不是原先注释误认为的"等价于跳过"）。
        death_window: extract_death_events给出的counter确认窗口(lo, hi)。
            生产调用必须传入：搜索从lo开始、基线帧取在lo之前，见上文。
        allow_unanchored: 显式放弃锚点约束，只按death_ts搜索。仅供研究/
            复现脚本使用（无counter真值时的误报率测量）。生产路径不要用：
            无锚点扫描正是AGE-131误报的来源。

    Raises:
        ValueError: 既没传death_window又没显式allow_unanchored=True。

    Returns:
        命中: {"region","cx","cy","ts_offset","source": "minimap_x_marker"}
        其中ts_offset是相对death_ts的偏移；传入death_window后搜索从窗口
        下界开始，所以它可以是负数（death_ts只是窗口中点，真实死亡可能
        更早）——下游只用region/source，这里保留原字段语义不变。
        窗口内未命中（如镜头被UI遮挡、录制帧率丢帧、候选全部被判定为
        噪点）: None
    """
    if death_window is None and not allow_unanchored:
        raise ValueError(
            "extract_death_location 必须锚定在counter确认过的死亡窗口内"
            "（AGE-131方案1）：请传入 extract_death_events 事件里的 "
            "death_window=e[\"window\"]。确实要做无锚点扫描（研究/复现用）"
            "请显式传 allow_unanchored=True。"
        )

    duration = video_duration(video_path)
    # 锚点：counter窗口下界（真实死亡最早可能发生的时刻）；无锚点模式退化为death_ts。
    if death_window is not None:
        anchor = min(float(death_window[0]), death_ts)
        latest = max(float(death_window[1]), death_ts)
    else:
        anchor = latest = death_ts
    ts = max(anchor, 0.0)
    end = min(latest + search_window, duration - 0.1)
    zones = list(static_zones or [])

    with tempfile.TemporaryDirectory(prefix="coach_dm_") as tmp:
        # 特征1：死亡前多帧基线，把此刻已存在的候选全部拉黑（死亡尚未发生，
        # 这些不可能是本次死亡的X标记）。取并集而非单帧，见docstring。
        for i, offset in enumerate(_BASELINE_OFFSETS):
            baseline_ts = anchor - offset
            if baseline_ts < 0:
                continue  # 死亡发生在视频开头，前面没有可用基线
            try:
                baseline_frame = Path(tmp) / f"baseline_{i}.png"
                grab_minimap_frame(video_path, baseline_ts, baseline_frame, crop)
                zones = zones + [(c["cx"], c["cy"])
                                 for c in _death_marker_candidates(baseline_frame, crop)]
            except (subprocess.CalledProcessError, ValueError):
                continue  # 单帧基线取不到不影响主流程，其余基线/static_zones照用

        while ts <= end + 1e-6:
            frame = Path(tmp) / f"dm_{ts:.3f}.png"
            try:
                grab_minimap_frame(video_path, ts, frame, crop)
                marker = detect_death_marker(frame, crop, exclude_zones=zones)
            except (subprocess.CalledProcessError, ValueError):
                ts += sample_interval
                continue
            if marker is not None:
                # 特征2：位置持续性复核——真正的X标记应在+1秒后仍停留在
                # 原位；逐帧跳变的画面噪点复核会失败，判定为误报继续向后搜索。
                # 复核帧允许越过搜索窗口末尾（它只是对同一个候选再看一眼，
                # 不是继续搜索），否则窗口最后一个采样点永远无法复核、只能
                # 无条件采信——那正好是噪点最容易漏过的位置。
                confirm_ts = min(ts + 1.0, duration - 0.1)
                position_confirmed = False
                if confirm_ts > ts:
                    confirm_frame = Path(tmp) / f"dm_confirm_{ts:.3f}.png"
                    try:
                        grab_minimap_frame(video_path, confirm_ts, confirm_frame, crop)
                        confirm_marker = detect_death_marker(confirm_frame, crop, exclude_zones=zones)
                        position_confirmed = (
                            confirm_marker is not None
                            and _in_zones(confirm_marker["cx"], confirm_marker["cy"],
                                         [(marker["cx"], marker["cy"])])
                        )
                    except (subprocess.CalledProcessError, ValueError):
                        position_confirmed = False
                else:
                    position_confirmed = True  # 已到视频末尾，无帧可复核，按命中采信

                # 特征3：复活倒计时共现复核。respawn_reader未提供时跳过
                # （视为通过），保持向后兼容；提供时必须在同一ts读到
                # 非None的倒计时数值才算通过——噪点源没有理由和倒计时
                # 同时出现。窗口锚定在已知死亡事件内（见函数docstring），
                # 倒计时持续多秒跨越多个采样点只会重复确认同一个marker，
                # 不会被计成多次死亡。
                #
                # 安全防护（AGE-131复查发现的bug）：respawn_crop在真实
                # 坐标标定完成前是占位值（见_FALLBACK_RESPAWN_CROP/
                # config.yaml的TODO）。占位坐标裁出的区域不是真正的复活
                # 倒计时HUD，respawn_reader在其上必然读不到倒计时、恒
                # 返回None——如果这里仍然照常执行"respawn_reader未落
                # None即不通过"的判定，效果不是原设计注释所说的"该特征被
                # 跳过、不影响原有过滤"，而是**respawn_confirmed恒为False，
                # 导致所有真实死亡X标记都被误判为噪点拒绝**（相当于把
                # extract_death_location的召回率打到接近0）。只要
                # respawn_crop还没标定，就必须整体跳过特征3（视为通过），
                # 等价于respawn_reader=None时的向后兼容行为；待真实坐标
                # 标定完成后，特征3才会真正生效。
                #
                # 同理，取不到复活HUD帧（裁剪区越界/丢帧/ffmpeg报错）是
                # "取证失败"而不是"证明了倒计时没出现"，不能据此否决候选：
                # 那会把同一个配置问题重新变成召回崩塌。按"本特征无结论"
                # 处理，退回特征1+2的判定。
                respawn_confirmed = True
                if respawn_reader is not None and respawn_crop_is_calibrated(respawn_crop):
                    respawn_frame = Path(tmp) / f"rs_{ts:.3f}.png"
                    try:
                        grab_respawn_frame(video_path, ts, respawn_frame, respawn_crop)
                    except subprocess.CalledProcessError:
                        pass  # 取证失败 → 本特征无结论，不否决
                    else:
                        respawn_confirmed = respawn_reader(respawn_frame) is not None

                if position_confirmed and respawn_confirmed:
                    return {
                        "region": marker["region"],
                        "cx": marker["cx"],
                        "cy": marker["cy"],
                        "ts_offset": round(ts - death_ts, 2),
                        "source": "minimap_x_marker",
                    }
                zones = zones + [(marker["cx"], marker["cy"])]  # 噪点，排除后继续搜索
            ts += sample_interval
    return None


# ---------------------------------------------------------------------------
# 默认KDA读数器（VLM实现，阶段2接入LLM配置后可用）
# ---------------------------------------------------------------------------

_KDA_PROMPT = (
    "这是一张王者荣耀对局界面顶部HUD计数器区域的截图，"
    "包含 击杀/死亡/助攻 三个数字（形如 2/1/8）。"
    "请只输出JSON数组 [击杀, 死亡, 助攻]，例如 [2, 1, 8]。"
    "如果图中看不清或没有这三个数字，只输出 null。"
)


_RESPAWN_PROMPT = (
    "这是一张王者荣耀对局界面的截图局部，可能包含\"复活倒计时\"UI"
    "（通常显示为剩余秒数，如\"复活: 8\"或纯数字倒计时）。"
    "如果图中能看到复活倒计时，只输出该剩余秒数的整数，例如 8。"
    "如果图中没有复活倒计时（角色存活或看不清），只输出 null。"
)


def make_vlm_respawn_reader(vlm_client: Any) -> RespawnReader:
    """用视觉LLM构造respawn_reader（AGE-131方案3：respawn-HUD共现特征）。

    读不出/调用失败/未显示倒计时统一返回None，供extract_death_location
    的respawn_confirmed逻辑判定为"倒计时未共现"。
    """
    from core.llm_client import LLMError, extract_json  # 延迟导入避免循环

    def reader(image_path: Path) -> Optional[int]:
        try:
            raw = vlm_client.chat_image(_RESPAWN_PROMPT, image_path)
        except LLMError:
            return None
        if "null" in raw.lower() and not any(ch.isdigit() for ch in raw):
            return None
        try:
            data = extract_json(raw)
        except ValueError:
            return None
        if isinstance(data, int) and data >= 0:
            return data
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], int):
            return data[0]
        return None

    return reader


def make_vlm_kda_reader(vlm_client: Any) -> KdaReader:
    """用视觉LLM（如qwen-vl）构造kda_reader（core.llm_client.LLMClient实例）。

    读不出/调用失败返回None → extract_death_events视为该帧HUD不可见，
    走邻近重采逻辑。
    """
    from core.llm_client import LLMError, extract_json  # 延迟导入避免循环

    def reader(image_path: Path) -> Optional[KDA]:
        try:
            raw = vlm_client.chat_image(_KDA_PROMPT, image_path)
        except LLMError:
            return None
        if "null" in raw.lower() and "[" not in raw:
            return None
        try:
            data = extract_json(raw)
        except ValueError:
            return None
        if (isinstance(data, list) and len(data) == 3
                and all(isinstance(x, int) and x >= 0 for x in data)):
            return (data[0], data[1], data[2])
        return None

    return reader
