const fs = require('fs');
const path = '/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json';
const d = JSON.parse(fs.readFileSync(path,'utf8'));
const extras = [
  ['fqiUm2azky0','https://www.youtube.com/watch?v=fqiUm2azky0','当对抗路来玩射手时有多敢打？包输的对局被后羿翻盘','射手','HonorofKings王者提升班','search-verified'],
  ['fhvKUve9TuU','https://www.youtube.com/watch?v=fhvKUve9TuU','队友没错错的是数据让你产生了幻觉｜澜','打野','HonorofKings王者提升班','search-verified'],
  ['1e4gzwNhDxo','https://www.youtube.com/watch?v=1e4gzwNhDxo','粉丝复盘后羿西施合集｜1700分发育路不会抗压','射手','HonorofKings王者提升班','search-verified'],
  ['HXzCHwKOjo4','https://www.youtube.com/watch?v=HXzCHwKOjo4','粉丝复盘钟馗｜宝子们期待的神奇宝贝钟馗','辅助','HonorofKings王者提升班','search-verified'],
  ['AiFsjrFFZ8A','https://www.youtube.com/watch?v=AiFsjrFFZ8A','国服武则天挂边全局思路｜连胜技巧出装打法分享','法师','王者荣耀教学频道','search-verified'],
  ['MADe7o_U5xE','https://www.youtube.com/watch?v=MADe7o_U5xE','149段发育路卢雅娜第一视角：组合技能用对','射手','王者荣耀教学频道','search-verified'],
  ['M7VrRtmhlN0','https://www.youtube.com/watch?v=M7VrRtmhlN0','高评分弈星6分钟精讲教学：抢线速度与支援','法师','琴涫','search-verified'],
  ['BV1NE4m197xx','https://www.bilibili.com/video/BV1NE4m197xx/','中路公式化打法全方位分析中单新玩法','法师','浅梦/Bilibili','search-verified'],
  ['BV1EJ4m1A7b9','https://www.bilibili.com/video/BV1EJ4m1A7b9/','打野单挑玄策无解？世一老六罕见solo输给路人','打野','Bilibili王者内容','search-verified'],
  ['BV1Ph4y1N7Cu','https://www.bilibili.com/video/BV1Ph4y1N7Cu/','白姨寂然后续：复盘与打野/对抗路打法思路','打野','Bilibili王者内容','search-verified'],
  ['BV14u411n7Vz','https://www.bilibili.com/video/BV14u411n7Vz/','二锅头测试中单太乙新出装，一路追击四杀','辅助','Bilibili王者内容','search-verified']
];
const seen = new Set(d.records.map(r=>r.video_id));
for (const [id,url,title,role,channel,status] of extras) if(!seen.has(id)) {
  d.records.push({seed_id:`hokclass_${String(d.records.length+1).padStart(3,'0')}`,video_id:id,url,title_hint:title,title,role_hint:role,role,hero:'待确认',source_channel:channel,source_kind:'cross-platform search result',transcript_status:'pending',download_status:'pending',metadata_status:'search-verified',evidence_quality:status,rank_stratum:'待确认',rank_evidence:'needs-title-or-thumbnail-verification',series:/神奇宝贝/.test(title)?'神奇宝贝TV':'其他',coverage_status:'needs-verification'});
}
d.count=d.records.length;
for(const key of ['role','rank_stratum','series']){d[`${key}_counts`]={};for(const r of d.records)d[`${key}_counts`][r[key]]=(d[`${key}_counts`][r[key]]||0)+1;}
fs.writeFileSync(path,JSON.stringify(d,null,2)+'\n');
console.log(JSON.stringify({count:d.count,role_counts:d.role_counts,rank_counts:d.rank_stratum_counts,series_counts:d.series_counts},null,2));
