#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
 Authors:
   yifengyou <842056007@qq.com>
"""

import argparse
import datetime
import glob
import json
import logging
import os
import os.path
import re
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler

import requests
import select

CURRENT_VERSION = "0.1.0"
logger = None
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
msg_token = "4155d89f-0b1c-44a8-8411-4f40c1d95795"


def timer(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        elapsed = end - start
        logger.info(f"{func.__name__} took {elapsed} seconds")
        return result

    return wrapper


class Wecom():
    """
    企业微信群聊机器人，官方文档：https://developer.work.weixin.qq.com/document/path/91770
    """

    def __init__(self, key=None):
        if key is None:
            raise Exception(" wecom api key is None ")
        self._key = key

    def do_send(self, data):
        res = None
        headers = {'Content-Type': 'application/json'}
        url = f'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self._key}'
        r = requests.post(url=url, headers=headers, data=json.dumps(data))
        try:
            res = json.loads(r.text)
        except:
            pass
        if r.status_code == 200 and res and 'errcode' in res and 0 == res['errcode']:
            logger.info('* wecomBot send msg success')
        else:
            logger.info('* wecomBot send msg failed!')
            logger.info(r.text)

    def send_markdown(self, msg):
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": msg,
            },
        }
        self.do_send(data)


def init_logger(args):
    global logger, timestamp
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
                else:
                    print("UNKOWN:", line)
        if p.poll() is not None:
            break
    return p.returncode, stdout_output, stderr_output


def do_sendmsg(args, ret=0, stdout="", stderr="", extra=""):
    if not args.quiet:
        msg_sender = Wecom(key=msg_token)
        format_msg = f"# mbuild消息播报:\n" \
                     f"命令 : <font color=\"info\">{' '.join(sys.argv)}</font>\n" \
                     f"返回值 : {ret}\n" \
                     f"输出 : {stdout}\n" \
                     f"错误 : {stderr}\n" \
                     f"附加 : {extra}\n" \
                     f"开始时间 : {timestamp}\n" \
                     f"结束时间 : {datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}"
        msg_sender.send_markdown(msg=format_msg)


def handle_stat(args):
    pass


def rpmbuild_per_srpm(srpm):
    # 获取srpm名称 N-V-R
    ret, srpm_name, stderr = do_exe_cmd(["rpm", "-qp", "--queryformat", "%{NAME}", srpm], print_output=True)
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
    logger.info(f"mbuild dir : {mbuilddir}")
    rpmbuilddir = os.path.join(mbuilddir, "rpmbuild_" + timestamp)
    if not os.path.exists(mbuilddir):
        os.makedirs(rpmbuilddir, exist_ok=True)
    logger.info(f"rpmbuild dir : {rpmbuilddir}")

    ret, stdout, stderr = do_exe_cmd(
        ["rpm", "-ivh", "--define", f"_topdir {rpmbuilddir}", f"{srpm}"],
        print_output=True
    )
    if ret != 0:
        # logger.error(f" install srpm {srpm} to {rpmbuilddir} failed! [{ret}] {stderr}")
        errorlog = os.path.join(mbuilddir, "mbuild_srpminstall_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
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
    logger.info(f"using spec {spec}")

    # 导出rpm -qa记录
    ret, stdout, stderr = do_exe_cmd(["rpm", "-qa"], print_output=False)
    if ret != 0:
        # logger.error(f" query all rpm failed! [{ret}] {stderr}")
        errorlog = os.path.join(mbuilddir, "mbuild_rpmqa_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        return
    rpm_manifest = os.path.join(mbuilddir, "mbuild_rpm-manifest_" + timestamp)
    with open(rpm_manifest, 'w') as fd:
        fd.write(stdout)

    # 安裝依赖
    ret, stdout, stderr = do_exe_cmd(["yum", "builddep", "-y", spec], print_output=True)
    if ret != 0:
        # logger.error(f" yum builddep failed! [{ret}] {stderr}")
        errorlog = os.path.join(mbuilddir, "mbuild_builddep_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        return
    buildlog = os.path.join(mbuilddir, "mbuild_builddep.log_" + timestamp)
    with open(buildlog, 'w') as fd:
        fd.write(stdout)

    # rpmbuild编译
    ret, stdout, stderr = do_exe_cmd(
        ["rpmbuild", "--define", f"_topdir {rpmbuilddir}", "-ba", f"{spec}", "--nocheck"],
        print_output=True)
    if ret != 0:
        # logger.error(f" rpmbuild failed! [{ret}] {stderr}")
        errorlog = os.path.join(mbuilddir, "mbuild_build_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        return
    buildlog = os.path.join(mbuilddir, "mbuild_rpmbuild.log_" + timestamp)
    with open(buildlog, 'w') as fd:
        fd.write(stdout)


@timer
def handle_build(args):
    if not os.path.exists(args.workdir) or not os.path.isdir(args.workdir):
        print(f"{args.workdir} is not a valid directory")
        exit(1)

    workdir = os.path.abspath(args.workdir)
    init_logger(args)
    logger.info(f"workdir: {workdir}")

    if args.srpm and len(args.srpm) > 0:
        total = len(args.srpm)
        for index, srpm in enumerate(args.srpm):
            if not os.path.exists(srpm) or not os.path.isfile(srpm):
                logger.error(f"{srpm} is not a valid srpm file")
                exit(1)
            srpm_path = os.path.abspath(srpm)
            logger.info(f"[{index + 1}/{total}] build {srpm}")
            rpmbuild_per_srpm(srpm_path)
    else:
        srpms = glob.glob(f"{args.workdir}/*.src.rpm")
        if not srpms:
            logger.error(f"No src.rpm found in {args.workdir}")
            exit(1)
        total = len(srpms)
        for index, srpm in enumerate(srpms):
            srpm_path = os.path.abspath(srpm)
            logger.info(f"[{index + 1}/{total}] build {srpm}")
            rpmbuild_per_srpm(srpm_path)

    if not args.quiet:
        msg_sender = Wecom(key=msg_token)
        format_msg = f"# mbuild消息播报:\n" \
                     f"命令 : <font color=\"info\">{' '.join(sys.argv)}</font>\n" \
                     f"开始时间 : {timestamp}\n" \
                     f"结束时间 : {datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}"
        msg_sender.send_markdown(msg=format_msg)


@timer
def handle_localinstall(args):
    if not os.path.exists(args.workdir) or not os.path.isdir(args.workdir):
        print(f"{args.workdir} is not a valid directory")
        exit(1)

    workdir = os.path.abspath(args.workdir)
    init_logger(args)
    logger.info(f"workdir: {workdir}")

    if not args.srpm:
        logger.error(f" must specific target srpm")

    if not os.path.exists(args.srpm) or not os.path.isfile(args.srpm):
        logger.error(f"{args.srpm} is not a valid srpm file")
        exit(1)
    srpm_path = os.path.abspath(args.srpm)

    ret, stdout, stderr = do_exe_cmd(
        ["rpm", "-ivh", "--define", f"_topdir {workdir}", f"{srpm_path}"],
        print_output=True
    )
    if ret != 0:
        # logger.error(f" install srpm {srpm} to {rpmbuilddir} failed! [{ret}] {stderr}")
        errorlog = os.path.join(workdir, "mbuild_srpminstall_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        return
    else:
        logger.info(f"localinstall {srpm_path} success!")

    if not args.quiet:
        msg_sender = Wecom(key=msg_token)
        format_msg = f"# mbuild消息播报:\n" \
                     f"命令 : <font color=\"warning\">{' '.join(sys.argv)}</font>\n" \
                     f"开始时间 : {timestamp}\n" \
                     f"结束时间 : {datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}"
        msg_sender.send_markdown(msg=format_msg)


@timer
def handle_localbuild(args):
    """
    编译指定目录
    :param args:
    :return:
    """
    if not os.path.exists(args.workdir) or not os.path.isdir(args.workdir):
        print(f"{args.workdir} is not a valid directory")
        exit(1)

    workdir = os.path.abspath(args.workdir)
    init_logger(args)
    logger.info(f"workdir: {workdir}")

    # 检查工作目录是否为rpmbuild目录（包含SOURCES、SPECS）
    if not os.path.exists(os.path.join(workdir, "SOURCES")) or not os.path.exists(os.path.join(workdir, "SPECS")):
        logger.error(f"No SOURCES or SPECS dir found in {workdir}")
        return

    # 检查spec，获取SPEC绝对路径spec
    specs = glob.glob(f"{workdir}/SPECS/*.spec")
    if len(specs) == 0:
        logger.error(f"no specs found!")
        return
    elif len(specs) > 1:
        logger.error(f"found spec more than one [{len(specs)}]")
        return
    spec = os.path.abspath(specs[0])
    logger.info(f"using spec {spec}")

    # 导出rpm -qa记录
    ret, stdout, stderr = do_exe_cmd(["rpm", "-qa"], print_output=False)
    if ret != 0:
        # logger.error(f" query all rpm failed! [{ret}] {stderr}")
        errorlog = os.path.join(workdir, "mbuild_rpmqa_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        return
    rpm_manifest = os.path.join(workdir, "mbuild_rpm-manifest_" + timestamp)
    with open(rpm_manifest, 'w') as fd:
        fd.write(stdout)

    # 安裝依赖
    ret, stdout, stderr = do_exe_cmd(["yum", "builddep", "-y", spec], print_output=True)
    if ret != 0:
        # logger.error(f" yum builddep failed! [{ret}] {stderr}")
        errorlog = os.path.join(workdir, "mbuild_builddep_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        return
    buildlog = os.path.join(workdir, "mbuild_builddep.log_" + timestamp)
    with open(buildlog, 'w') as fd:
        fd.write(stdout)
        fd.write(stderr)

    # rpmbuild编译
    ret, stdout, stderr = do_exe_cmd(
        ["rpmbuild", "--define", f"_topdir {workdir}", "-ba", f"{spec}", "--nocheck"],
        print_output=True
    )
    if ret != 0:
        # logger.error(f" rpmbuild failed! [{ret}] {stderr}")
        errorlog = os.path.join(workdir, "mbuild_build_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        return
    buildlog = os.path.join(workdir, "mbuild_rpmbuild.log_" + timestamp)
    with open(buildlog, 'w') as fd:
        fd.write(stdout)
        fd.write(stderr)

    if not args.quiet:
        msg_sender = Wecom(key=msg_token)
        format_msg = f"# mbuild消息播报:\n" \
                     f"命令 : <font color=\"info\">{' '.join(sys.argv)}</font>\n" \
                     f"开始时间 : {timestamp}\n" \
                     f"结束时间 : {datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}"
        msg_sender.send_markdown(msg=format_msg)


def handle_clean(args):
    if not os.path.exists(args.workdir) or not os.path.isdir(args.workdir):
        print(f"{args.workdir} is not a valid directory")
        exit(1)

    workdir = os.path.abspath(args.workdir)
    print(f"workdir: {workdir}")

    # 检查spec
    logs = glob.glob(f"{workdir}/mbuild_*")
    if len(logs) == 0:
        print(f"no mbuild log found! bye~")
        return
    for l in logs:
        if os.path.isfile(l):
            os.remove(l)
            print(f"delete {l} done!")
    print(f"clean done")


def mockbuild_per_srpm(args, srpm):
    srpm_path = os.path.abspath(srpm)

    # 选择输出目录
    if not args.output:
        # 获取srpm名称 N-V-R
        ret, srpm_name, stderr = do_exe_cmd(
            ["rpm", "-qp", "--nosignature", "--nodigest", "--queryformat", "%{NAME}", srpm_path],
            print_output=False
        )
        if ret != 0:
            msg = f" query srpm file ret is not zero [{ret}] {stderr}"
            logger.error(msg)
            do_sendmsg(args, ret=-1, stderr=msg)
            return
        srpm_name = srpm_name.strip()
        logger.info(f"srpm name : [{srpm_name}]")

        # 创建构建目录
        topdir = os.path.dirname(srpm_path)
        output_dir = os.path.join(topdir, srpm_name)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        logger.info(f"output_dir dir : {output_dir}")
    else:
        try:
            os.makedirs(args.output, exist_ok=True)
        except Exception as e:
            msg = f"failed to create {args.output}"
            logger.error(msg)
            do_sendmsg(args, ret=-1, stderr=msg)
            exit(1)
        output_dir = args.output

    if not args.root:
        root = "rocky-8-x86_64"
    else:
        root = args.root

    # mock编译
    cmd = [
        "/usr/bin/mock",
        "--root", f"{root}",
        "--rebuild", f"{srpm_path}",
        "--resultdir", f"{output_dir}",
        "--verbose"
    ]
    logger.info(f"run cmd {' '.join(cmd)}")
    ret, stdout, stderr = do_exe_cmd(cmd, print_output=True, shell=False)
    if ret != 0:
        # logger.error(f" rpmbuild failed! [{ret}] {stderr}")
        errorlog = os.path.join(output_dir, "mbuild_mock_err.log_" + timestamp)
        with open(errorlog, 'w') as fd:
            fd.write(stdout)
            fd.write(stderr)
        do_sendmsg(args, ret=ret)
        return
    buildlog = os.path.join(output_dir, "mbuild_mock.log_" + timestamp)
    with open(buildlog, 'w') as fd:
        fd.write(stdout)
        fd.write(stderr)


@timer
def handle_mock(args):
    if not os.path.exists(args.workdir) or not os.path.isdir(args.workdir):
        print(f"{args.workdir} is not a valid directory")
        exit(1)

    workdir = os.path.abspath(args.workdir)
    init_logger(args)
    logger.info(f"workdir: {workdir}")

    if args.srpm:
        if not os.path.exists(args.srpm) or not os.path.isfile(args.srpm):
            logger.error(f"{args.srpm} is not a valid srpm file")
            exit(1)
        srpm_path = os.path.abspath(args.srpm)
        mockbuild_per_srpm(args, srpm_path)
    else:
        srpms = glob.glob(f"{args.workdir}/*.src.rpm")
        if not srpms:
            logger.error(f"No src.rpm found in {args.workdir}")
            exit(1)
        total = len(srpms)
        for index, srpm in enumerate(srpms):
            srpm_path = os.path.abspath(srpm)
            logger.info(f"[{index + 1}/{total}] build {srpm}")
            mockbuild_per_srpm(args, srpm_path)

    do_sendmsg(args)


def handle_check(args):
    if not os.path.exists(args.workdir) or not os.path.isdir(args.workdir):
        print(f"{args.workdir} is not a valid directory")
        exit(1)

    workdir = os.path.abspath(args.workdir)
    print(f"workdir: {workdir}")

    def find_rpm_files(dir_path):
        flag = False
        rpms = []
        for entry in os.scandir(dir_path):
            if entry.is_file() and entry.name.endswith(".rpm"):
                flag = True
                rpms.append(os.path.basename(entry.path))
            elif entry.is_dir():
                find_rpm_files(entry.path)
        if flag:
            print(f"[+] {os.path.abspath(dir_path)}")
            for r in rpms:
                print(f"\t[-] {r}")

    find_rpm_files(workdir)


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
    parent_parser.add_argument("-o", "--output", default=None, help="output dir path")
    parent_parser.add_argument("-w", "--workdir", default=".", help="setup workdir")
    parent_parser.add_argument('-d', '--debug', default=None, action="store_true", help="enable debug output")
    parent_parser.add_argument('-q', '--quiet', default=False, action="store_true", help="keep quiet, no msg send")

    # 添加子命令 stat
    parser_stat = subparsers.add_parser('stat', parents=[parent_parser])
    parser_stat.set_defaults(func=handle_stat)

    # 添加子命令 build
    parser_build = subparsers.add_parser('build', parents=[parent_parser])
    parser_build.add_argument('-s', '--srpm', nargs="+", default=None, help="build specific srpm")
    parser_build.set_defaults(func=handle_build)

    # 添加子命令 localinstall
    parser_localinstall = subparsers.add_parser('localinstall', parents=[parent_parser])
    parser_localinstall.set_defaults(func=handle_localinstall)

    # 添加子命令 localbuild
    parser_localbuild = subparsers.add_parser('localbuild', parents=[parent_parser])
    parser_localbuild.set_defaults(func=handle_localbuild)

    # 添加子命令 handle_mock
    parser_mock = subparsers.add_parser('mock', parents=[parent_parser])
    parser_mock.add_argument('-r', '--root', default=None, help="specific mock config")
    parser_mock.add_argument('-s', '--srpm', nargs="+", default=None, help="build specific srpm")
    parser_mock.set_defaults(func=handle_mock)

    # 添加子命令 clean
    parser_clean = subparsers.add_parser('clean', parents=[parent_parser])
    parser_clean.set_defaults(func=handle_clean)

    # 添加子命令 check
    parser_check = subparsers.add_parser('check', parents=[parent_parser])
    parser_check.set_defaults(func=handle_check)

    # 开始解析命令
    args = parser.parse_args()

    # 解析命令后解析配置文件，合并两者
    for filename in os.listdir('.'):
        if filename.endswith(".mbuild"):
            print("load config file %s" % filename)
            with open(filename, 'r', encoding='utf8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    match = re.match(r'(\w+)\s*=\s*([\w/.-]+)', line)
                    if match:
                        key = match.group(1)
                        value = match.group(2)
                        # 如果命令行没有定义key，则使用配置中的KV
                        if not hasattr(args, key):
                            setattr(args, key, value)
                        # 如果命令行未打开选项，但配置中打开，则使用配置中的KV
                        if getattr(args, key) is None:
                            setattr(args, key, value)

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
