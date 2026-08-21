# -*- coding: utf-8 -*-
"""FastAPI层（Web UI scaffold epic AGE-176）。

只是orchestrator.py/training_engine.py既有逻辑的薄HTTP封装，不重新实现
任何检测/分类/LLM调用逻辑——所有真正的业务逻辑仍然活在core/utils里，
这一层只负责：请求解析→调用→序列化返回，以及视频分析这种耗时操作的
后台任务化。

启动：
    cd coach && uvicorn api.main:app --reload
"""
