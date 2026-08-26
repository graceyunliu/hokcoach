const fs=require('fs');
const path='/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json';
const d=JSON.parse(fs.readFileSync(path,'utf8'));
const replay=/复盘|replay|review|first-person|first person|POV|VOD|full match|全局讲解|losing game|败局|翻盘|实战|gameplay|高分局|巅峰赛|排位|粉丝投稿|fan submission|fan review/i;
const strategyOnly=/tier ranking|strength ranking|版本强度|公式化打法|出装铭文|三件装备|must-learn|essential skills|基础教学|零基础|ranking of current|best.*climb/i;
for(const r of d.records){const t=`${r.title||''} ${r.title_hint||''}`;r.content_type=replay.test(t)&&!strategyOnly.test(t)?'full-game-or-replay-review':'strategy-or-format-adjacent';r.seed_eligibility=r.content_type==='full-game-or-replay-review'?'eligible-seed':'context-only';r.full_game_evidence=/全局|full match|first-person|第一视角|复盘|replay|review|VOD|巅峰赛|高分局|粉丝投稿|fan submission|fan review/i.test(t)?'title-cue':'weak';}
d.eligible_count=d.records.filter(r=>r.seed_eligibility==='eligible-seed').length;d.context_only_count=d.records.length-d.eligible_count;fs.writeFileSync(path,JSON.stringify(d,null,2)+'\n');console.log(JSON.stringify({total:d.count,eligible_count:d.eligible_count,context_only_count:d.context_only_count},null,2));
