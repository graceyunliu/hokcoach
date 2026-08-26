const fs = require('fs');
const path = '/home/ubuntu/hokcoach/data/source_seeds/youtube/seed_manifest.json';
const data = JSON.parse(fs.readFileSync(path, 'utf8'));
const heroRules = [
  ['海月',['海月','Haiyue']],['西施',['西施','Xi Shi','Xishi']],['小乔',['小乔','Xiao Qiao']],['安琪拉',['安琪拉','Angela']],['貂蝉',['貂蝉','Diaochan']],['甄姬',['甄姬']],['妲己',['妲己','Daji']],['王昭君',['王昭君']],['金蝉',['金蝉']],['海诺',['海诺','Heino']],['干将莫邪',['干将','Ganjiang']],['诸葛亮',['诸葛','Zhuge']],['橘右京',['橘右京','橘子']],['马超',['马超','Ma Chao']],['狂铁',['狂铁']],['项羽',['项羽']],['吕布',['吕布','Lu Bu']],['孙悟空',['孙悟空','悟空','Wukong']],['赵云',['赵云','Zhao Yun']],['澜',['澜','Lan']],['镜',['镜']],['裴擒虎',['裴擒虎','Pei Qihu']],['李白',['李白','Li Bai']],['刘备',['刘备']],['大司命',['大司命']],['后羿',['后羿','Hou Yi']],['马可波罗',['马可','Marco']],['公孙离',['公孙离']],['百里守约',['百里守约','Baili Shouyue']],['狄仁杰',['狄仁杰']],['鲁班七号',['鲁班']],['艾琳',['艾琳']],['朵莉亚',['朵莉亚','Doria','Dolia']],['大乔',['大乔','Da Qiao']],['少司缘',['少司缘']],['瑶',['瑶']],['孙膑',['孙膑']],['蔡文姬',['蔡文姬']],['张飞',['张飞']],['钟馗',['钟馗']],['雅典娜',['雅典娜']],['花木兰',['花木兰']],['司空震',['司空震','Sikong Zhen']],['云缨',['云缨']],['韩信',['韩信']],['玄策',['玄策']],['敖隐',['敖隐']],['女娲',['女娲']],['奕星',['奕星']],['高渐离',['高渐离']],['不知火舞',['不知火舞','Mai Shiranui']],['宫本武藏',['宫本']],['扁鹊',['扁鹊']],['嫦娥',['嫦娥']],
];
function firstMatch(text, rules) { for (const [name, keys] of rules) if (keys.some(k => text.toLowerCase().includes(k.toLowerCase()))) return name; return null; }
function rankStratum(text) {
  const t = text.toLowerCase();
  if (/1900|2000|2100|2200|2300|巅峰|全国前百|全国第一|国服|职业|kpl|pro|top-ranked|high-rank|mmr/.test(t)) return '高端巅峰/职业';
  if (/新手|青铜|白银|黄金|铂金|低段位|低分段|1000|1100|1200|1300|1400/.test(t)) return '新手-低段位';
  if (/钻石|星耀|王者|1500|1600|1700|1800/.test(t)) return '中段位-高段位';
  return '待确认';
}
function roleFor(text, hero) {
  const t = text.toLowerCase();
  if (/对抗|边路|clash|top lane|马超|狂铁|项羽|吕布|亚连|夏侯|关羽|老夫子|花木兰|司空震/.test(t)) return '对抗';
  if (/打野|jungle|野王|镜|澜|孙悟空|马超|橘右京|刘备|大司命|赵云|裴擒虎|李白|兰|韩信|玄策|云缨|宫本/.test(t)) return '打野';
  if (/射手|marksman|后羿|公孙离|马可|狄仁杰|百里守约|鲁班|艾琳|敖隐/.test(t)) return '射手';
  if (/辅助|support|少司缘|朵莉亚|大乔|蔡文姬|瑶|孙膑|张飞|钟馗/.test(t)) return '辅助';
  if (/中路|mid|法师|小乔|西施|海月|貂蝉|安琪拉|甄姬|妲己|姜子牙|干将|王昭君|扁鹊|金蝉|海诺|诸葛|女娲|奕星|高渐离|不知火舞|嫦娥/.test(t)) return '法师';
  return '待确认';
}
for (const row of data.records) {
  const text = `${row.title || ''} ${row.title_hint || ''}`;
  row.hero = firstMatch(text, heroRules) || '待确认';
  row.role = roleFor(text, row.hero);
  row.rank_stratum = rankStratum(text);
  row.series = /神奇宝贝|pokemon/i.test(text) ? '神奇宝贝TV' : '其他';
  row.rank_evidence = row.rank_stratum === '待确认' ? 'title-unresolved' : 'title-cue';
  row.coverage_status = row.rank_stratum !== '待确认' && row.role !== '待确认' && row.hero !== '待确认' ? 'usable-seed' : 'needs-verification';
}
const counts = (key) => data.records.reduce((m,r)=>(m[r[key]]=(m[r[key]]||0)+1,m),{});
data.role_counts = counts('role');
data.rank_counts = counts('rank_stratum');
data.series_counts = counts('series');
data.hero_counts = counts('hero');
fs.writeFileSync(path, JSON.stringify(data, null, 2) + '\n');
console.log(JSON.stringify({count:data.count,role_counts:data.role_counts,rank_counts:data.rank_counts,series_counts:data.series_counts,hero_counts:data.hero_counts}, null, 2));
