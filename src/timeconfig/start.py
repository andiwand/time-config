#!/usr/bin/env python3

# TODO: add gps/pps

import os
import re
import sys
import pwd
import argparse
import syslog
import subprocess
import xml.etree.ElementTree as ET

SYSLOG_PREFIX = "pd time deamon: "

baud_map = { "4800": 0, "9600": 16, "19200": 32, "38400": 48, "57600": 64, "115200": 80 }
sentence_map = { "$GPMRC": 1, "$GPGGA": 2, "$GPGLL": 4, "$GPZDA": 8, "$GPZDG": 8 }

def log(msg):
    syslog.syslog("%s%s" % (SYSLOG_PREFIX, msg))
    print(msg)

def parse_config(args):
    log("parsing config...")
    tree = ET.parse(args.config)
    root = tree.getroot()
    
    files = {
        "ntp": { "config": "ntp.config", "pid": "/var/run/ntpd.pid", "drift": "/var/lib/ntp/drift" },
        "ptp": { "log": "/var/log/ptp.log", "lock": "/var/run/ptpd.lock", "statistics": "/var/log/ptp.stats" }
    }
    
    directory = os.getcwd()
    if root.find("files") is not None:
        directory = root.find("files").text
    
    directory = os.path.abspath(directory)
    for mf in files:
        for f in files[mf]:
            if not os.path.isabs(files[mf][f]): files[mf][f] = os.path.join(directory, files[mf][f])

    ntp_user = "%s:%s" % (pwd.getpwnam("ntp").pw_uid, pwd.getpwnam("ntp").pw_gid)
    ntp_config = []
    ntp_args = [ "ntpd", "-g", "-p", files["ntp"]["pid"], "-u", ntp_user, "-c", files["ntp"]["config"], "-f", files["ntp"]["drift"] ]
    ptp_args = [ "ptpd", "-f", files["ptp"]["log"], "-l", files["ptp"]["lock"], "-S", files["ptp"]["statistics"] ]
    
    next_unit = { "local": 0, "pps": 0, "nmea": 0 }
    
    method = root.find("time-source").find("method").text if root.find("time-source").find("method") is not None else "none"
    log("configuring method %s..." % method)
    if method == "none":
        pass
    elif method == "ntp":
        ntp_config.append("tos mindist 0.4") # TODO: check vaule
        ntp = root.find("time-source").find("ntp-source")
        prefer = " prefer"
        for source in ntp.find("sources"):
            if source.tag == "server":
                ntp_config.append("server %s minipoll 4 maxpoll 4 iburst%s" % (source.text, prefer))
            elif source.tag == "reference-clock":
                driver = source.find("driver").text
                #stratum = source.find("stratum").text
                if driver == "local":
                    # http://doc.ntp.org/current-stable/drivers/driver1.html
                    
                    unit = next_unit["local"]
                    next_unit["local"] += 1
                    
                    ntp_config.append("server 127.127.1.%d minpoll 4 maxpoll 4%s" % (unit, prefer))
                    #ntp_config.append("fudge 127.127.1.%d stratum %s" % (unit, stratum))
                elif driver == "pps":
                    # http://doc.ntp.org/current-stable/drivers/driver22.html
                    
                    device = source.find("device").text
                    m = re.match(r"/dev/pps(\d+)", device)
                    if m:
                        unit = int(m.group(1))
                        next_unit["pps"] = unit + 1
                    else:
                        unit = next_unit["pps"]
                        next_unit["pps"] += 1
                    
                    if device != "/dev/pps%d" % unit:
                        log("symlink %s to /dev/pps%d" % (device, unit))
                        if not args.dry_run: os.symlink(device, "/dev/pps%d" % unit)
                    
                    ntp_config.append("server 127.127.22.%d minpoll 4 maxpoll 4%s" % (unit, prefer))
                    #ntp_config.append("fudge 127.127.22.%d stratum %s" % (unit, stratum))
                    ntp_config.append("fudge 127.127.22.%d flag3 1" % unit) # enable kernel PPS discipline
                elif driver == "nmea":
                    # http://doc.ntp.org/current-stable/drivers/driver20.html
                    
                    device = source.find("device").text
                    pps_device = source.find("pps-device").text if source.find("pps-device") is not None else None
                    init_script = source.find("init-script").text if source.find("init-script") is not None else None
                    unit = next_unit["nmea"]
                    next_unit["nmea"] += 1
                    
                    serial_offset = source.find("serial-offset").text if source.find("serial-offset") is not None else "0"
                    baud = source.find("baud").text if source.find("baud") is not None else "9600"
                    sentence = source.find("sentense").text if source.find("sentence") is not None else "$GPZDG"
                    mode = baud_map[baud] | sentence_map[sentence]
                    
                    log("symlink %s to /dev/gps%d" % (device, unit))
                    if not args.dry_run: os.symlink(device, "/dev/gps%d" % unit)
                    if pps_device is not None:
                        log("symlink %s to /dev/gpspps%d" % (pps_device, unit))
                        if not args.dry_run: os.symlink(pps_device, "/dev/gpspps%d" % unit)
                    
                    if init_script:
                        log("execute init-script...")
                        if not args.dry_run: subprocess.call("cat %s > %s" % (init_script, device), shell=True)
                        if not args.dry_run: subprocess.call("stty -F %s raw %s cs8 clocal -cstopb" % (device, baud))
                    
                    ntp_config.append("server 127.127.20.%d mode %d minpoll 4 maxpoll 4%s" % (unit, mode, prefer))
                    #ntp_config.append("fudge 127.127.20.%d stratum %s" % (unit, stratum))
                    if pps_device is not None: ntp_config.append("fudge 127.127.20.%d flag1 1" % unit) # enable PPS
                    ntp_config.append("fudge 127.127.20.%d flag3 1" % unit) # kernel discipline
                    ntp_config.append("fudge 127.127.20.%d time2 %s" % (unit, serial_offset)) # serial offset
                else:
                    log("unknown reference clock.")
                    return None
            else:
                log("unknown clock source.")
                return None
            prefer = ""
        ntp_config.append("restrict -4 default kod nomodify notrap nopeer noquery")
        ntp_config.append("restrict -6 default kod nomodify notrap nopeer noquery")
        ntp_config.append("restrict 127.0.0.1")
        ntp_config.append("restrict ::1")
        # TODO: disable clock access
    elif method == "ptp":
        ptp = root.find("time-source").find("ptp-source")
        interface = ptp.find("interface").text
        ptp_args += [ "-i", interface, "-s", "-y", "-r", "0" ]
    else:
        log("unknown method.")
        return None

    ntp_dist = root.find("time-distribution").find("ntp-distribution")
    if ntp_dist is not None:
        log("configuring ntp distribution...")
        # TODO: enable clock access

    ptp_dist = root.find("time-distribution").find("ptp-distribution")
    if ptp_dist is not None:
        # TODO: error if ptp source
        log("configuring ptp distribution...")
        interface = ptp_dist.find("interface").text
        ptp_args += [ "-i", interface, "-M", "-n" ]

    ntp = { "files": files["ntp"], "config": ntp_config, "args": ntp_args } if ntp_config else None
    ptp = { "files": files["ptp"], "args": ptp_args } if "-i" in ptp_args else None

    return { "ntp": ntp, "ptp": ptp }

def start_ntp(args, config):
    with open(config["files"]["config"], "w") as f:
        for line in config["config"]:
            f.write(line)
            f.write("\n")
    log("kill old ntp deamon...")
    if not args.dry_run: subprocess.call([ "killall", "ntpd" ])
    log("starting ntp one-shot sync...")
    if not args.dry_run:
        err = subprocess.call(config["args"] + [ "-q", ])
        if err: return err
    log("starting ntp daemon...")
    log(" ".join(config["args"]))
    err = 0
    if not args.dry_run: err = subprocess.call(config["args"])
    return err

def start_ptp(args, config):
    log("kill old ptp deamon...")
    if not args.dry_run: subprocess.call([ "killall", "ptpd" ])
    log("starting ptp daemon...")
    log(" ".join(config["args"]))
    err = 0
    if not args.dry_run: err = subprocess.call(config["args"])
    return err

def parse_args(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="path to config")
    parser.add_argument("--dry-run", help="don't start services", action="store_true")
    return parser.parse_args(args)

def main():
    syslog.openlog(logoption=syslog.LOG_PID)

    args = parse_args()
    config = parse_config(args)
    if not config:
        log("failed to parse config. exit.")
        return 1

    if config["ntp"]:
        err = start_ntp(args, config["ntp"])
        if err:
            log("faied to start ntp daemon. exit.")
            return 1
    if config["ptp"]:
        err = start_ptp(args, config["ptp"])
        if err:
            log("faied to start ptp daemon. exit.")
            return 1

    log("done.")
    return 0

if __name__ == "__main__":
    exit = main()
    sys.exit(exit)

