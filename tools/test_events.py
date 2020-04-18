from datetime import datetime
import logging
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
    if len(sys.argv) not in (5, 6):
        print(f'{sys.argv[0]} host port user password [log]')
        sys.exit(1)

    host = sys.argv[1]
    port = sys.argv[2]
    user = sys.argv[3]
    pswd = sys.argv[4]
    log = len(sys.argv) == 6
    if log:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s: %(name)s: %(message)s",
        )
        urllib3_logger = logging.getLogger("urllib3.connectionpool")
        if not any(isinstance(x, NoHeaderErrorFilter) for x in urllib3_logger.filters):
            urllib3_logger.addFilter(NoHeaderErrorFilter())

    cam = Http(host, port, user, pswd, retries_connection=1, timeout_protocol=3.05)

    dev_type = cam.device_type
    if log:
        print()
    print(dev_type.strip())
    if log:
        print()

    sw_info = cam.software_information
    if log:
        print()
    for info in sw_info:
        print(info.strip())
    if log:
        print()

    ver_http = cam.version_http_api
    if log:
        print()
    print(ver_http.strip())
    if log:
        print()

    ret = cam.command(
        'eventManager.cgi?action=attach&codes=[VideoMotion]',
        timeout_cmd=(3.05, None), stream=True)
    ret.encoding = 'utf-8'
    print()

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


class NoHeaderErrorFilter(logging.Filter):
    """
    Filter out urllib3 Header Parsing Errors due to a urllib3 bug.

    See https://github.com/urllib3/urllib3/issues/800
    """

    def filter(self, record):
        """Filter out Header Parsing Errors."""
        return "Failed to parse headers" not in record.getMessage()


if __name__ == '__main__':
    main()
