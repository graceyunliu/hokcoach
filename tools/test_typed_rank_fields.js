const assert=require('assert');
const d=require('../data/source_seeds/youtube/seed_manifest.json');
assert.strictEqual(d.count,161);
assert.strictEqual(d.records.filter(r=>r.rank_schema_version==='typed-v1').length, d.count);
for(const r of d.records){
  const p=r.rank_profile;
  assert.ok(p && Object.prototype.hasOwnProperty.call(p,'regular_rank'));
  assert.ok(p && Object.prototype.hasOwnProperty.call(p,'peak_score'));
  assert.ok(p && Object.prototype.hasOwnProperty.call(p,'hero_power'));
  if(p.peak_score) assert.strictEqual(p.peak_score.unit,'peak_score');
  if(p.hero_power) assert.strictEqual(p.hero_power.unit,'hero_power');
  if(p.regular_rank) assert.ok(['tier','stars'].includes(p.regular_rank.unit));
}
const find=id=>d.records.find(r=>r.seed_id===id);
assert.strictEqual(find('hokclass_008').rank_profile.peak_score, null); // 1160 is mentioned without a typed 巅峰 context.
assert.strictEqual(find('hokclass_039').rank_profile.hero_power.value,7000);
assert.strictEqual(find('hokclass_053').rank_profile.hero_power.value,13000);
assert.strictEqual(find('hokclass_060').rank_profile.peak_score.value,1200);
assert.strictEqual(find('hokclass_060').rank_profile.regular_rank,null);
assert.strictEqual(find('hokclass_070').rank_profile.peak_score.value,2100);
console.log('typed rank field tests passed');
