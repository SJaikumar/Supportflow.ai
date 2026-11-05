"""Background SLA and notification worker; run separately from Streamlit.

    python -m supportflow.worker --once
    python -m supportflow.worker --interval 30 --auto-refunds

The worker is optional for previewing the interface, but is required for ongoing
24x7 SLA reminders. No external messaging or real payment APIs are used.
"""
from __future__ import annotations
import argparse
import logging
import time
from .db import initialize
from .operations import run_tick


def main(argv=None):
    parser = argparse.ArgumentParser(description='SupportFlow operational worker')
    parser.add_argument('--once', action='store_true', help='Run one sweep and quit')
    parser.add_argument('--interval', type=int, default=60, help='Seconds between checks (min 10)')
    parser.add_argument('--auto-refunds', action='store_true',
                        help='Process human-approved simulated refunds automatically')
    parser.add_argument('--refund-delay', type=int, default=60,
                        help='Wait N seconds after approval before completing simulated refund')
    args = parser.parse_args(argv)
    if not args.once and args.interval < 10:
        parser.error('--interval must be at least 10 seconds')
    if args.refund_delay < 0:
        parser.error('--refund-delay cannot be negative')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    initialize()
    while True:
        try:
            result = run_tick(process_refunds=args.auto_refunds,
                              refund_delay_seconds=args.refund_delay)
            logging.info('SLA sweep finished: %s', result)
        except Exception:
            logging.exception('SLA worker failed. Next sweep will retry unchanged records.')
            if args.once:
                raise
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
