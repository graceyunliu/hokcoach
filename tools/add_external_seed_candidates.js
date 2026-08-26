const fs = require('fs');
const path = '/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json';
const data = JSON.parse(fs.readFileSync(path, 'utf8'));
const extras = [
  {video_id:'QHVOZlII7VE', url:'https://www.youtube.com/watch?v=QHVOZlII7VE', title_hint:'峰赛1770分打野第一视角复盘教学全局讲解', role_hint:'打野', source_channel:'王者荣耀Honor of Kings / 折纸', source_kind:'YouTube search result', evidence_quality:'search-verified'},
  {video_id:'UMdrheux9yo', url:'https://www.youtube.com/watch?v=UMdrheux9yo', title_hint:'巅峰赛全国中单分榜第一晋级赛传送诸葛第一视角复盘教学全局讲解', role_hint:'法师', source_channel:'王者荣耀Honor of Kings', source_kind:'YouTube search result', evidence_quality:'search-verified'}
];
const existing = new Set(data.records.map(r => r.video_id));
for (const e of extras) if (!existing.has(e.video_id)) {
  data.records.push({seed_id:`hokclass_${String(data.records.length + 1).padStart(3, '0')}`, ...e, transcript_status:'pending', download_status:'pending'});
}
data.count = data.records.length;
data.role_counts = {};
for (const r of data.records) data.role_counts[r.role_hint] = (data.role_counts[r.role_hint] || 0) + 1;
fs.writeFileSync(path, JSON.stringify(data, null, 2) + '\n');
console.log(JSON.stringify({count:data.count, role_counts:data.role_counts}, null, 2));
