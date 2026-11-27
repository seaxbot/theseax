# Independent recount of every figure in the hygiene story, straight from the raw FSA files (not hyg.json)
import json, glob, datetime
R = []
for f in glob.glob('/home/claude/fsa2/fsa-*.json'):
    R += json.load(open(f))
EAT = {'Restaurant/Cafe/Canteen','Takeaway/sandwich shop','Pub/bar/nightclub','Hotel/bed & breakfast/guest house','Mobile caterer'}
num = lambda r: r['rating'] in ('0','1','2','3','4','5')
by = lambda la: [r for r in R if r['la'] == la]
eat = [r for r in R if num(r) and r['type'] in EAT]
tw = [r for r in eat if r['type'] == 'Takeaway/sandwich shop']
chk = {}
chk['total businesses 15,436'] = len(R)
chk['eat rated 6,732'] = len(eat)
chk['eat 5 5,289'] = sum(r['rating']=='5' for r in eat)
chk['eat 5 pct 79'] = round(100*sum(r['rating']=='5' for r in eat)/len(eat))
chk['eat <=2 159'] = sum(r['rating'] in '012' for r in eat)
chk['eat <=2 pct 2'] = round(100*sum(r['rating'] in '012' for r in eat)/len(eat))
chk['tw rated 1,254'] = len(tw); chk['tw 5 839'] = sum(r['rating']=='5' for r in tw)
chk['tw below5 415'] = sum(r['rating']!='5' for r in tw); chk['tw below5 pct ~33'] = round(100*sum(r['rating']!='5' for r in tw)/len(tw),1)
for t in ('Restaurant/Cafe/Canteen','Pub/bar/nightclub'):
    x=[r for r in eat if r['type']==t]; chk[f'{t} below5 pct ~20'] = round(100*sum(r['rating']!='5' for r in x)/len(x),1)
chk['tw 4=232,3=152,<=2=31'] = (sum(r['rating']=='4' for r in tw), sum(r['rating']=='3' for r in tw), sum(r['rating'] in '012' for r in tw))
las = sorted({r['la'] for r in R})
for la in las:
    t=[r for r in tw if r['la']==la]; e=[r for r in eat if r['la']==la]
    chk[f'{la} tw5'] = f"{sum(r['rating']=='5' for r in t)}/{len(t)} = {100*sum(r['rating']=='5' for r in t)/len(t):.1f}% | eat5 {100*sum(r['rating']=='5' for r in e)/len(e):.1f}% | eat<=2 {sum(r['rating'] in '012' for r in e)}/{len(e)} {100*sum(r['rating'] in '012' for r in e)/len(e):.1f}% | min {min(int(r['rating']) for r in e)} | await {sum(1 for r in R if r['la']==la and r['type'] in EAT and r['rating']=='AwaitingInspection')}"
chk['awaiting eat 418'] = sum(1 for r in R if r['type'] in EAT and r['rating']=='AwaitingInspection')
T=datetime.date(2026,11,27)
def old(r):
    try: return (T-datetime.date.fromisoformat(r['date'][:10])).days > 5*365.25
    except: return False
chk['older than 5y 184'] = sum(old(r) for r in eat)
chk['zero eat'] = [(r['name'], r['la'], r['date'][:10], r['a1'], r['a2'], r['pending']) for r in eat if r['rating']=='0']
for k,v in chk.items(): print(k, '=>', v)
