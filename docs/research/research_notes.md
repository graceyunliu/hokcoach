# Replay-coaching research notes (working)

## Repository baseline
- Repository: https://github.com/graceyunliu/hokcoach
- Main branch at commit `5e33b09`.
- Existing product is a Python CLI/text MVP with rule-first replay analysis, optional VLM, minimap color-threshold detection, knowledge retrieval, constraints, training, and LLM fallback.
- README states automated video replay is currently HUD coarse sampling + binary localization + minimap HSV threshold/connected components; 34 offline tests are expected.

## Sources opened
1. Official王者营地 feature article: https://pvp.qq.com/web201706/newsdetail.shtml?tid=588700
   Search result describes upgraded replay as including draft/lineup advantage and counter analysis, real-time win probability from economy/experience gaps, and key-event marking.
2. Bilibili 花海/影实战复盘 page: https://www.bilibili.com/video/BV1BDm1YpEgy/
   Page title: “王者荣耀：影国服教学课程（实战复盘）：花海第一视角复盘，来学影的实战细节”. Visible description says the lessons cover “灵活使用远近重普蓄”, “前期支援优先打路线，后期支援优先发育路线”, “影的核心依旧是发育，不要为了蹭草、抢人影响自身发育”, “学会隐藏视野和给到假视野，在团战中利用二技能快速绕后切后排，推动团战胜利”.

## Initial category seeds
- Mechanical execution: attack/skill timing, charged attacks, skill sequencing, movement/approach, burst combos.
- Macro/tempo: early-vs-late rotation priority, farming vs joining, lane/route selection.
- Information/vision: hide own information, create false information, bush-checking/探草, reading enemy location.
- Teamfight: flank timing, target selection, backline access, converting won fight into objective/push.
- Resource discipline: avoid low-value contesting that sacrifices own development.

These are source-backed seeds, not yet the final taxonomy. Continue with more representative streamer/pro pages and repository code/tests.

## Additional opened-source findings
3. Official赛事运营 article: https://pvp.qq.com/gicp/news/600/570395.html
   Full text frames coaching around objective-oriented decisions rather than “can we fight”: tower purpose, rotate/swap lanes, position control, vision control, and intentionality. It distinguishes early pressure/composition timing from late teamfight timing, and describes wave control as the prerequisite for tower pressure: fast clear to delay enemy rotations, then create numbers advantages on another lane. It also notes that fights often depend on an opponent’s exposed mistake, such as poor vision checking or bad movement.
4. Official video detail page for朵莉亚: https://pvp.qq.com/v/detail.shtml?G_Biz=18&tid=855022
   Dynamic page exposed no useful transcript in extraction; retain as a lead only.
5. YouTube high-rank jungle replay page: https://www.youtube.com/watch?v=QHVOZlII7VE
   Title explicitly states “峰赛1770分打野第一视角复盘教学全局讲解”, but public metadata exposes no transcript. Use as evidence for format/coverage intent, not for verbatim claims.
6. Douyin精选 page for 05最强海月 timed out in browser; it remains a search-discovered lead, not a verified content source.

## Evidence quality rule
Treat full page text or repository artifacts as strong evidence, search snippets as medium/lead evidence, and video titles without transcript as format evidence only. Do not claim exact streamer wording unless transcript/audio has been obtained.

## Broadened source inventory
7. Official course lead for花海/影: https://pvp.qq.com/m/m201606/detail.shtml?G_Biz=18&tid=881528&e_code=pvpweb_m.statictypenew.type6703 (redirected to a mobile video page that requires mobile rendering; search metadata states it is a王者营地国服系列课程 and teaches影’s进阶技巧与对局思路).
8. Search lead for无畏/张良复盘: https://www.facebook.com/wzryds/videos/.../783242598070807/ ; snippet mentions detailed first-person review, but source is a repost and not transcript-verified.
9. Search lead for无畏辅助 first-person review: https://www.youtube.com/watch?v=jjlhUhB_znU ; title establishes support-role first-person replay format, but public metadata did not expose transcript.
10. Search lead for高分中单复盘: https://www.youtube.com/watch?v=CsxmY6Qiz1M ; title states 2300-score mid first-person full-game replay explanation.
11. Search lead for小乔保姆级复盘: https://www.youtube.com/watch?v=h3WcqAUkn_0 ; title states 120 games to王者 and first-person full-game replay teaching.
12. Search lead for high-rank support: https://www.youtube.com/watch?v=I66rIP448OA ; title states 1820-score support first-person replay explanation.

Cross-source pattern: titles and official course descriptions consistently promise “第一视角/全局讲解/实战复盘”, indicating reviewers cover continuous decisions, not only post-death blame. The strongest directly readable content (花海 page description and official运营 article) emphasizes hidden/false vision, farming-vs-rotation priority, lane pressure, objective conversion, and teamfight flank/targeting. The 05最强海月 source could not be opened due timeout, so the report will label its specific categories as search-lead hypotheses rather than verified quotations.
