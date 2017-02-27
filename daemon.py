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
ptp_args = []

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
    interface = ptp.find("interface").text
    logfile = ptp.find("logfile").text
    statisticsfile = ptp.find("statisticsfile").text
    ptp_args = ["ptpd", "-i", interface, "-s", "-r", "0", "-f", logfile, "-S", statisticsfile]

ntp_distribution = root.find("time-distribution").find("ntp-distribution")
if ntp_distribution is not None:
    stratum = ntp_distribution.find("stratum").text
    ntp_conf.append("server 127.127.1.0")
    ntp_conf.append("fudge 127.127.1.0 stratum %s" % stratum)

ptp_distribution = root.find("time-distribution").find("ptp-distribution")
if ptp_distribution is not None:
    interface = ptp_distribution.find("interface").text
    ptp_master_args = ["ptpd", "-i", interface, "-M", "-n"]

if ntp_conf:
    with open(NTP_CONF, "w") as f:
        for line in ntp_conf:
            f.write(line)
            f.write("\n")
    # TODO: config pid file
    ntp = subprocess.Popen(["ntpd", "-p", "/var/run/ntpd.pid", "-g", "-c", "ntp.conf"])

if ptp_args:
    ptp = subprocess.Popen(ptp_args)

