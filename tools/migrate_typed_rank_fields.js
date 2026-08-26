const fs=require('fs');
const path='/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json';
const d=JSON.parse(fs.readFileSync(path,'utf8'));
function firstMatch(text,re){const m=text.match(re);return m?m[1]:null;}
function numValue(s){if(!s)return null;const t=s.toLowerCase().replace(/,/g,'');const m=t.match(/(\d+(?:\.\d+)?)\s*(w|万)?/);if(!m)return null;return Math.round(parseFloat(m[1])*(m[2]?10000:1));}
function typed(text, hero){
  const t=text.replace(/\s+/g,' ');
  let regular=null;
  if(/排位百星|百星/.test(t)) regular={label:'百星',value:100,unit:'stars',evidence:'title-cue'};
  else {
    const glory=/荣耀王者/.test(t);
    const tier=firstMatch(t,/(?:排位|段位|赛季|卡在|打)(青铜|白银|黄金|铂金|钻石|星耀|王者)/);
    if(glory) regular={label:'荣耀王者',value:null,unit:'tier',evidence:'title-cue'};
    else if(tier) regular={label:tier,value:null,unit:'tier',evidence:'title-cue'};
  }
  const peakRaw=firstMatch(t,/(?:巅峰(?:分|赛)?\s*)(\d{3,4})/);
  const peak=peakRaw?numValue(peakRaw):null;
  const heroPowerRaw=firstMatch(t,/(\d+(?:\.\d+)?\s*(?:w|W|万)?)(?:战力|省标|国标|combat power|power)/i);
  const power=heroPowerRaw?numValue(heroPowerRaw):null;
  const hero_power=power?{value:power,unit:'hero_power',hero:hero||'待确认',evidence:'title-cue'}:null;
  return {regular_rank:regular,peak_score:peak?{value:peak,unit:'peak_score',evidence:'title-cue'}:null,hero_power};
}
for(const r of d.records){const text=`${r.title||''} ${r.title_hint||''}`;r.rank_profile=typed(text,r.hero);r.rank_schema_version='typed-v1';r.rank_stratum_legacy=r.rank_stratum;const p=r.rank_profile; if(p.peak_score) r.rank_stratum=p.peak_score.value>=1900?'高端巅峰/职业':p.peak_score.value>=1500?'中段位-高段位':'新手-低段位'; else if(p.regular_rank) r.rank_stratum=p.regular_rank.label==='王者'?'中段位-高段位':'新手-低段位'; else if(p.hero_power) r.rank_stratum='英雄战力-独立指标';}
d.typed_rank_counts={regular_rank:d.records.filter(r=>r.rank_profile.regular_rank).length,peak_score:d.records.filter(r=>r.rank_profile.peak_score).length,hero_power:d.records.filter(r=>r.rank_profile.hero_power).length};
fs.writeFileSync(path,JSON.stringify(d,null,2)+'\n');
console.log(JSON.stringify(d.typed_rank_counts,null,2));
