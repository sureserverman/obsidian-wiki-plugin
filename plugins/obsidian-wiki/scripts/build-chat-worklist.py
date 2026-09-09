#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])); seen=set(); out=[]
for e in r.get('events',[]):
 k=e['event_key']
 if k not in seen: seen.add(k); out.append({'event_key':k,'disposition':'pending'})
print(json.dumps({'units':out,'count':len(out)},sort_keys=True))
