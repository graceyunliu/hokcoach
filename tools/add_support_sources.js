const fs=require('fs');
const path='/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json';
const d=JSON.parse(fs.readFileSync(path,'utf8'));
const rows=[
['hgojElN4OAs','开局辅助不跟直接不要了？','辅助'],['lse8jrHABsE','The Role of Support: Automatically Taking Blame in Unfavorable Games','辅助'],['DyYui3m3tys','锐评王者S41赛季辅助强度排名','辅助'],['18Pr7QTrzLc','Ranking of Current Support Strength','辅助'],['y6LYExRD988','五分钟速成辅助大局观｜张飞教学｜国服张飞','辅助'],['yfrwVtG-KXI','玩好辅助想上分｜少司缘','辅助'],['47HbaOOUtSQ','support with a 40% win rate and a 90 rating','辅助'],['VNRM3e8INFo','Support stuck in Peak Tier for ages','辅助'],['sPpOr2AJEzI','张飞保姆级教学-零基础也能变高手','辅助'],['dLqeEwXpsSE','How to Easily Get Gold Medals as a Support Player','辅助'],['LfjLv3lbLoU','辅助亚瑟强无敌8分钟平推对手','辅助'],['hGKand-Bn-8','元辅全网最细教学-零基础也能变高高手','辅助'],['4Tz9AiZ510M','辅助大乔运营一整局极限翻盘','辅助'],['ltAeWUb_EvU','True Innate Support Saint Body Ao Yin','辅助'],['MgDfOsw3IDE','辅助吕布依然可以扭转乾坤','辅助'],['xSkMAIdqUjw','孙膑高分局与低分段教学','辅助'],['HOi2aYcxo6Y','The Real Reason Why Supports Do Not Protect Marksmen','辅助'],['pvOVWF5jadU','为什么王者荣耀的辅助玩家总是背锅','辅助'],['OFAHGxgT6Hw','玩辅助历史最高1800','辅助'],['unACQa3RnQs','只玩辅助赵怀真上2400','辅助'],['GLDqNT3ETkk','Xiahou Dun support carry','辅助'],['qQS5HMxZaJE','零基础速成辅助元流','辅助'],['TDBIAfWCqcA','Marco Polo drives away his support','辅助']
];
const seen=new Set(d.records.map(r=>r.video_id));
for(const [id,title,role] of rows) if(!seen.has(id)) d.records.push({seed_id:`hokclass_${String(d.records.length+1).padStart(3,'0')}`,video_id:id,url:`https://www.youtube.com/watch?v=${id}`,title_hint:title,title,role_hint:role,role,hero:'待确认',source_channel:'HonorofKings王者提升班',source_kind:'channel role-search',transcript_status:'pending',download_status:'pending',metadata_status:'search-verified',evidence_quality:'search-verified',rank_stratum:'待确认',rank_evidence:'needs-title-or-thumbnail-verification',series:/神奇宝贝/.test(title)?'神奇宝贝TV':'其他',coverage_status:'needs-verification'});
d.count=d.records.length;
fs.writeFileSync(path,JSON.stringify(d,null,2)+'\n');
console.log(d.count);
