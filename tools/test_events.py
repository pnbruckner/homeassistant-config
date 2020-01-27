from datetime import datetime
import sys

from amcrest import Http


def lines(ret):
    line = ''
    for char in ret.iter_content(decode_unicode=True):
        line = line + char
        if line.endswith('\r\n'):
            yield line.strip()
            line = ''


def main():
    if len(sys.argv) != 5:
        print(f'{sys.argv[0]} host port user password')
        sys.exit(1)

    host = sys.argv[1]
    port = sys.argv[2]
    user = sys.argv[3]
    pswd = sys.argv[4]

    cam = Http(host, port, user, pswd, retries_connection=1, timeout_protocol=3.05)

    print(cam.device_type)
    print(*cam.software_information)

    ret = cam.command(
        'eventManager.cgi?action=attach&codes=[VideoMotion]',
        timeout_cmd=(3.05, None), stream=True)
    ret.encoding = 'utf-8'

    try:
        for line in lines(ret):
            if line.lower().startswith('content-length:'):
                chunk_size = int(line.split(':')[1])
                print(
                    datetime.now().replace(microsecond=0),
                    repr(next(ret.iter_content(
                        chunk_size=chunk_size, decode_unicode=True))),
                )
    except KeyboardInterrupt:
        ret.close()
        print(' Done!')


if __name__ == '__main__':
    main()
