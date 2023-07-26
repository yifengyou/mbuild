#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
 Authors:
   yifengyou <842056007@qq.com>
"""

import argparse
import datetime
import glob
import logging
import os
import os.path
import subprocess
import sys
from logging.handlers import RotatingFileHandler

import select

CURRENT_VERSION = "0.1.0"
logger = None


def beijing_timestamp():
    utc_time = datetime.datetime.utcnow()
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    beijing_time = utc_time.astimezone(beijing_tz)
    return beijing_time.strftime("%Y/%m/%d %H:%M:%S")


def perror(str):
    print("Error: ", str)
    sys.exit(1)


def check_python_version():
    current_python = sys.version_info[0]
    if current_python == 3:
        return
    else:
        raise Exception('Invalid python version requested: %d' % current_python)


def do_exe_cmd(cmd, print_output=False, shell=False):
    stdout_output = ''
    stderr_output = ''
    if isinstance(cmd, str):
        cmd = cmd.split()
    elif isinstance(cmd, list):
        pass
    else:
        raise Exception("unsupported type when run do_exec_cmd", type(cmd))

    # print("Run cmd:" + " ".join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell)
    while True:
        # 使用select模块，监控stdout和stderr的可读性，设置超时时间为0.1秒
        rlist, _, _ = select.select([p.stdout, p.stderr], [], [], 0.1)
        # 遍历可读的文件对象
        for f in rlist:
            # 读取一行内容，解码为utf-8
            line = f.readline().decode('utf-8').strip()
            # 如果有内容，判断是stdout还是stderr，并打印到屏幕，并刷新缓冲区
            if line:
                if f == p.stdout:
                    if print_output == True:
                        print("STDOUT", line)
                    stdout_output += line + '\n'
                    sys.stdout.flush()
                elif f == p.stderr:
                    if print_output == True:
                        print("STDERR", line)
                    stderr_output += line + '\n'
                    sys.stderr.flush()
        if p.poll() is not None:
            break
    return p.returncode, stdout_output, stderr_output


def handle_stat(args):
    pass


def build_per_srpm(srpm):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # 获取srpm名称 N-V-R
    ret, srpm_name, stderr = do_exe_cmd(["rpm", "-qp", "--queryformat", "%{NAME}", srpm], print_output=False)
    if ret != 0:
        logger.error(f" query srpm file ret is not zero [{ret}] {stderr}")
        return
    srpm_name = srpm_name.strip()
    logger.info(f"srpm name : [{srpm_name}]")

    # 创建构建目录
    topdir = os.path.dirname(srpm)
    mbuilddir = os.path.join(topdir, srpm_name)
    if not os.path.exists(mbuilddir):
        os.makedirs(mbuilddir, exist_ok=True)
    logger.info(f" mbuild dir : {mbuilddir}")
    rpmbuilddir = os.path.join(mbuilddir, "rpmbuild_" + timestamp)
    if not os.path.exists(mbuilddir):
        os.makedirs(rpmbuilddir, exist_ok=True)
    logger.info(f" rpmbuild dir : {rpmbuilddir}")

    ret, stdout, stderr = do_exe_cmd(
        ["rpm", "-ivh", "--define", f"_topdir {rpmbuilddir}", f"{srpm}"],
        print_output=False
    )
    if ret != 0:
        logger.error(f" install srpm {srpm} to {rpmbuilddir} failed! [{ret}] {stderr}")
        return

    # 检查spec
    specs = glob.glob(f"{rpmbuilddir}/SPECS/*.spec")
    if len(specs) == 0:
        logger.error(f"no specs found!")
        return
    elif len(specs) > 1:
        logger.error(f"found spec more than one [{len(specs)}]")
        return
    spec = os.path.abspath(specs[0])
    logger.info(f" using spec {spec}")

    # 导出rpm -qa记录
    ret, stdout, stderr = do_exe_cmd(["rpm", "-qa"], print_output=False)
    if ret != 0:
        logger.error(f" query all rpm failed! [{ret}] {stderr}")
        return
    rpm_manifest = os.path.join(mbuilddir, "rpm-manifest_" + timestamp)
    with open(rpm_manifest, 'w') as fd:
        fd.write(stdout)

    # 导出rpm -qa记录
    ret, stdout, stderr = do_exe_cmd(["rpm", "-qa"], print_output=False)
    if ret != 0:
        logger.error(f" query all rpm failed! [{ret}] {stderr}")
        return
    rpm_manifest = os.path.join(mbuilddir, "rpm-manifest_" + timestamp)
    with open(rpm_manifest, 'w') as fd:
        fd.write(stdout)



def handle_build(args):
    global logger
    begin_time = beijing_timestamp()

    if not os.path.exists(args.workdir) or not os.path.isdir(args.workdir):
        print(f"{args.workdir} is not a valid directory")
        exit(1)

    workdir = os.path.abspath(args.workdir)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")

    logger = logging.getLogger("mbuild")
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(console_handler)
    logfile = os.path.join(args.workdir,
                           "mbuild_" + timestamp
                           )
    file_handler = RotatingFileHandler(
        filename=logfile,
        encoding='UTF-8',
        maxBytes=1024000,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(file_handler)

    logger.setLevel(logging.INFO)

    logger.info(f" workdir: {workdir}")
    if args.srpm:
        if not os.path.exists(args.srpm) or not os.path.isfile(args.srpm):
            print(f"{args.srpm} is not a valid srpm file")
            exit(1)
        srpm_path = os.path.abspath(args.srpm)
        build_per_srpm(srpm_path)
    else:
        srpms = glob.glob(f"{args.workdir}/*.src.rpm")
        if not srpms:
            print(f"No src.rpm found in {args.workdir}")
            exit(1)
        total = len(srpms)
        for index, srpm in enumerate(srpms):
            srpm_path = os.path.abspath(srpm)
            logger.info(f"[{index + 1}/{total}] build {srpm}")
            build_per_srpm(srpm_path)

    logger.info("All done!")


def main():
    global CURRENT_VERSION
    check_python_version()

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-v", "--version", action="store_true",
                        help="show program's version number and exit")
    parser.add_argument("-h", "--help", action="store_true",
                        help="show this help message and exit")

    subparsers = parser.add_subparsers()

    # 定义base命令用于集成
    parent_parser = argparse.ArgumentParser(add_help=False, description="mbuild - a tool for kernel development")
    parent_parser.add_argument("-V", "--verbose", default=None, action="store_true", help="show verbose output")
    parent_parser.add_argument("-j", "--job", default=os.cpu_count(), type=int, help="job count")
    parent_parser.add_argument("-o", "--output", default="mbuild.db", help="mbuild database file path")
    parent_parser.add_argument("-w", "--workdir", default=".", help="setup workdir")
    parent_parser.add_argument('-l', '--log', default=None, help="log file path")
    parent_parser.add_argument('-d', '--debug', default=None, action="store_true", help="enable debug output")
    parent_parser.add_argument('-s', '--srpm', default=None, help="build specific srpm")

    # 添加子命令 stat
    parser_stat = subparsers.add_parser('stat', parents=[parent_parser])
    parser_stat.set_defaults(func=handle_stat)

    # 添加子命令 build
    parser_build = subparsers.add_parser('build', parents=[parent_parser])
    parser_build.set_defaults(func=handle_build)

    # 开始解析命令
    args = parser.parse_args()

    if args.version:
        print("mbuild %s" % CURRENT_VERSION)
        sys.exit(0)
    elif args.help or len(sys.argv) < 2:
        parser.print_help()
        sys.exit(0)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
