#!/usr/bin/env python3

from collections import OrderedDict
import re
import sys


try:
    filename = sys.argv[1]
    entity_id = sys.argv[2]
except:
    print('Usage: python3 {} filename entity_id [attribute...]'.format(sys.argv[0]))
    sys.exit(1)
attrs = sys.argv[3:]

new_state_format = r'([0-9-]+ [0-9:]+).*new_state=<state {}=([^;]+); (.*) @ ([0-9-:.T]+)>.*'

states = []
ts_hdr = 'log time'
max_ts = len(ts_hdr)
lu_hdr = 'last_updated'
max_lu = len(lu_hdr)
state_hdr = 'state'
max_state = len(state_hdr)
max_attr = {}
for attr in attrs:
    max_attr[attr] = len(attr)

with open(filename) as f:
    new_state = new_state_format.format(entity_id.replace('.', '\.'))
    p = re.compile(new_state)
    for line in f:
        m = p.match(line)
        if m:
            ts = m.group(1)
            max_ts = max(max_ts, len(ts))
            last_updated = m.group(4)
            max_lu = max(max_lu, len(last_updated))
            state = m.group(2)
            max_state = max(max_state, len(state))
            s = m.group(3)
            _attrs = OrderedDict()
            for attr in attrs:
                try:
                    start = s.index(attr+'=')+len(attr)+1
                    _attr = s[start:s.rfind(', ', start, s.find('=', start))]
                except:
                    _attr = '???'
                _attrs[attr] = _attr
                max_attr[attr] = max(max_attr[attr], len(_attr))
            states.append((ts, last_updated, state, _attrs))

print('{:{}} | {:{}} | {:{}}'.format(ts_hdr, max_ts, lu_hdr, max_lu, state_hdr, max_state), end='')
for attr in attrs:
    print(' | {:{}}'.format(attr, max_attr[attr]), end='')
print('')
print('-'*max_ts, '-'*max_lu, '-'*max_state, sep='-|-', end='')
for attr in attrs:
    print('', '-'*max_attr[attr], sep='-|-', end='')
print('')
for ts, last_updated, state, _attrs in states:
    print('{:{}} | {:{}} | {:{}}'.format(ts, max_ts, last_updated, max_lu, state, max_state), end='')
    for k,v in _attrs.items():
        print(' | {:{}}'.format(v, max_attr[k]), end='')
    print('')
