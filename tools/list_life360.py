import sys

from life360 import life360

_API_TOKEN = 'cFJFcXVnYWJSZXRyZTRFc3RldGhlcnVmcmVQdW1hbUV4dWNyRU'\
             'h1YzptM2ZydXBSZXRSZXN3ZXJFQ2hBUHJFOTZxYWtFZHI0Vg=='


def main():
    api = life360(_API_TOKEN, sys.argv[1], sys.argv[2], 3.05)
    for circle in api.get_circles():
        print('Circle: {}'.format(circle['name']))
        print('  Members:')
        for member in api.get_circle_members(circle['id']):
            first = member.get('firstName')
            last = member.get('lastName')
            if first and last:
                full_name = ' '.join([first, last])
            else:
                full_name = first or last
            print('    {}'.format(full_name))
        print('  Places:')
        for place in api.get_circle_places(circle['id']):
            print('    {}'.format(place['name']))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('{} username password'.format(sys.argv[0]))
        sys.exit(1)
    main()
