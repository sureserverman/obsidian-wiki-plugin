"""One bounded stdin JSON request; configured roots never enter public requests."""
import os
from pathlib import Path
import subprocess
import sys

from .contracts import Refusal, REQUEST_BYTES, decode, encode, error, validate_request
from .service import configuration, configured_service


def exit_code(result):
    if result['ok']:return 0
    if result['state'] in ('invalid_request','unsupported_schema','unsupported_filter'):return 2
    if result['state']=='budget_exhausted':return 3
    if result['state']=='invalid_receipt':return 5
    return 4


def resolve_source():
    # Use the existing resolver and its exact precedence. No request/query value
    # enters an argument, environment assignment, or shell program.
    resolver=Path(__file__).resolve().parents[1]/'resolve-vault.sh'
    try:
        child=subprocess.run(['bash',str(resolver)],stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL,timeout=10,check=False)
        root=child.stdout.decode('utf-8').rstrip('\n')
        if child.returncode or not root.startswith('/') or '\n' in root or len(root.encode())>4096:
            raise Refusal('source_unavailable')
        return root
    except (OSError,UnicodeError,subprocess.TimeoutExpired):
        raise Refusal('source_unavailable') from None


def main(*, admin=False):
    operation='unknown'
    try:
        args=sys.argv[1:]
        rotate=admin and args==['--rotate-receipt-key']
        if args and not rotate:raise Refusal('invalid_request')
        raw=sys.stdin.buffer.read(REQUEST_BYTES+1)
        request=decode(raw)
        if type(request) is dict and type(request.get('operation')) is str:
            operation=request['operation']
        request=validate_request(request,admin=admin)
        if rotate and operation!='refresh':raise Refusal('invalid_request')
        home=Path.home()
        config_base=Path(os.environ.get('XDG_CONFIG_HOME') or home/'.config')
        config_path=config_base/'obsidian-wiki/wiki-access.json'
        config=configuration(config_path)
        state_base=Path(os.environ.get('XDG_STATE_HOME') or config_base)
        root=resolve_source()
        service=configured_service(root,state_base,config)
        result=service.administer(request,rotate=rotate) if admin else service.handle(request)
        if result['ok']:
            if configuration(config_path)!=config or resolve_source()!=root:
                raise Refusal('generation_stale')
    except Refusal as refusal:result=error(operation,refusal.code)
    except Exception:
        # The public boundary must never print a traceback containing private paths,
        # queries or source data, including for unexpected backend failures.
        result=error(operation,'index_unavailable')
    # Buffer all output until the service has completed its source/key checks.
    # No framing newline: signed response_bytes equals the bytes on stdout.
    sys.stdout.buffer.write(encode(result))
    return exit_code(result)
