const fs = require('fs');
const raw = fs.readFileSync('/home/ubuntu/console_outputs/exec_result_2026-08-26_11-29-41_770.txt', 'utf8').trim();
const rows = JSON.parse(raw);
const excluded = new Set(['Play all', 'Shuffle play']);
const unique = [];
const seen = new Set();
for (const row of rows) {
  const url = row.url;
  if (!url || excluded.has(row.title) || seen.has(url)) continue;
  seen.add(url);
  const id = new URL(url).searchParams.get('v');
  const title = row.title || '';
  const role = /打野|jungle|野王|镜|澜|孙悟空|马超|橘右京|橘子|刘备|大司命|赵云|裴擒虎|李白|兰/.test(title) ? '打野' :
    /射手|marksman|后羿|公孙离|马可|狄仁杰|百里守约|鲁班|艾琳/.test(title) ? '射手' :
    /辅助|support|少司缘|朵莉亚|大乔|蔡文姬|瑶|孙膑/.test(title) ? '辅助' :
    /对抗|边路|狂铁|项羽|吕布|马超|亚连|夏侯|关羽|老夫子/.test(title) ? '对抗' :
    /中路|mid|法师|小乔|西施|海月|貂蝉|安琪拉|甄姬|妲己|姜子牙|干将|王昭君|扁鹊|金蝉|海诺/.test(title) ? '法师' : '待确认';
  unique.push({seed_id: `hokclass_${String(unique.length + 1).padStart(3, '0')}`, video_id: id, url, title_hint: title, role_hint: role, source_channel: 'HonorofKings王者提升班', source_kind: 'YouTube playlist/search catalog', transcript_status: 'pending', download_status: 'pending', evidence_quality: 'catalog-verified'});
}
const counts = {};
for (const row of unique) counts[row.role_hint] = (counts[row.role_hint] || 0) + 1;
const out = {generated_at: new Date().toISOString(), source_playlist: 'https://www.youtube.com/playlist?list=PLK78_awGVR4MPZc-8Mr_P26NnLtKvzyfg', channel: 'https://www.youtube.com/@HonorofKings%E7%8E%8B%E8%80%85%E6%8F%90%E5%8D%87%E7%8F%AD', requested_minimum: 100, count: unique.length, role_counts: counts, records: unique};
fs.writeFileSync('/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json', JSON.stringify(out, null, 2) + '\n');
console.log(JSON.stringify({count: unique.length, role_counts: counts}, null, 2));
