#!/usr/bin/env python

import argparse
import configparser
import lib_python.project_builder as project_builder
import sys
import os
import time
import platform
from pathlib import Path, PurePosixPath

ROCK_BUILDER_VERSION = "2025-05-27_01"

def is_directory_in_path_env_variable(env_variable, directory):
  """
  Checks if a directory is in the env_variable environment variable.

  Args:
    env_variable: Environment variable used to check the path
    directory: The path searched from the environment variable

  Returns:
    True if the directory is in PATH, False otherwise.
  """
  path_env = os.environ.get(env_variable, '')
  path_directories = path_env.split(os.pathsep)
  return directory in path_directories

def do_therock(prj_builder):
    ret = False
    if (prj_builder is not None):
        # setup first the project specific environment variables
        prj_builder.printout("start")
        prj_builder.do_env_setup()
        #print("do_env_setup done")

        # then do all possible commands requested for the project
        # multiple steps possible, so do not use else's here
        if (args.init):
            prj_builder.printout("init")
            prj_builder.init()
        if (args.clean):
            prj_builder.printout("clean")
            prj_builder.clean()
        if (args.checkout):
            prj_builder.printout("checkout")
            prj_builder.checkout()
            # enable hipify always when doing checkout even if it is not requested explicitly as it's own command
            args.hipify = True
        if (args.hipify):
            prj_builder.printout("hipify")
            prj_builder.hipify()
        if (args.pre_config):
            prj_builder.printout("pre_config")
            prj_builder.pre_config()
        if (args.config):
            prj_builder.printout("config")
            prj_builder.config()
        if (args.post_config):
            prj_builder.printout("post_config")
            prj_builder.post_config()
        if (args.build):
            prj_builder.printout("build")
            prj_builder.build()
        if (args.install):
            prj_builder.printout("install")
            prj_builder.install()
        # in the end restore original environment variables
        # so that they do not cause problem for next possible project handled
        prj_builder.undo_env_setup()
        prj_builder.printout("done")
        ret = True
    return ret;

is_posix = not any(platform.win32_ver())

if is_posix:
    ENV_VARIABLE_NAME__LIB="LD_LIBRARY_PATH"
else:
    ENV_VARIABLE_NAME__LIB="LIBPATH"

#os.environ["ROCK_BUILDER_HOME_DIR"] = os.getcwd()
current_file_path = os.path.abspath(__file__)
rock_builder_home_dir = os.path.dirname(current_file_path)
os.environ["ROCK_BUILDER_HOME_DIR"] = rock_builder_home_dir
os.environ["ROCK_BUILDER_SRC_DIR"] = os.environ["ROCK_BUILDER_HOME_DIR"] + "/src_projects"
os.environ["ROCK_BUILDER_BUILD_DIR"] = os.environ["ROCK_BUILDER_HOME_DIR"] + "/builddir"

if "ROCM_HOME" not in os.environ:
    rocm_home_root_path = Path(rock_builder_home_dir) / "../../build/dist/rocm"
    rocm_home_root_path = rocm_home_root_path.resolve()
    print("p: " + rocm_home_root_path.as_posix())
    #print("ROCM_HOME: " + rocm_home_root_path)
    if rocm_home_root_path.exists():
        os.environ["ROCM_HOME"] = rocm_home_root_path.as_posix()
        rocm_home_bin_path = rocm_home_root_path / "bin"
        rocm_home_lib_path = rocm_home_root_path / "lib"
        rocm_home_bin_path = rocm_home_bin_path.resolve()
        rocm_home_lib_path = rocm_home_lib_path.resolve()
        rocm_home_llvm_path = rocm_home_root_path / "lib" / "llvm" / "bin"
        rocm_home_llvm_path = rocm_home_llvm_path.resolve()
        if rocm_home_bin_path.exists():
            if rocm_home_lib_path.exists():
                if not is_directory_in_path_env_variable("PATH", rocm_home_bin_path.as_posix()):
                    #print("Adding " + rocm_home_bin_path.as_posix() + " to PATH")
                    os.environ["PATH"] = rocm_home_bin_path.as_posix() + os.pathsep + os.environ.get("PATH", "")
                if not is_directory_in_path_env_variable("PATH", rocm_home_llvm_path.as_posix()):
                    #print("Adding " + rocm_home_bin_path.as_posix() + " to PATH")
                    os.environ["PATH"] = rocm_home_llvm_path.as_posix() + os.pathsep + os.environ.get("PATH", "")
                if not is_directory_in_path_env_variable(ENV_VARIABLE_NAME__LIB, rocm_home_lib_path.as_posix()):
                    #print("Adding " + rocm_home_lib_path.as_posix() + " to " + ENV_VARIABLE_NAME__LIB)
                    os.environ[ENV_VARIABLE_NAME__LIB] = rocm_home_lib_path.as_posix() + os.pathsep + os.environ.get(ENV_VARIABLE_NAME__LIB, "")
            else:
                print("Error, could not find directory " + rocm_home_lib_path.as_posix())
        else:
            print("Error, could not find directory " + rocm_home_bin_path.as_posix())
    else:
        print("Error, ROCM_HOME was not defined and ROCM build could not be found from the expected location: " + rocm_home_root_path.as_posix())
        sys.exit(1)

python_home_dir = os.path.dirname(sys.executable)
if "VIRTUAL_ENV" in os.environ:
    os.environ["ROCK_PYTHON_PATH"] = python_home_dir
else:
    if "ROCK_PYTHON_PATH" in os.environ:
        if not os.path.abspath(python_home_dir) == os.path.abspath(os.environ["ROCK_PYTHON_PATH"]):
            print("Error, virtual python environment is not active and")
            print("PYTHON location is different than ROCK_PYTHON_PATH")
            print("    PYTHON location: " + python_home_dir)
            print("    ROCK_PYTHON_PATH: " + os.environ["ROCK_PYTHON_PATH"])
            print("If you want use this python location instead of using a virtual python env, define ROCK_PYTHON_PATH:")
            if is_posix:
                print("    export ROCK_PYTHON_PATH=" + python_home_dir)
            else:
                print("    set ROCK_PYTHON_PATH=" + python_home_dir)
            print("Alternatively activate the virtual python environment")
            sys.exit(1)
        else:
            print("Using python from location: " + python_home_dir)
    else:
        print("Error, virtual python environment is not active and ROCK_PYTHON_PATH is not defined")
        print("    PYTHON location: " + python_home_dir)
        print("If you want use this python location instead of using a virtual python env, define ROCK_PYTHON_PATH:")
        if is_posix:
            print("    export ROCK_PYTHON_PATH=" + python_home_dir)
        else:
            print("    set ROCK_PYTHON_PATH=" + python_home_dir)
        print("Alternatively activate the virtual python environment")
        sys.exit(1)

print("RockBuilder " + ROCK_BUILDER_VERSION)
print("")
print("Build environment:")
print("-----------------------------")
print("ROCM_HOME: " + os.environ["ROCM_HOME"])
print("ROCK_PYTHON_PATH: " + os.environ["ROCK_PYTHON_PATH"])
print("ROCK_BUILDER_HOME_DIR: " + os.environ["ROCK_BUILDER_HOME_DIR"])
print("ROCK_BUILDER_SRC_DIR: " + os.environ["ROCK_BUILDER_SRC_DIR"])
print("ROCK_BUILDER_BUILD_DIR: " + os.environ["ROCK_BUILDER_BUILD_DIR"])
print("PATH: " + os.environ["PATH"])
print(ENV_VARIABLE_NAME__LIB + ": " + os.environ[ENV_VARIABLE_NAME__LIB])
print("-----------------------------")
time.sleep(1)

# Create an ArgumentParser object
parser = argparse.ArgumentParser(description='ROCK Project Builders')

# Add arguments
parser.add_argument('--project', type=str, help='select target for the action. Can be either one project or all projects in core_apps.pcfg.', default='all')
parser.add_argument('--init',  action='store_true', help='init build environment by installing dependencies', default=False)
parser.add_argument('--clean',  action='store_true', help='clean build files', default=False)
parser.add_argument('--checkout',  action='store_true', help='checkout source code for the project', default=False)
parser.add_argument('--hipify',  action='store_true', help='hipify command for project', default=False)
parser.add_argument('--pre_config',  action='store_true', help='pre-config command for project', default=False)
parser.add_argument('--config',  action='store_true', help='config command for project', default=False)
parser.add_argument('--post_config',  action='store_true', help='post-config command for project', default=False)
parser.add_argument('--build',  action='store_true', help='build project', default=False)
parser.add_argument('--install',  action='store_true', help='install build project', default=False)

# Parse the arguments
args = parser.parse_args()

if ("--checkout" in sys.argv) or ("--clean" in sys.argv) or ("--init" in sys.argv) or ("--hipify" in sys.argv) or\
   ("--pre_config" in sys.argv) or ("--config" in sys.argv) or ("--post_config" in sys.argv) or\
   ("--build" in sys.argv) or ("--install" in sys.argv):
    print("checkout/init/clean/hipify/pre_config/config/post_config/build or install argument specified")
else:
    #print("Action not specified.(checkout/init/clean/hipify/pre_config/config/post_config/build or install)")
    #print("Using default values")
    args.checkout=True
    args.init=True
    args.hipify=True
    args.pre_config=True
    args.config=True
    args.post_config=True
    args.build=True
    args.install=True

# Access the arguments
print("Actions Enabled:")
print('    checkout: ', args.checkout)
print('    init:    ', args.init)
print('    clean:    ', args.clean)
print('    hipify:    ', args.hipify)
print('    pre_config:', args.pre_config)
print('    config:', args.config)
print('    post_config:', args.post_config)
print('    build:    ', args.build)
print('    install:  ', args.install)
print('Projects:', args.project)

project_manager = project_builder.RockExternalProjectListManager(rock_builder_home_dir)
# allow_no_value param says that no value keys are ok
sections = project_manager.sections()
#print(sections)
project_list = project_manager.get_external_project_list()
#print(project_list)

for ii, prj_item in enumerate(project_list):
    print(f"    Project [{ii}]: {prj_item}")

# let user to see env variables for a while before build start
time.sleep(1)

if (args.project == "all"):
    for ii, prj_item in enumerate(project_list):
        print(f"[{ii}]: {prj_item}")
        prj_builder = project_manager.get_rock_project_builder(project_list[ii])
        if (prj_builder is None):
            print("Failed get project builder")
            sys.exit(1)
        else:
            do_therock(prj_builder)
else:
    prj_builder = project_manager.get_rock_project_builder(args.project)
    if (prj_builder is None):
        print("Failed get project builder")
        sys.exit(1)
    else:
        do_therock(prj_builder)
