import re

p = re.compile(r'\d+-\d+-\d+\s+\d+:\d+:\d+\s+([A-Z]+)[^[]*\[([^]]+)\]')
comps = {}
n_comps = 0
for line in open('home-assistant.log').readlines():
    m = p.match(line)
    if m:
        comp = (m.group(2), m.group(1))
        comps[comp] = comps.get(comp, 0) + 1
        n_comps += 1
for comp in sorted(comps.items(), key=lambda x: x[1], reverse=True):
    print(comp[0][0], comp[0][1], comp[1])
print('total:', n_comps)
