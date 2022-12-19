#!/usr/bin/env python3

from collections import OrderedDict
import re
import sys


try:
    filename = sys.argv[1]
    if '.' not in sys.argv[2]:
        raise ValueError
except:
    print('Usage: python3 {} filename (entity_id [attribute...])...'.format(sys.argv[0]))
    sys.exit(1)

attrs = {}
entity_id = None
for arg in sys.argv[2:]:
    if '.' in arg:
        if entity_id is not None:
            attrs[entity_id] = entity_attrs
        entity_id = arg
        entity_attrs = []
    else:
        entity_attrs.append(arg)
attrs[entity_id] = entity_attrs

haevent = re.compile(
    r'([0-9-]+ [0-9:.]+).*homeassistant_(start|started|stop|final_write|close)\[.*'
)
new_state_none = re.compile(r'([0-9-]+ [0-9:.]+)(.*)new_state=None(.*)')
ent_id = re.compile(r'.*entity_id=([^,>]+).*')
new_state = re.compile(
    r'([0-9-]+ [0-9:.]+).*new_state=<state ([^=]+)=([^;]*); (.*) @ ([0-9+-:.T]+)>.*')
new_state2 = re.compile(
    r'([0-9-]+ [0-9:.]+).*new_state=<state ([^=]+)=([^@]*) @ ([0-9+-:.T]+)>.*')

ent_hdr = 'entity_id'
max_ent = len(ent_hdr)
ts_hdr = 'log time'
max_ts = len(ts_hdr)
lc_hdr = 'last_changed'
max_lc = len(lc_hdr)
state_hdr = 'state'
max_state = len(state_hdr)
if len(attrs) == 1:
    max_attr = {}
    for attr in entity_attrs:
        max_attr[attr] = len(attr)
else:
    attr_hdr = 'attributes'

HAEVENT = 'Home Assistant'
HAFMT = ' {} {{}} '.format(HAEVENT)

states = []
with open(filename) as f:
    for line in f:
        m = haevent.match(line)
        if m:
            ts = m.group(1)
            max_ts = max(max_ts, len(ts))
            last_changed = HAFMT.format(m.group(2).replace('_', ' ').title())
            max_lc = max(max_lc, len(last_changed))
            states.append((None, ts, last_changed, None, None))
            continue

        m = new_state_none.match(line)
        if m:
            n = ent_id.match(m.group(2)) or ent_id.match(m.group(3))
            entity_id = n.group(1)
            if entity_id in attrs:
                max_ent = max(max_ent, len(entity_id))
                ts = m.group(1)
                max_ts = max(max_ts, len(ts))
                state = '=== None ==='
                max_state = max(max_state, len(state))
                states.append((entity_id, ts, '', state, {}))
            continue

        m = new_state.match(line)
        if m:
            s = m.group(4)
            last_changed = m.group(5)
        else:
            m = new_state2.match(line)
            s = ''
            last_changed = m.group(4) if m else ''
        if m and m.group(2) in attrs:
            entity_id = m.group(2)
            max_ent = max(max_ent, len(entity_id))
            ts = m.group(1)
            max_ts = max(max_ts, len(ts))
            max_lc = max(max_lc, len(last_changed))
            state = m.group(3)
            max_state = max(max_state, len(state))
            _attrs = OrderedDict()
            for attr in attrs[entity_id]:
                try:
                    start = s.index(attr+'=')+len(attr)+1
                    _attr = s[start:s.rfind(', ', start, s.find('=', start))]
                except:
                    _attr = '???'
                _attrs[attr] = _attr
            if len(attrs) == 1:
                for attr in entity_attrs:
                    max_attr[attr] = max(max_attr[attr], len(_attrs[attr]))
            states.append((entity_id, ts, last_changed, state, _attrs))

if len(attrs) > 1:
    print('{:{}} | '.format(ent_hdr, max_ent), end='')
print('{:{}} | {:{}} | {:{}}'.format(ts_hdr, max_ts, lc_hdr, max_lc, state_hdr, max_state), end='')
if len(attrs) == 1:
    for attr in entity_attrs:
        print(' | {:{}}'.format(attr, max_attr[attr]), end='')
else:
    print(' | {}'.format(attr_hdr), end='')
print('')

if len(attrs) > 1:
    print('-'*max_ent, end='-|-')
print('-'*max_ts, '-'*max_lc, '-'*max_state, sep='-|-', end='')
if len(attrs) == 1:
    for attr in entity_attrs:
        print('', '-'*max_attr[attr], sep='-|-', end='')
else:
    print('-|-', end='')
    print('-'*len(attr_hdr), end='')
print('')

prev_entity_id = None
for entity_id, ts, last_changed, state, _attrs in states:
    if HAEVENT in last_changed:
        entity_id = '='*max_ent
        last_changed = '{:=^{}}'.format(last_changed, max_lc)
        state = '='*max_state
        if len(attrs) == 1:
            _attrs = OrderedDict()
            for attr in entity_attrs:
                _attrs[attr] = '='*max_attr[attr]
        else:
            _attrs = {'=': '='*(len(attr_hdr)-2)}
    if len(attrs) > 1:
        print('{:{}} | '.format('' if entity_id == prev_entity_id and HAEVENT not in last_changed else entity_id, max_ent), end='')
    prev_entity_id = entity_id
    print('{:{}} | {:{}} | {:{}}'.format(ts, max_ts, last_changed , max_lc, state , max_state), end='')
    if len(attrs) == 1:
        for k,v in _attrs.items():
            print(' | {:{}}'.format(v if HAEVENT not in last_changed else '='*max_attr[k], max_attr[k]), end='')
    else:
        print(' |', end='')
        for k,v in _attrs.items():
            print(' {}={}'.format(k, v), end='')
    print('')
