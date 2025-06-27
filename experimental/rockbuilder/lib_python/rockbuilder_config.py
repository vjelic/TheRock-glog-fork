import ast
import configparser
import os
import platform
import sys
import ast
import subprocess
from lib_python.repo_management import RockProjectRepo
from pathlib import Path, PurePosixPath


class RockBuilderConfig(configparser.ConfigParser):
    def __init__(self, rcb_root_dir):
        super(RockBuilderConfig, self).__init__(allow_no_value=True)
        self.rcb_root_dir = rcb_root_dir
        self.fname_cfg = rcb_root_dir / "rockbuilder.ini"
        self.gpu_list = None
        self.rock_sdk_whl_url = None
        self.rock_sdk_new_build_dir = None
        self.rock_sdk_old_build_dir = None

    def _replace_env_variables(self, cmd_str):
        ret = os.path.expandvars(cmd_str)
        return ret

    def _exec_subprocess_cmd(self, exec_cmd, exec_dir):
        ret = True
        return ret
        if exec_cmd is not None:
            exec_dir = self._replace_env_variables(exec_dir)
            print("exec_cmd: " + exec_cmd)
            # capture_output=True --> can print output after process exist, not possible to see the output during the build time
            # capture_output=False --> can print output only during build time
            # result = subprocess.run(exec_cmd, shell=True, capture_output=True, text=True)
            result = subprocess.run(
                exec_cmd, cwd=exec_dir, shell=True, capture_output=False, text=True
            )
            if result.returncode == 0:
                if result.stdout:
                    print(result.stdout)
            else:
                ret = False
                print(result.stdout)
                print(f"Error: {result.stderr}")
        return ret

    # if the rockbuilder.ini file is present, set some build options based on to it's values
    def read_cfg(self):
        ret = False
        if self.fname_cfg.exists():
            # get last modifued date
            f_stats = self.fname_cfg.stat()
            self.file_last_mod_time_sec = f_stats.st_mtime
            # read the config values
            self.read(self.fname_cfg)
            ret = True
        return ret

    def get_as_list(self, section_name_rocm_sdk, key_name_rocm_sdk_whl_url):
        # we get values as a string reporesenting a list of strings
        ret = self.get(section_name_rocm_sdk, key_name_rocm_sdk_whl_url)
        # convert it to real python list object
        ret = ast.literal_eval(ret)
        # ret = ret.split(", ")
        return ret

    def setup_build_env(self):
        section_name_rocm_sdk = "rocm_sdk"
        section_name_build_targets = "build_targets"
        key_name_rocm_sdk_whl_url = "rocm_sdk_whl_server_url"
        key_name_rocm_sdk_new_build = "rocm_sdk_build"
        key_name_rocm_sdk_old_build = "rocm_sdk_dir"
        key_name_gpus = "gpus"
        rocm_sdk_uninstall_cmd = (
            sys.executable
            + " -m pip cache remove rocm_sdk --cache-dir "
            + self.rcb_root_dir.as_posix()
        )
        install_deps_cmd = (
            sys.executable
            + " -m pip install setuptools --cache-dir "
            + self.rcb_root_dir.as_posix()
        )
        rocm_sdk_install_cmd_base = (
            sys.executable
            + " -m pip install rocm_sdk --force-reinstall --cache-dir "
            + self.rcb_root_dir.as_posix()
        )

        # check the selected target GPUs
        if self.has_option(section_name_build_targets, key_name_gpus):
            self.gpu_list = self.get_as_list(section_name_build_targets, key_name_gpus)
        # check option to use rocm sdk from the wheel
        if self.has_option(section_name_rocm_sdk, key_name_rocm_sdk_whl_url):
            self.rock_sdk_whl_url = self.get_as_list(
                section_name_rocm_sdk, key_name_rocm_sdk_whl_url
            )
            # there should be only one item in the list
            if len(self.rock_sdk_whl_url) == 1:
                self.rock_sdk_whl_url = self.rock_sdk_whl_url[0]
            else:
                print(
                    "rockbuilder.ini file error, wheel server url must be an an string array with with one server specified"
                )
                sys.exit(1)

        # check whether new rocm sdk build should be done
        if self.has_option(section_name_rocm_sdk, key_name_rocm_sdk_new_build):
            self.rock_sdk_new_build_dir = self.get_as_list(
                section_name_rocm_sdk, key_name_rocm_sdk_new_build
            )
            # there should be only one item in this list
            if len(self.rock_sdk_new_build_dir) == 1:
                self.rock_sdk_new_build_dir = self.rock_sdk_new_build_dir[0]
            else:
                print(
                    "rockbuilder.ini file error, wheel server url must be an an string array with with directory"
                )
                sys.exit(1)

        # check whether old rocm sdk build should be done
        if self.has_option(section_name_rocm_sdk, key_name_rocm_sdk_old_build):
            self.rock_sdk_old_build_dir = self.get_as_list(
                section_name_rocm_sdk, key_name_rocm_sdk_old_build
            )
            # there should be only one item in this list
            if len(self.rock_sdk_old_build_dir) == 1:
                self.rock_sdk_old_build_dir = self.rock_sdk_old_build_dir[0]
            else:
                print(
                    "rockbuilder.ini file error, wheel server url must be an an string array with with directory"
                )
                sys.exit(1)

        # set target GPUs to environment variable
        if self.gpu_list:
            for ii, gpu_target in enumerate(self.gpu_list):
                if ii == 0:
                    gpus = self.gpu_list[0]
                else:
                    gpus = gpus + ";" + self.gpu_list[ii]
            os.environ["THEROCK_AMDGPU_TARGETS"] = gpus

        # rocm sdk from the pip wheel option
        if self.rock_sdk_whl_url and self.gpu_list:
            # config file specifies that rocm_sdk used comes from the pip wheel
            # install first the pip wheel
            # print("rocm_sdk_uninstall_cmd: " + rocm_sdk_uninstall_cmd)
            self._exec_subprocess_cmd(install_deps_cmd, self.rcb_root_dir.as_posix())
            self._exec_subprocess_cmd(
                rocm_sdk_uninstall_cmd, self.rcb_root_dir.as_posix()
            )
            # for now only 1 wheel can actually be installed, so rockbuilder_cfg.py selection tool
            # will allow user to select only one gpu target when this option is defined
            for gpu_target in self.gpu_list:
                full_rock_sdk_whl_url = self.rock_sdk_whl_url + gpu_target
                full_rocm_sdk_install_cmd = (
                    rocm_sdk_install_cmd_base + " --index-url " + full_rock_sdk_whl_url
                )
                # print("full_rocm_sdk_install_cmd: " + full_rocm_sdk_install_cmd)
                self._exec_subprocess_cmd(
                    full_rocm_sdk_install_cmd, self.rcb_root_dir.as_posix()
                )
            # set ROCM_HOME to point to the python venv which contains rocm_sdk
            os.environ["ROCM_HOME"] = sys.prefix

        # rocm sdk from the existing directory specified in the rockbuilder.init
        if self.rock_sdk_old_build_dir and self.gpu_list:
            os.environ["ROCM_HOME"] = self.rock_sdk_old_build_dir

        # rocm sdk build for the new directory specified in the rockbuilder.init
        # if self.rock_sdk_old_build_dir and self.gpu_list:
        # A) Either do everything in python code
        # 1) create/init the rocm_sdk/.venv
        # 2) exec get_sources()
        # 3) cmake configure
        # 4) cmake --build build
        #    os.environ["ROCM_HOME"] = self.rock_sdk_old_build_dir
        # B) or generate setup_env and build_rocm_sdk scripts for linux and windows
