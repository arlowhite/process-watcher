#!/usr/bin/env python3

import sys
import argparse
from argparse import RawTextHelpFormatter
import logging

from process import *

# Remember to update README.md after modifying
parser = argparse.ArgumentParser(formatter_class=RawTextHelpFormatter,
                                 description="""Watch a process and notify when it completes via various \
communication protocols.
(See README.md for help installing dependencies)

[+] indicates the argument may be specified multiple times, for example:
 %(prog)s -p 1234 -p 4258 -c myapp* -crx "exec\d+" --to person1@domain.com --to person2@someplace.com
""")

parser.add_argument('-p', '--pid', help='process ID(s) to watch [+]',
                    type=int,
                    action='append', default=[])
parser.add_argument('-c', '--command',
                    help='watch all processes matching the command name pattern. (shell-style wildcards) [+]',
                    action='append', default=[], metavar='COMMAND_PATTERN')
parser.add_argument('-crx', '--command-regex',
                    help='watch all processes matching the command name regular expression. [+]',
                    action='append', default=[], metavar='COMMAND_REGEX')
parser.add_argument('-w', '--watch-new', help='watch for new processes that match --command. '
                                              '(run forever)', action='store_true')
parser.add_argument('--to', help='email address to send to [+]', action='append', metavar='EMAIL_ADDRESS')
parser.add_argument('--id', help='pushover user id [+]', action='append', metavar='USER_ID')
parser.add_argument('--t', help='pushover api token [+]', action='append', metavar='API_TOKEN')
parser.add_argument('--channel', help='channel to send to [+]', action='append')
parser.add_argument('-n', '--notify', help='send DBUS Desktop notification', action='store_true')
parser.add_argument('-i', '--interval', help='how often to check on processes. (default: 15.0 seconds)',
                    type=float, default=15.0, metavar='SECONDS')
parser.add_argument('-q', '--quiet', help="don't print anything to stdout except warnings and errors",
                    action='store_true')
parser.add_argument('--log', help="log style output (timestamps and log level)", action='store_true')
parser.add_argument('--tag', help='label for process [+]', action='append', metavar='LABEL')

# Just print help and exit if no arguments specified.
if len(sys.argv) == 1:
    print('No arguments given, printing help:\n')
    parser.print_help()
    sys.exit()

args = parser.parse_args()

log_level = logging.WARNING if args.quiet else logging.INFO
log_format = '%(asctime)s %(levelname)s: %(message)s' if args.log else '%(message)s'
logging.basicConfig(format=log_format, level=log_level)


# Load communication protocols based present arguments
# (library, send function keyword args)
comms = []
if args.to:
    try:
        import communicate.email
        comms.append((communicate.email, {'to': args.to}))
    except:
        logging.exception('Failed to load email module. (required by --to)')
        sys.exit(1)

if args.channel:
    try:
        import communicate.slack
        comms.append((communicate.slack, {'channel': args.channel}))
    except:
        logging.exception('Failed to load slack module. (required by --channel)')
        sys.exit(1)

if args.notify:
    exception_message = 'Failed to load Desktop Notification module. (required by --notify)'
    try:
        import communicate.dbus_notify
        comms.append((communicate.dbus_notify, {}))
    except ImportError as err:
        if err.name == 'notify2':
            logging.error("{}\n 'notify2' python module not installed.\n"
                          " pip install notify2"
                          " (you also need to install the python3-dbus system package)".format(exception_message))
        else:
            logging.exception(exception_message)
        sys.exit(1)
    except:
        logging.exception(exception_message)
        sys.exit(1)

if args.id and args.t:
    try:
        import communicate.pushover
        comms.append((communicate.pushover, {'user_id': args.id, 'api_token': args.t}))
    except:
        logging.exception("Failed to setup Pushover.")
        sys.exit(1)


# dict of all the process watching objects pid -> ProcessByPID
# items removed when process ends
watched_processes = {}

# Initialize processes from arguments, get metadata
for pid in args.pid:
    try:
        if pid not in watched_processes:
            watched_processes[pid] = ProcessByPID(pid)

    except NoProcessFound as ex:
        logging.warning('No process with PID {}'.format(ex.pid))

process_matcher = ProcessMatcher()
new_processes = ProcessIDs()

for pattern in args.command:
    process_matcher.add_command_wildcard(pattern)

for regex in args.command_regex:
    process_matcher.add_command_regex(regex)

# Initial processes matching conditions
for pid in process_matcher.matching(new_processes):
    if pid not in watched_processes:
        watched_processes[pid] = ProcessByPID(pid)

# Whether program needs to check for new processes matching conditions
# Would a user ever watch for a specific PID number to recur?
watch_new = args.watch_new and process_matcher.num_conditions > 0

if not watched_processes and not watch_new:
    logging.warning('No processes found to watch.')
    sys.exit()

logging.info('Watching {} processes:'.format(len(watched_processes)))
for pid, process in watched_processes.items():
    logging.info(process.info())

try:
    to_delete = []
    while True:
        time.sleep(args.interval)
        # Need to iterate copy since removing within loop.
        for pid, process in watched_processes.items():
            try:
                running = process.check()
                if not running:
                    to_delete.append(pid)

                    logging.info('Process stopped\n%s', process.info())

                    for comm, send_args in comms:
                        if args.tag:
                            template = '{executable} process {pid} ended' + ': {}'.format(args.tag)
                        else:
                            template = '{executable} process {pid} ended'
                        
                        comm.send(process=process, subject_format=template, **send_args)

            except:
                logging.exception('Exception encountered while checking or communicating about process {}'.format(pid))

                if pid not in to_delete:
                    # Exception raised in check(), queue PID to be deleted
                    to_delete.append(pid)

        if to_delete:
            for pid in to_delete:
                del watched_processes[pid]

            to_delete.clear()

        if watch_new:
            for pid in process_matcher.matching(new_processes):
                try:
                    watched_processes[pid] = p = ProcessByPID(pid)
                    logging.info('watching new process\n%s', p.info())

                except:
                    logging.exception('Exception encountered while attempting to watch new process {}'.format(pid))

        elif not watched_processes:
            sys.exit()

except KeyboardInterrupt:
    # Force command prompt onto new line
    print()
