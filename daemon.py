#!/usr/bin/env python3

import os
import argparse
import subprocess
import xml.etree.ElementTree as ET

NTP_CONF = "ntp.conf"

parser = argparse.ArgumentParser()
parser.add_argument("config", help="path to config")
args = parser.parse_args()

tree = ET.parse(args.config)
root = tree.getroot()

ntp_conf = []
ptp_args = ["ptpd"]
ptp_enabled = False

method = root.find("time-source").find("method").text
if method == "ntp":
    ntp = root.find("time-source").find("ntp-source")
    for server in ntp.find("sources").findall("server"):
        # TODO: implement prefer
        ntp_conf.append("server %s minipoll 4 maxpoll 4 iburst" % server.text)
    if ntp.find("driftfile") is not None:
        ntp_conf.append("driftfile %s" % ntp.find("driftfile").text)
elif method == "ptp":
    ptp = root.find("time-source").find("ptp-source")
    ptp_enabled = True

ntp_distribution = root.find("time-distribution").find("ntp-distribution")
if ntp_distribution is not None:
    stratum = ntp_distribution.find("stratum").text
    ntp_conf.append("server 127.127.1.0")
    ntp_conf.append("fudge 127.127.1.0 stratum %s" % stratum)

if ntp_conf:
    with open(NTP_CONF, "w") as f:
        for line in ntp_conf:
            f.write(line)
            f.write("\n")
    ntp = subprocess.Popen(["ntpd", "-c", "ntp.conf"])

if ptp_enabled:
    ptp = subprocess.Popen(ptp_args)

