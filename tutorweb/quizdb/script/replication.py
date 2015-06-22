# -*- coding: utf-8 -*-
import argparse
import calendar
import json
import logging
import os
import os.path
import urlparse
import socket
import time

from ..replication.dump import dumpData, dumpIsEmpty
from ..replication.ingest import ingestData

logger = logging.getLogger(__package__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


def getApplication(configFile):
    """Start Zope/Plone based on a config, return root app"""
    from Zope2.Startup.run import configure
    configure(configFile)
    import Zope2
    return Zope2.app()


def replicateIngest():
    parser = argparse.ArgumentParser(description='Ingest new data in work dir')
    parser.add_argument(
        '--work-dir',
        help='Where dumps should be stored',
    )
    parser.add_argument(
        '--zope-conf',
        help='Zope configuration file',
    )
    args = parser.parse_args()

    app = getApplication(args.zope_conf)
    import transaction

    for fileName in os.listdir(args.work_dir):
        if not fileName.endswith('.json'):
            continue
        logger.info("Ingesting dump %s", fileName)

        # Open dump and ingest
        with open(os.path.join(args.work_dir, fileName), 'r') as f:
            ingestData(json.load(f))
        transaction.commit()

        # Worked, move this file to archive
        os.renames(
            os.path.join(args.work_dir, fileName),
            os.path.join(args.work_dir, 'archive', fileName),
        )


def replicateDump():
    parser = argparse.ArgumentParser(description='Dump out data since last dump')
    parser.add_argument(
        '--work-dir',
        help='Where dumps should be stored',
    )
    parser.add_argument(
        '--zope-conf',
        help='Zope configuration file',
    )
    parser.add_argument(
        '--max-values',
        type=int,
        default=None,
        help='Maximum answers to export, to constrain file size',
    )
    args = parser.parse_args()

    # Open work_dir, get most recent state
    listing = [os.path.join(args.work_dir, f) for f in os.listdir(args.work_dir) if f.endswith('.json')]
    if listing:
        stateFile = max(listing, key = os.path.getctime)
        logger.info("Reading statefile %s", stateFile)
        with open(stateFile, 'r') as f:
            state = json.load(f)['state']
    else:
        logger.info("No statefile, starting afresh")
        state = {}
    if args.max_values:
        state['maxVals'] = args.max_values

    # Start Zope, get dump
    logger.info("Dumping data")
    app = getApplication(args.zope_conf)
    out = dumpData(state)
    if dumpIsEmpty(out):
        logger.info("Nothing new to write out")
        return 0

    # Write dump out to new file, try to be atomic
    newFile = os.path.join(args.work_dir, 'dump-%s-%d.json' % (
        socket.getfqdn(),
        calendar.timegm(time.gmtime()),
    ))
    logger.info("Writing dump %s", newFile)
    with open(newFile + '.writing', 'w') as f:
        json.dump(out, f)
    os.rename(newFile + '.writing', newFile)
