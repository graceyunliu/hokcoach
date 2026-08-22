# MOBA 录屏分析 — 学术方法补调研报告

> 场景：从玩家上传的手机录屏中检测王者荣耀游戏内事件。已用 HSV 颜色阈值 + 连通域 + 模板匹配做过一轮调研。
> 本报告基于 arXiv / 顶会论文，每条论文标题、作者、年份、venue 均经一级来源页面（arXiv abs / CVF / AAAI / IEEE / ACM / OpenReview）核实。
> 标注规则：**direct** = 可直接用于本场景；**transferable** = 方法可迁移；**adjacent** = 仅相邻/理论启发；无对应论文时明确写"未找到直接相关研究"。

---

## Q1. 游戏内 HUD / UI 元素识别

**有直接相关的学术研究**——这是一个已有专门 benchmark 的细分领域（mobile game UI element detection），且近两年（2023–2025）仍有新工作。

1. **A Practical Evaluation of UI Element Detection for Automated Mobile Game Testing**
   - 作者：Nozomu Karai, Koya Ihara, Tatsuya Ishimoto, Daiki Kubo, Kotaro Kikuchi
   - 年份/Venue：2025 / IEEE CoG 2025（IEEE Conference on Games），DOI 10.1109/CoG64752.2025.11114223
   - URL：https://ieeexplore.ieee.org/document/11114223/
   - 做什么：针对手游构建了三类游戏 UI 元素检测数据集，benchmark 了现有 UI 检测方法，结论是现有方法在游戏 UI 上精度仍不足、但可用于 monkey testing 等特定目的。
   - 相关性：**direct** — 直接就是"手游 UI 元素检测"问题。
   - 迁移评估：**值得深挖**。它给出的是评测基线与数据集范式，说明用通用 UI 检测器（如 YOLO/Detectron 类）做手游图标检测可行但精度有限；对我们最大的价值是"需要自建少量游戏内标注数据 + 检测器"这条已被验证的路径，而非现成方法。标注成本中等（每类几十到几百张）。

2. **YOLOv5-ABLN: A Small Object Detection Model for Game App Interface**
   - 作者：Yunli Chen, Rui Tian, Yan Li, Yong Li
   - 年份/Venue：2023 / ICSESS 2023，DOI 10.1109/ICSESS58500.2023.10293127
   - URL：https://ieeexplore.ieee.org/document/10293127/
   - 做什么：针对手游 GUI 小目标元素检测，在 YOLOv5s 上加 Bi-Level Routing Attention + Normalized Wasserstein Distance 损失，自建 2400 张数据集，mAP 91.9%。
   - 相关性：**transferable** — 工程上最接近我们"图标检测"的可落地方案。
   - 迁移评估：**谨慎关注**。方法本身成熟可复现（YOLO 系列 + 注意力），但需要我们自建标注数据，且它面向的是"可点击元素检测"（按钮等），不是"固定状态图标识别"；对固定位置的 UI 图标，模板匹配/XFeat（见 Q3）反而更省事。适合作为"图标位置不固定 / 需要检测"场景的备选。

3. **Owl Eyes: Spotting UI Display Issues via Visual Understanding**
   - 作者：Zhe Liu, Chunyang Chen, Junjie Wang, Yuekai Huang, Jun Hu, Qing Wang
   - 年份/Venue：2020 / ACM FSE 2020，DOI 10.1145/3324884.3416547
   - URL：https://arxiv.org/pdf/2009.01417.pdf
   - 做什么：用视觉理解检测 GUI 显示缺陷（错位、重叠等），自建 4470 张标注数据集，85% precision/84% recall。
   - 相关性：**adjacent** — 不是图标识别，是 UI 缺陷检测。
   - 迁移评估：**不建议投入**。与我们的任务重合度低，仅作"GUI 视觉理解 + 自建数据集"的方法论参考。

> Q1 结论：有直接相关的细分领域（手游 UI 元素检测），但学术界主流是"检测器 + 自建标注"路线，**需要标注数据**；对我们"固定 UI 图标识别"而言，Q3 中的免标注局部特征匹配（XFeat）通常更经济。建议把 Q1 这类工作作为"图标位置会变 / 需要检测未知图标"时的备选，而非主链路。

---

## Q2. 电竞 / MOBA 录像事件检测 & 关键时刻识别

**未找到直接针对"MOBA 录像视频帧"做事件检测的成熟学术研究**——MOBA 专属的、基于视频帧的事件时序定位文献非常稀疏。最接近的是一篇 2024 年的多模态游戏事件检测框架；其余 MOBA/LoL 论文多基于**比赛日志/时间线数据**而非视频帧，仅作相邻参考。

1. **3M: Multi-modal Multi-task Multi-teacher Learning for Game Event Detection**
   - 作者：Thye Shan Ng, Feiqi Cao, Soyeon Caren Han
   - 年份/Venue：2024 / arXiv:2406.09076（venue 页面未标注具体会议）
   - URL：https://arxiv.org/abs/2406.09076
   - 做什么：多模态多教师游戏事件检测框架，融合**在线聊天文本 + 解说员语音 + 游戏内 UI**三路信号做事件检测与理解。
   - 相关性：**transferable** — 目前最接近"游戏事件检测"的学术框架。
   - 迁移评估：**谨慎关注**。它用的是直播流的三模态（聊天+语音+UI），不是我们手里的"纯录屏画面"；但它证明"游戏 UI 截图 + 音频"组合可做事件检测，对我们把"画面+击杀播报音"结合（见 Q6）有直接启发。需要自建标注，工程量中等。

2. **Video Highlight Prediction Using Audience Chat Reactions**
   - 作者：Alexander C. Berg, Cheng-Yang Fu, Joon Lee, Mohit Bansal
   - 年份/Venue：2017 / EMNLP 2017，arXiv:1707.08559
   - URL：https://arxiv.org/abs/1707.08559
   - 做什么：用视觉特征 + 观众聊天文本做电竞/体育直播高光时刻预测。
   - 相关性：**adjacent** — 电竞高光检测，但依赖聊天文本（我们没有）。
   - 迁移评估：**不建议直接用**，但思路（视觉+外部文本信号）可借鉴。

3. **Commentary Generation from Data Records of Multiplayer Strategy Esports Game**（相邻，日志型）
   - 作者：Zihan Wang, Naoki Yoshinaga
   - 年份/Venue：2024 / arXiv:2212.10935
   - URL：https://arxiv.org/abs/2212.10935
   - 做什么：基于电竞比赛**日志/数据记录**生成解说文本。
   - 相关性：**adjacent（基于日志，非视频）** — 仅说明 MOBA 日志型事件分析已有研究，对我们"纯录屏"无直接迁移价值。

> Q2 结论：**未找到直接相关研究（基于 MOBA 录像视频帧的事件时序定位）**。可迁移的相邻研究是 3M（多模态游戏事件检测）。这是整份报告里"学术上有趣、但商业化距离较远"的一块——真正能用的 MOBA 事件检测产品方案目前都靠游戏内数据接口或日志，而非纯视频。对我们而言，事件检测更现实的做法是"画面信号（Q1/Q3）+ 音频信号（Q6）+ 运动信号（Q4）"的组合启发式，而非照搬某篇 MOBA 论文。

---

## Q3. 小样本 / 零样本图标匹配的新方法（2022 后）

**有大量成熟且可直接落地的研究**，且均**免标注、免训练**，是整份报告里最值得直接替换现有 cv2.matchTemplate 的部分。

1. **XFeat: Accelerated Features for Lightweight Image Matching**
   - 作者：Guilherme Potje, Felipe Cadar, Andre Araujo, Renato Martins, Erickson R. Nascimento
   - 年份/Venue：2024 / CVPR 2024，arXiv:2404.19174
   - URL：https://arxiv.org/abs/2404.19174
   - 做什么：为资源受限设备设计的快速局部特征检测+描述+匹配，普通笔记本 CPU 上实时，比现有深度局部特征快最多 5×。
   - 相关性：**direct**
   - 迁移评估：**值得深挖（首选）**。零标注（预训练权重直接用），把固定 UI 图标当模板做对应点匹配 + 几何验证，天然对缩放、分辨率、轻微遮挡更鲁棒，手机端可行。比 matchTemplate 多一层 mutual-NN + RANSAC 后处理。

2. **LightGlue: Local Feature Matching at Light Speed**
   - 作者：Philipp Lindenberger, Paul-Edouard Sarlin, Marc Pollefeys
   - 年份/Venue：2023 / arXiv:2306.13643（社区通行为 ICCV 2023）
   - URL：https://arxiv.org/abs/2306.13643
   - 相关性：**direct** — UI 图标匹配属于"容易图像对"，自适应早停让耗时远低于最坏情况。
   - 迁移评估：**谨慎关注**。免标注免微调，但偏 GPU 友好，落手机需 ONNX/CoreML/NCNN 导出；对纯小图标 patch 可能过度设计，建议作精度上限基线。

3. **Efficient LoFTR: Semi-Dense Local Feature Matching with Sparse-Like Speed**
   - 作者：Yifan Wang, Xingyi He, Sida Peng, Dongli Tan, Xiaowei Zhou
   - 年份/Venue：2024 / CVPR 2024，arXiv:2403.04765
   - URL：https://arxiv.org/abs/2403.04765
   - 相关性：**transferable** — detector-free，对低纹理目标（纯色按钮、扁平图标）尤其有价值。
   - 迁移评估：**谨慎关注**。Transformer 主干，参数高于 XFeat，建议只在"模板匹配置信度低"的困难帧作兜底二级匹配。

4. **MobileCLIP: Fast Image-Text Models through Multi-Modal Reinforced Training**
   - 作者：Pavan Kumar Anasosalu Vasu, Hadi Pouransari, Fartash Faghri, Raviteja Vemulapalli, Oncel Tuzel
   - 年份/Venue：2023（v2 2024）/ CVPR 2024，arXiv:2311.17049
   - URL：https://arxiv.org/abs/2311.17049
   - 相关性：**transferable** — 手机可跑的通用视觉嵌入，每类 1–5 张样例算 prototype 向量做度量学习式 few-shot 识别。
   - 迁移评估：**值得深挖**。无需训练，图像编码器有移动端友好变体可量化部署；缺点是全局嵌入无定位能力，需配合固定 ROI 裁切（我们 UI 位置固定，正好满足）。

5. **GUing: A Mobile GUI Search Engine using a Vision-Language Model**
   - 作者：Jialiang Wei 等
   - 年份/Venue：2024 / ACM TOSEM，arXiv:2405.00145
   - URL：https://arxiv.org/abs/2405.00145
   - 相关性：**adjacent** — 证明在 GUI 截图域上继续对比预训练可显著优于通用 CLIP。
   - 迁移评估：**谨慎关注**。提供"域内自监督预训练 + 小样本原型分类"范式与预训练权重来源。

> 详见 research_q3_q7_fewshot_lightweight.md（含 OmniGlue、JamMa 等备选）。

---

## Q4. 游戏内角色异常位移 / 瞬移（闪现）检测

**未找到直接针对"游戏角色闪现/瞬移检测"的学术论文**，但该问题在方法论上是标准的**轨迹点异常检测（point outlier in trajectory）**问题，监控/交通/GPS 领域有大量可直接迁移的成熟方案，且主流方法**无监督/自监督**。

1. **Learning Regularity in Skeleton Trajectories for Anomaly Detection in Videos**
   - 作者：Romero Morais, Vuong Le, Truyen Tran, Budhaditya Saha, Moussa Mansour, Svetha Venkatesh
   - 年份/Venue：2019 / CVPR 2019，arXiv:1903.03295
   - URL：https://arxiv.org/abs/1903.03295
   - 做什么：监控视频异常检测，把骨架运动分解为 global body movement（整体位移轨迹）与 local posture，用 encoder-decoder RNN 建模正常动力学，重构/预测误差大即异常。
   - 相关性：**transferable（强）**
   - 迁移评估：**值得深挖（首选）**。其"global movement 分支"几乎就是我们要的——专门学习被跟踪主体质心轨迹的正常动力学，闪现的瞬时大位移会在预测误差上形成尖峰。自监督（只需正常轨迹），可只保留 global 分支做轻量 RNN，单机实时可行。

2. **Trajectory Outlier Detection: Algorithms, Taxonomies, Evaluation, and Open Challenges**
   - 作者：Asma Belhadi, Youcef Djenouri, Jerry Chun-Wei Lin, Alberto Cano
   - 年份/Venue：2020 / ACM TMIS，DOI 10.1145/3399631
   - URL：https://dl.acm.org/doi/10.1145/3399631
   - 相关性：**adjacent（方法学地图）**
   - 迁移评估：**值得深挖（立项必读）**。明确区分"整条轨迹异常"与"点异常"，闪现属于点异常，据此可先上运动学阈值 baseline，零算力成本。

3. **Anomaly Transformer: Time Series Anomaly Detection with Association Discrepancy**
   - 作者：Jiehui Xu, Haixu Wu, Jianmin Wang, Mingsheng Long
   - 年份/Venue：2022 / ICLR 2022，arXiv:2110.02642
   - URL：https://openreview.net/forum?id=LzQQ89U1qm_
   - 相关性：**transferable（强，但偏重）**
   - 迁移评估：**谨慎关注**。把英雄坐标序列当多变量时序直接喂入即可输出逐时刻异常分数，无监督；但 Transformer 对短序列属牛刀杀鸡，建议作 baseline 打不平时的升级方案。

4. **Trajectory Anomaly Detection with Language Models (LM-TAD)**
   - 作者：Jonathan Mbuya, Dieter Pfoser, Antonios Anastasopoulos
   - 年份/Venue：2024 / arXiv:2409.15366
   - URL：https://arxiv.org/abs/2409.15366
   - 相关性：**transferable（中高）**
   - 迁移评估：**谨慎关注**。surprisal rate 给逐点异常度（"闪现发生在第几帧"），user token 思路可迁移为"英雄 token"（不同英雄移速不同）。需把坐标离散化成 token 网格。

> 实践建议：先用运动学先验做强 baseline（英雄移速上限 × Δt 阈值 + 鲁棒 z-score），这对"位移远超物理上限"大概率已足够；误报多时再升级到 Morais 的 global-movement encoder-decoder。**真正的工程瓶颈不在异常检测算法，而在上游稳定跟踪与坐标归一化**（镜头移动、小地图与主视角坐标系换算、ID 切换），跟踪跳变本身就会产生假闪现。

---

## Q5. 视野 / 信息不完整状态下的状态推断（POMDP / 游戏状态重建）

**有直接相关的学术框架**——"战争迷雾下推断隐藏状态"在 RTS 游戏里有专门研究，但它们**都依赖游戏内部状态访问**，对我们"纯录屏"场景是**理论启发**而非可直接用的方法。诚实地说：这条线对"探草死"目前判定为几乎不可行的信号，学术上也只能提供思路，不能直接解决。

1. **DefogGAN: Predicting Hidden Information in the StarCraft Fog of War with Generative Adversarial Nets**
   - 作者：Yonghyun Jeong, Hyunjin Choi, Byoungjip Kim, Youngjune Gwon
   - 年份/Venue：2020 / AAAI 2020，arXiv:2003.01927
   - URL：https://arxiv.org/abs/2003.01927
   - 做什么：给定 RTS 游戏的**部分可观测状态**，用 GAN 生成"去雾"后的完整游戏状态图像，预测迷雾区隐藏单位/信息。
   - 相关性：**transferable（强，理论启发）**
   - 迁移评估：**谨慎关注**。这是最直接相关的"部分可观测游戏状态推断"研究，思路可启发我们处理"某区域是否已被探明视野"。但它需要游戏内部状态输入（StarCraft 的部分观测向量），我们只有录屏画面；迁移需先用视觉重建一个"当前可见状态表示"，再喂入类似的预测网络——中间这一步本身就是难题。对"探草死"信号，它提供的是"基于历史可见区域 + 时间衰减的视野置信度建模"这个思路，而非现成可用的检测器。

2. **Forward Modeling for Partial Observation Strategy Games — A StarCraft Defogger**
   - 作者：Gabriel Synnaeve, Zeming Lin, Jonas Gehring 等
   - 年份/Venue：2018 / arXiv:1812.00054
   - URL：https://arxiv.org/abs/1812.00054
   - 做什么：为部分可观测策略游戏做前向建模，预测迷雾区隐藏状态。
   - 相关性：**transferable（理论启发）**
   - 迁移评估：**谨慎关注**。与 DefogGAN 同类，依赖游戏内部状态访问；价值在于"前向预测未观测区域"的理论框架，对纯录屏场景需大量改造。

3. **Learning Causal State Representations of Partially Observable Environments**
   - 作者：Amy Zhang, Zachary C. Lipton, Luis Pineda, Kamyar Azizzadenesheli, Anima Anandkumar, Laurent Itti, Joelle Pineau, Tommaso Furlanello
   - 年份/Venue：2019 / arXiv:1906.10437（NeurIPS 2019 系）
   - URL：https://arxiv.org/abs/1906.10437
   - 做什么：在 POMDP 中学习因果状态表示——从动作与观测历史中学习能预测未来观测的状态表示，用于部分可观测环境下的高效策略学习。
   - 相关性：**transferable（理论框架）**
   - 迁移评估：**不建议直接投入**。纯理论框架，面向 RL，需要动作-观测历史序列；对我们"仅视觉"场景是远端启发。仅作为"如何从有限观测推断隐状态"的理论参考。

> Q5 结论：学术界有"战争迷雾下推断隐藏状态"的直接研究（DefogGAN 等），但**它们都依赖游戏内部状态访问，对我们纯录屏场景是理论启发而非现成方案**。对"探草死"这类信号，学术上能给的启发是：基于"历史可见区域 + 时间衰减 + 移动预测"建一个视野置信度图，但落地到纯视觉判定仍然困难，维持"几乎不可行"的判断是合理的。

---

## Q6. 多模态（视觉 + 音频）游戏事件识别

**有直接相关研究**——3M（见 Q2）就是把游戏 UI + 解说语音 + 聊天文本结合做事件检测的框架；通用音视频领域也有成熟的轻量方案。多模态确实**显著优于纯视觉**在 highlight/事件检测上的表现，这是学术共识。

1. **3M: Multi-modal Multi-task Multi-teacher Learning for Game Event Detection**
   - （详见 Q2）作者：Thye Shan Ng, Feiqi Cao, Soyeon Caren Han；2024 / arXiv:2406.09076
   - URL：https://arxiv.org/abs/2406.09076
   - 相关性：**direct（游戏事件 + 音频）** — 融合游戏 UI + 解说员语音 + 聊天文本。
   - 迁移评估：**值得深挖**。直接证明"画面 + 音频"组合可做游戏事件检测；我们可取其"游戏 UI 截图 + 击杀播报音效"二路融合的简化版。需自建标注，工程量中等。

2. **Unsupervised Video Highlight Detection by Learning from Audio and Visual Recurrence**
   - 作者：Zahidul Islam, Sujoy Paul, Mrigank Rochan
   - 年份/Venue：2025 / WACV 2025，arXiv:2407.13933
   - URL：https://arxiv.org/abs/2407.13933
   - 做什么：无监督，用视觉特征 + 音频特征联合做视频高光检测。
   - 相关性：**transferable** — 通用音视频高光检测，非游戏专属。
   - 迁移评估：**谨慎关注**。无监督（免标注）是亮点，但面向通用视频；可借鉴其音视频融合结构，用于把击杀播报音与画面事件对齐。

3. **Automated Detection of Sport Highlights from Audio and Video Sources**
   - 作者：Francesco Della Santa, Morgana Lalli
   - 年份/Venue：2025 / arXiv:2501.16100
   - URL：https://arxiv.org/abs/2501.16100
   - 做什么：轻量深度学习，用音频 Mel-spectrogram + 灰度视频帧做体育高光检测。
   - 相关性：**transferable** — 轻量、音频+视频，工程范式贴合手机端。
   - 迁移评估：**值得深挖**。轻量、双模态、面向效率，正是我们"录屏画面 + 游戏音效"组合的工程模板。

> Q6 结论：**多模态显著优于纯视觉**是学术共识，且 3M 已在游戏事件检测上验证过。对我们最实际的一步是：把击杀/控制技能播报音效（固定、易识别）与画面信号做时间对齐融合——音频端用简单的音效模板匹配即可，能大幅降低纯视觉方案的误报。这是性价比很高的工程方向。

---

## Q7. 轻量级设备端部署

**有大量成熟研究**，且学术共识明确："以实测设备延迟而非 FLOPs 为优化目标"。

1. **MobileOne: An Improved One millisecond Mobile Backbone**
   - 作者：Pavan Kumar Anasosalu Vasu, James Gabriel, Jeff Zhu, Oncel Tuzel, Anurag Ranjan
   - 年份/Venue：2022（v2 2023）/ CVPR 2023，arXiv:2206.04040
   - URL：https://arxiv.org/abs/2206.04040
   - 做什么：以设备延迟为优化目标做骨干设计与重参数化，iPhone12 上推理 <1 ms，ImageNet 75.9%。
   - 相关性：**direct**
   - 迁移评估：**值得深挖**。若把图标识别换成学习式小分类器，MobileOne 是最直接的骨干；训练后重参数化为纯推理结构，端侧部署简单，需少量标注（每类几十张，可模板合成自动生成）。

2. **FastViT: A Fast Hybrid Vision Transformer using Structural Reparameterization**
   - 作者：同 MobileOne 团队
   - 年份/Venue：2023 / ICCV 2023，arXiv:2303.14189
   - URL：https://arxiv.org/abs/2303.14189
   - 做什么：混合 ViT，RepMixer 降低内存访问成本，移动端比 EfficientNet 快 4.9×，且对分布外样本/图像损坏更鲁棒。
   - 相关性：**direct**
   - 迁移评估：**值得深挖**。鲁棒性 + 移动延迟双优，适合应对录屏压缩伪影、不同机型渲染差异。作 MobileOne 的更高精度档位备选。

3. **FrameHopper: Selective Processing of Video Frames in Detection-driven Real-Time Video Analytics**
   - 作者：Md Adnan Arefeen, Sumaiya Tabassum Nimi, Md Yusuf Sarwar Uddin
   - 年份/Venue：2022 / DCOSS 2022，arXiv:2203.11493
   - URL：https://arxiv.org/abs/2203.11493
   - 做什么：把"跳过多少连续帧"建模为误差 vs 处理率优化问题，用离线 RL 学 skip-length 策略，摄像端轻量 agent 过滤帧。
   - 相关性：**direct**
   - 迁移评估：**值得深挖（性价比最高的一步）**。MOBA 录屏中相邻帧 UI 区域大多不变，学习式/启发式跳帧可把有效计算量降一个数量级。无需视觉标注（用检测输出一致性自监督），最容易在现有 cv2 流水线上落地，且与换不换匹配模型无关。

4. **Efficient Track Anything (EfficientTAM)**
   - 作者：Yunyang Xiong 等
   - 年份/Venue：2024 / arXiv:2411.18933
   - URL：https://arxiv.org/abs/2411.18933
   - 相关性：**transferable** — 轻量化 SAM 2，明确以"手机端视频目标分割"为动机。
   - 迁移评估：**不建议作为主链路**。零标注 prompt 驱动，但即便高效版仍重于图标匹配需求；适合后续跟踪非固定元素（英雄位移、小地图目标）的备用能力。

> 详见 research_q3_q7_fewshot_lightweight.md（含 GEMEL、EdgeMA、计算效率综述等备选）。

---

## 优先级总结

**值得深挖（直接可落地 / 性价比高）：**
- Q3：XFeat（免标注局部特征，直接替换 matchTemplate）、MobileCLIP（每类 1–5 样例原型匹配）
- Q7：FrameHopper 跳帧（录屏高时序冗余，降算力一个数量级，改动最小）
- Q6：画面 + 击杀播报音效融合（音频端简单模板匹配即可，大幅降误报）
- Q4：运动学阈值 baseline + Morais global-movement encoder-decoder（无监督，闪现点异常检测）
- Q1：Karai 2025 的手游 UI 检测 benchmark 路线（仅当图标位置会变 / 需检测未知图标时）

**谨慎关注（学术有价值但需较多改造 / 标注 / 算力）：**
- Q3：LightGlue、Efficient LoFTR（GPU 友好，落手机需导出量化，对小图标过度设计）
- Q2：3M 多模态游戏事件检测（最接近但用的是直播三模态，需自建标注）
- Q4：Anomaly Transformer、LM-TAD（牛刀杀鸡，作升级方案）
- Q7：MobileOne/FastViT（若转学习式分类器时的骨干选择）

**不建议投入（学术上有趣但不实用 / 距离过远）：**
- Q1：Owl Eyes（UI 缺陷检测，重合度低）
- Q2：基于日志的 MOBA 解说生成、观众聊天高光预测（依赖我们没有的日志/聊天文本）
- Q5：POMDP / DefogGAN / 因果状态表示（依赖游戏内部状态访问，对纯录屏是理论启发；"探草死"维持"几乎不可行"判断合理）

**两个最该先做的工程动作**（与论文无关但收益最大）：
1. 上跳帧 + ROI 裁切降算力（FrameHopper 思路）
2. 把击杀/控制播报音效与画面信号做时间对齐融合（3M / Della Santa 思路）
