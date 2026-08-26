const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json','utf8'));
for (const r of d.records) {
  if (r.rank_stratum === '待确认' || r.role === '待确认' || r.hero === '待确认') console.log(`${r.seed_id}\t${r.role}\t${r.rank_stratum}\t${r.hero}\t${r.title}`);
}
console.log('\nSUMMARY', JSON.stringify({role_counts:d.role_counts,rank_counts:d.rank_counts,series_counts:d.series_counts},null,2));
