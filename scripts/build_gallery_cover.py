"""Draw a bounded, three-card project preview from the existing public aggregates."""
from pathlib import Path
from collections import Counter
import math,json
r=Path(__file__).resolve().parents[1]/'showcase'
d=json.loads((r/'assets/gallery-data.json').read_text(encoding='utf-8'))
colors=['#4269d0','#efb118','#ff725c','#6cc5b0','#a463f2','#ff8ab7','#97bbf5','#b59a6b','#60a8a4','#b5c456','#9194a5']
s=['''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720"><defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#101827"/><stop offset=".48" stop-color="#101827"/><stop offset=".8" stop-color="#a7b0be"/><stop offset="1" stop-color="#fff"/></linearGradient><clipPath id="window"><rect x="70" y="292" width="1060" height="340"/></clipPath></defs><rect width="1200" height="720" fill="url(#bg)"/><rect width="1200" height="62" fill="white"/><g font-family="Segoe UI,Microsoft YaHei,sans-serif"><rect x="34" y="19" width="24" height="24" rx="5" fill="#191919"/><path d="M41 26H51M41 32H48M41 38H45" stroke="white" stroke-width="2"/><text x="71" y="36" fill="#191919" font-size="16" font-weight="600">BEI</text><text x="110" y="36" fill="#6b7789" font-size="11">Enterprise Intelligence</text><text x="62" y="114" fill="#bdc7d8" font-size="16">本地模型、数据工程、可探索的公开信息</text><text x="60" y="180" fill="white" font-size="45" font-weight="600">让公开数据，成为有据可查的企业情报。</text><text x="62" y="224" fill="#cbd5e1" font-size="14">数据笔记本：三张完整卡片、有限侧边预览、首尾连续循环</text><g clip-path="url(#window)">''']
def card(x,title,label):
 return f'<g transform="translate({x} 295)"><rect width="294" height="340" fill="white" stroke="#dce3ed"/><rect x="14" y="10" width="64" height="20" rx="10" fill="#f6f8fb" stroke="#e2e7ee"/><text x="46" y="24" text-anchor="middle" fill="#536178" font-size="9">{label}</text><path d="M271 12h5v5M266 27h-5v-5" fill="none" stroke="#8b9097" stroke-width="1.4"/><text x="16" y="51" fill="#263247" font-size="15" font-weight="600">{title}</text><g transform="translate(0 25)">'
s.append(card(-156,'执行进度快照','执行进度'))
pts=d['progress']['points'];lo=min(x['completed'] for x in pts);hi=max(x['completed'] for x in pts)
p=' '.join(('M' if i==0 else 'L')+f'{20+i*36:.1f} {240-(v["completed"]-lo)/(hi-lo)*160:.1f}' for i,v in enumerate(pts))
s.append(f'<path d="{p}" fill="none" stroke="#4269d0" stroke-width="3"/></g></g>')
s.append(card(150,'展开后的文件是什么样？','文件概览'))
counts=Counter()
for v in d['formats']:counts[v['format']]+=v['files']
a=-math.pi/2
for i,(name,n) in enumerate(counts.most_common()):
 b=a+n/d['corpus']['logical_files']*math.pi*2
 def pt(rad,angle):return f'{147+rad*math.cos(angle):.2f} {160+rad*math.sin(angle):.2f}'
 path=f'M{pt(102,a)}A102 102 0 {int(b-a>math.pi)} 1 {pt(102,b)}L{pt(52,b)}A52 52 0 {int(b-a>math.pi)} 0 {pt(52,a)}Z'
 s.append(f'<path d="{path}" fill="{colors[i%len(colors)]}" stroke="white"/>');a=b
s.append('<text x="147" y="163" text-anchor="middle" fill="#263247" font-size="19">11,701</text><text x="147" y="181" text-anchor="middle" fill="#7b8799" font-size="9">逻辑文件</text><text x="16" y="290" fill="#7b8799" font-size="9">格式 × 解析状态 / 全批元数据</text></g></g>')
s.append(card(454,'许可相关记录，分成十类。','事件分类'))
events=Counter()
for v in d['events']:
 if v['type'] in d['taxonomy']['refined_types']:events[v['label']]+=v['count']
for i,(name,n) in enumerate(events.most_common()):
 y=54+i*17
 s.append(f'<text x="64" y="{y+10}" text-anchor="end" fill="#657187" font-size="8">{name}</text><rect x="72" y="{y}" width="{n/max(events.values())*177:.1f}" height="12" fill="{colors[i%len(colors)]}"/>')
s.append('<rect x="13" y="249" width="268" height="40" fill="#f6f8fb"/><text x="22" y="265" fill="#b65b2a" font-size="8" font-family="Consolas,monospace">SELECT event_type, status, count(*)</text><text x="22" y="279" fill="#4d6788" font-size="8" font-family="Consolas,monospace">FROM classified_events GROUP BY event_type;</text></g></g>')
s.append(card(758,'相同内容，只理解一次。','内容去重'))
s.append('<text x="17" y="78" fill="#6b7789" font-size="11">1,440,619 条来源记录</text><path d="M25 105C110 105 150 93 251 93L251 127C150 127 110 138 25 138Z" fill="#4269d0"/><path d="M25 140C110 140 150 147 251 147L251 221C150 221 110 216 25 216Z" fill="#bdd0f5"/><text x="147" y="259" text-anchor="middle" fill="#4269d0" font-size="25">1 − U/N = 73.0%</text><text x="18" y="290" fill="#7b8799" font-size="9">比例表示重复来源，原始位置全部保留</text></g></g>')
s.append(card(1062,'三维文件空间','文件空间'))
for i,v in enumerate(d['file_space']['bins']):
 s.append(f'<circle cx="{25+i%7*36}" cy="{85+i//7*25}" r="{min(10,3+math.sqrt(v["files"])*.16):.2f}" fill="{colors[i%len(colors)]}" stroke="white"/>')
s.append('</g></g></g>')
for i in range(7):s.append(f'<circle cx="{520+i*21}" cy="659" r="4" fill="#cdd5df"/>')
s.append('<rect x="536" y="655" width="43" height="8" rx="4" fill="#344155"/><text x="600" y="697" text-anchor="middle" fill="#7b8799" font-size="10">独立绘制的项目预览示意 / 原位方法分页 / 可放大阅读 / 合成示例与真实汇总分别标明</text></g></svg>')
(r/'assets/project-preview.svg').write_text(''.join(s),encoding='utf-8')
print('Updated cover: three complete notebooks, clipped neighbors and reading window.')
