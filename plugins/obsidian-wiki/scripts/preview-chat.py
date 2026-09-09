#!/usr/bin/env python3
import hashlib,json,sys
r=json.load(open(sys.argv[1])); patches=r.get('patches',[])
print(json.dumps({'digest':hashlib.sha256(json.dumps(patches,sort_keys=True).encode()).hexdigest(),'patches':patches,'apply_authorized':False},sort_keys=True))
