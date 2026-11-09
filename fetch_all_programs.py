import urllib.request
import re
import json
import time

programs = {}
# All DU programs have code D... or search by letters
search_terms = [
    'd0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7', 'd8', 'd9',
    'bsp', 'pbsp', 'msp', 'pmsp', 'dok', 'psp',
    'it', 'dator', 'bio', 'kim', 'fiz', 'eko', 'psih', 'lingv', 'ties',
    'pedag', 'skol', 'vadib', 'bizn', 'maksl', 'muz', 'vest', 'filol', 'dizain'
]

for term in search_terms:
    url = f"https://luis.lu.lv/pls/pub/PUB_NOD.picker_response?l=1&p_kas=prg&p_au=D&p_mg=FO0064&p_fak=&p_lim=&p_nod=&p_sem=&p_krs=&p_pas=&p_tlp=&p_vrz=&p_gru=&p_search=search:{term}&p_max_rows=100&p_current_results=&p_filter="
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'label:"(.*?)"\s*,\s*value:"(.*?)"', content)
            for label, val in matches:
                programs[val] = label
    except Exception as e:
        print(f"Error fetching {term}: {e}")
    time.sleep(0.1)

print(f"Total programs discovered: {len(programs)}")
for code, name in sorted(programs.items()):
    print(f"{code}: {name}")

with open("du_all_programs.json", "w", encoding="utf-8") as f:
    json.dump(programs, f, ensure_ascii=False, indent=2)
