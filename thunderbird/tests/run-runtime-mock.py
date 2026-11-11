#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Reuse the existing POA, optionally replacing its Internet MIME fixture for UI tests."""
import argparse
import importlib.util
import os
import pathlib
import sys
from email.message import EmailMessage
from email.policy import SMTP

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--html',action='store_true')
args, command=parser.parse_known_args()
if not command:
    parser.error('a test command is required')
mock=pathlib.Path(__file__).resolve().parents[2]/'tests/mock/run-with-mock.py'
spec=importlib.util.spec_from_file_location('runtime_mock',mock)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if args.html:
    message=EmailMessage(policy=SMTP)
    message['From']='Bob <bob@phantom.com>'
    message['To']='User One <u1@phantom.com>'
    message['Subject']='Test message'
    message['Message-ID']='<orig-1@phantom.com>'
    message['X-Original-MIME']='yes'
    message.set_content('Hello, plain fallback.\n')
    message.add_alternative('<html><body><p id="groupwise-html">Hello, HTML fixture.</p></body></html>',subtype='html')
    message.add_attachment(b'GroupWise attachment fixture\n',maintype='application',subtype='octet-stream',filename='proof.txt')
    module.ORIGINAL=message.as_bytes()
    os.environ['GW_RUNTIME_HTML']='1'
os.environ['GW_RUNTIME_MIME_SIZE']=str(len(module.ORIGINAL))
sys.argv=[sys.argv[0],*command]
raise SystemExit(module.main())
