const fs = require('fs');
const path = '/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json';
const data = JSON.parse(fs.readFileSync(path, 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  for (const [i, row] of data.records.entries()) {
    try {
      const endpoint = `https://www.youtube.com/oembed?url=${encodeURIComponent(row.url)}&format=json`;
      const res = await fetch(endpoint, {headers:{'User-Agent':'Mozilla/5.0'}});
      if (res.ok) {
        const meta = await res.json();
        row.title = meta.title || row.title_hint;
        row.author_name = meta.author_name || row.source_channel;
        row.metadata_status = 'oembed-verified';
      } else row.metadata_status = `oembed-http-${res.status}`;
    } catch (e) { row.metadata_status = 'oembed-error'; }
    if (i % 10 === 0) fs.writeFileSync(path, JSON.stringify(data, null, 2) + '\n');
    await sleep(100);
  }
  fs.writeFileSync(path, JSON.stringify(data, null, 2) + '\n');
  console.log(JSON.stringify({count:data.records.length, verified:data.records.filter(r=>r.metadata_status==='oembed-verified').length}, null, 2));
})();
