#!/usr/bin/env python

import argparse
import configparser
import sys
import os
import time
import platform
import lib_python.project_builder as project_builder
import lib_python.rockbuilder_config as RockBuilderConfig
from pathlib import Path, PurePosixPath

ROCK_BUILDER_VERSION = "2025-06-25_01"


def get_rocm_builder_root_dir():
    current_file_path = os.path.abspath(__file__)
    ret = Path(os.path.dirname(current_file_path)).resolve()
    return ret


def printout_rock_builder_info():
    print("RockBuilder " + ROCK_BUILDER_VERSION)
    print("")
    print("ROCK_BUILDER_HOME_DIR: " + os.environ["ROCK_BUILDER_HOME_DIR"])
    print("ROCK_BUILDER_SRC_DIR: " + os.environ["ROCK_BUILDER_SRC_DIR"])
    print("ROCK_BUILDER_BUILD_DIR: " + os.environ["ROCK_BUILDER_BUILD_DIR"])


def printout_build_env_info():
    printout_rock_builder_info()
    print("Build environment:")
    print("-----------------------------")
    print("ROCM_HOME: " + os.environ["ROCM_HOME"])
    print("ROCK_PYTHON_PATH: " + os.environ["ROCK_PYTHON_PATH"])
    print("PATH: " + os.environ["PATH"])
    print("-----------------------------")
    time.sleep(1)


def get_build_arguments(rock_builder_home_dir):
    # Create an ArgumentParser object
    parser = argparse.ArgumentParser(description="ROCK Project Builders")

    # Add arguments
    parser.add_argument(
        "--project",
        type=str,
        help="select target for the action. Can be either one project or all projects in core_apps.pcfg.",
        default="all",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="init build environment by installing dependencies",
        default=False,
    )
    parser.add_argument(
        "--clean", action="store_true", help="clean build files", default=False
    )
    parser.add_argument(
        "--checkout",
        action="store_true",
        help="checkout source code for the project",
        default=False,
    )
    parser.add_argument(
        "--hipify",
        action="store_true",
        help="hipify command for project",
        default=False,
    )
    parser.add_argument(
        "--pre_config",
        action="store_true",
        help="pre-config command for project",
        default=False,
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="config command for project",
        default=False,
    )
    parser.add_argument(
        "--post_config",
        action="store_true",
        help="post-config command for project",
        default=False,
    )
    parser.add_argument(
        "--build", action="store_true", help="build project", default=False
    )
    parser.add_argument(
        "--install", action="store_true", help="install build project", default=False
    )
    parser.add_argument(
        "--post_install",
        action="store_true",
        help="post-install command for project",
        default=False,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to copy built wheels to",
        default=rock_builder_home_dir / "packages" / "wheels",
    )

    # Parse the arguments
    args = parser.parse_args()
    if (
        ("--checkout" in sys.argv)
        or ("--clean" in sys.argv)
        or ("--init" in sys.argv)
        or ("--hipify" in sys.argv)
        or ("--pre_config" in sys.argv)
        or ("--config" in sys.argv)
        or ("--post_config" in sys.argv)
        or ("--build" in sys.argv)
        or ("--install" in sys.argv)
        or ("--post_install" in sys.argv)
    ):
        print(
            "checkout/init/clean/hipify/pre_config/config/post_config/build/install/post_install argument specified"
        )
    else:
        # print("Action not specified.(checkout/init/clean/hipify/pre_config/config/post_config/build/install/post_install)")
        # print("Using default values")
        # enable everything except clean
        args.checkout = True
        args.init = True
        args.clean = False
        args.hipify = True
        args.pre_config = True
        args.config = True
        args.post_config = True
        args.build = True
        args.install = True
        args.post_install = True
    # force the hipify step always as a part of the checkout
    if args.checkout:
        args.hipify = True

    # add output dir to environment variables
    os.environ["ROCK_BUILDER_PACKAGE_OUTPUT_DIR"] = args.output_dir.as_posix()

    return args


def printout_build_arguments(args):
    # printout arguments enabled
    print("Actions Enabled:")
    print("    checkout: ", args.checkout)
    print("    init:    ", args.init)
    print("    clean:    ", args.clean)
    print("    hipify:    ", args.hipify)
    print("    pre_config:", args.pre_config)
    print("    config:", args.config)
    print("    post_config:", args.post_config)
    print("    build:    ", args.build)
    print("    install:  ", args.install)
    print("    post_install:  ", args.post_install)
    print("Projects:", args.project)


def verify_build_env__python(self):
    # check the python used. It needs to be by default an virtual env but
    # this can be overriden to real python version by setting up ENV variable
    # ROCK_PYTHON_PATH
    python_home_dir = os.path.dirname(sys.executable)
    if "VIRTUAL_ENV" in os.environ:
        os.environ["ROCK_PYTHON_PATH"] = python_home_dir
    else:
        if "ROCK_PYTHON_PATH" in os.environ:
            if not os.path.abspath(python_home_dir) == os.path.abspath(
                os.environ["ROCK_PYTHON_PATH"]
            ):
                print("Error, virtual python environment is not active and")
                print(
                    "PYTHON location is different than specified by the ROCK_PYTHON_PATH"
                )
                print("    PYTHON location: " + python_home_dir)
                print("    ROCK_PYTHON_PATH: " + os.environ["ROCK_PYTHON_PATH"])
                print(
                    "If you want use this python location instead of using a virtual python env, define ROCK_PYTHON_PATH:"
                )
                if is_posix:
                    print("    export ROCK_PYTHON_PATH=" + python_home_dir)
                else:
                    print("    set ROCK_PYTHON_PATH=" + python_home_dir)
                print("Alternatively activate the virtual python environment")
                sys.exit(1)
            else:
                print("Using python from location: " + python_home_dir)
        else:
            print(
                "Error, virtual python environment is not active and ROCK_PYTHON_PATH is not defined"
            )
            print("    PYTHON location: " + python_home_dir)
            print(
                "If you want use this python location instead of using a virtual python env, define ROCK_PYTHON_PATH:"
            )
            if is_posix:
                print("    export ROCK_PYTHON_PATH=" + python_home_dir)
            else:
                print("    set ROCK_PYTHON_PATH=" + python_home_dir)
            print("Alternatively activate the virtual python environment")
            sys.exit(1)


def verify_build_env(args, rock_builder_home_dir):
    # we may actually need to have the build environment
    # even during the checkout as we do the hipify during the checkout process
    """"
    if ((args.checkout == True) and\
        (args.init == False) and\
        (args.clean == False) and\
        (args.hipify == False) and\
        (args.pre_config == False) and\
        (args.config == False) and\
        (args.post_config == False) and\
        (args.build == False) and\
        (args.install == False) and\
        (args.post_install == False)):
        # allow code checkout even before TheRock build has been installed
        printout_rock_builder_info()
        return
    """

    # set the ENV_VARIABLE_NAME__LIB to be either LD_LIBRARY_PATH or LIBPATH depending
    # whether code is executed on Linux or Windows (it is later used to set env-variables)
    if is_posix:
        ENV_VARIABLE_NAME__LIB = "LD_LIBRARY_PATH"
    else:
        ENV_VARIABLE_NAME__LIB = "LIBPATH"

    # read and set up env based on to rockbuilder.ini file if it exist
    rcb_config = RockBuilderConfig.RockBuilderConfig(rock_builder_home_dir)
    res = rcb_config.read_cfg()
    if res:
        rcb_config.setup_build_env()

    # check that THEROCK_AMDGPU_TARGETS has been specified on Windows builds.
    # This is needdd because on locally build rocm sdk we can not automatically query
    # what are the build targets that are supported by rocm_sdk used.
    if not is_posix:
        if not "THEROCK_AMDGPU_TARGETS" in os.environ:
            print(
                "Error, THEROCK_AMDGPU_TARGETS must be set on Windows to select the target GPUs"
            )
            print("Target GPU must match with the GPU selected on TheRock core build")
            print("Example for building for AMD Strix Halo and RX 9070:")
            print("  set THEROCK_AMDGPU_TARGETS=gfx1151;gfx1201")
            sys.exit(1)

    # check rocm
    if "ROCM_HOME" in os.environ:
        rocm_home_root_path = Path(os.environ["ROCM_HOME"])
        rocm_home_root_path = rocm_home_root_path.resolve()
    else:
        rocm_home_root_path = rock_builder_home_dir / "../../build/dist/rocm"
        rocm_home_root_path = rocm_home_root_path.resolve()
        print("using locally build rocm sdk from TheRock:")
        print("    " + rocm_home_root_path.as_posix())
    if rocm_home_root_path.exists():
        # set ROCM_HOME if not yet set
        if not "ROCM_HOME" in os.environ:
            # print("ROCM_HOME: " + rocm_home_root_path.as_posix())
            os.environ["ROCM_HOME"] = rocm_home_root_path.as_posix()

        rocm_home_bin_path = rocm_home_root_path / "bin"
        rocm_home_lib_path = rocm_home_root_path / "lib"
        rocm_home_bin_path = rocm_home_bin_path.resolve()
        rocm_home_lib_path = rocm_home_lib_path.resolve()
        rocm_home_llvm_path = rocm_home_root_path / "lib" / "llvm" / "bin"
        rocm_home_llvm_path = rocm_home_llvm_path.resolve()
        if rocm_home_bin_path.exists():
            if rocm_home_lib_path.exists():
                if not is_directory_in_env_variable_path(
                    "PATH", rocm_home_bin_path.as_posix()
                ):
                    # print("Adding " + rocm_home_bin_path.as_posix() + " to PATH")
                    os.environ["PATH"] = (
                        rocm_home_bin_path.as_posix()
                        + os.pathsep
                        + os.environ.get("PATH", "")
                    )
                if not is_directory_in_env_variable_path(
                    "PATH", rocm_home_llvm_path.as_posix()
                ):
                    # print("Adding " + rocm_home_llvm_path.as_posix() + " to PATH")
                    os.environ["PATH"] = (
                        rocm_home_llvm_path.as_posix()
                        + os.pathsep
                        + os.environ.get("PATH", "")
                    )
                if not is_directory_in_env_variable_path(
                    ENV_VARIABLE_NAME__LIB, rocm_home_lib_path.as_posix()
                ):
                    # print("Adding " + rocm_home_lib_path.as_posix() + " to " + ENV_VARIABLE_NAME__LIB)
                    os.environ[ENV_VARIABLE_NAME__LIB] = (
                        rocm_home_lib_path.as_posix()
                        + os.pathsep
                        + os.environ.get(ENV_VARIABLE_NAME__LIB, "")
                    )
                # find bitcode and put it to path
                for folder_path in Path(rocm_home_root_path).glob("**/bitcode"):
                    folder_path = folder_path.resolve()
                    os.environ["ROCK_BUILDER_BITCODE_HOME"] = folder_path.as_posix()
                    break
                # find clang
                if is_posix:
                    clang_exec_name = "clang"
                else:
                    clang_exec_name = "clang.exe"
                for folder_path in Path(rocm_home_root_path).glob(
                    "**/" + clang_exec_name
                ):
                    clang_home = folder_path.parent
                    # make sure that we found bin/clang and not clang folder
                    if clang_home.name.lower() == "bin":
                        clang_home = clang_home.parent
                        if clang_home.is_dir():
                            clang_home = clang_home.resolve()
                            os.environ[
                                "ROCK_BUILDER_CLANG_HOME"
                            ] = clang_home.as_posix()
                            break
            else:
                print(
                    "Error, could not find directory ROCM_SDK/lib: "
                    + rocm_home_lib_path.as_posix()
                )
                sys.exit(1)
        else:
            print(
                "Error, could not find directory ROCM_SDK/bin: "
                + rocm_home_bin_path.as_posix()
            )
            sys.exit(1)
    else:
        print("Error, ROCM_HOME is not defined and")
        print("ROCM build is not detected in the RockBuilder build environment:")
        print("    " + rocm_home_root_path.as_posix())
        print("")
        sys.exit(1)

    printout_build_env_info()


# check whether specified directory is included in the specified environment variable
def is_directory_in_env_variable_path(env_variable, directory):
    """
    Checks if a directory is in the env_variable specified as a parameter.
    (path, libpath, etc)

    Args:
      env_variable: Environment variable used to check the path
      directory: The path searched from the environment variable

    Returns:
      True if the directory is in PATH, False otherwise.
    """
    path_env = os.environ.get(env_variable, "")
    path_directories = path_env.split(os.pathsep)
    return directory in path_directories


# do all build steps for given process
def do_therock(prj_builder):
    ret = False
    if prj_builder is not None:
        if prj_builder.check_skip_on_os() == False:
            # setup first the project specific environment variables
            prj_builder.printout("start")
            prj_builder.do_env_setup()
            # print("do_env_setup done")

            # then do all possible commands requested for the project
            # multiple steps possible, so do not use else's here
            if args.clean:
                prj_builder.printout("clean")
                prj_builder.clean()
            if args.checkout:
                prj_builder.printout("checkout")
                prj_builder.checkout()
                # enable hipify always when doing the code checkout
                # even if it is not requested explicitly to be it's own command
                args.hipify = True
            if args.init:
                prj_builder.printout("init")
                prj_builder.init()
            if args.hipify:
                prj_builder.printout("hipify")
                prj_builder.hipify()
            if args.pre_config:
                prj_builder.printout("pre_config")
                prj_builder.pre_config()
            if args.config:
                prj_builder.printout("config")
                prj_builder.config()
            if args.post_config:
                prj_builder.printout("post_config")
                prj_builder.post_config()
            if args.build:
                prj_builder.printout("build")
                prj_builder.build()
            if args.install:
                prj_builder.printout("install")
                prj_builder.install()
            if args.post_install:
                prj_builder.printout("post_install")
                prj_builder.post_install()
            # in the end restore original environment variables
            # so that they do not cause problem for next possible project handled
            prj_builder.undo_env_setup()
            prj_builder.printout("done")
            ret = True
        else:
            print("skip_windows or skip_linux enabled for project")
            prj_builder.printout("skip")
            ret = True
    return ret


is_posix = not any(platform.win32_ver())

rock_builder_home_dir = get_rocm_builder_root_dir()
os.environ["ROCK_BUILDER_HOME_DIR"] = rock_builder_home_dir.as_posix()
os.environ["ROCK_BUILDER_SRC_DIR"] = (rock_builder_home_dir / "src_projects").as_posix()
os.environ["ROCK_BUILDER_BUILD_DIR"] = (rock_builder_home_dir / "builddir").as_posix()

args = get_build_arguments(rock_builder_home_dir)
printout_build_arguments(args)
verify_build_env__python(args)
verify_build_env(args, rock_builder_home_dir)

project_manager = project_builder.RockExternalProjectListManager(
    rock_builder_home_dir, args.output_dir
)
# allow_no_value param says that no value keys are ok
sections = project_manager.sections()
# print(sections)
project_list = project_manager.get_external_project_list()
# print(project_list)

for ii, prj_item in enumerate(project_list):
    print(f"    Project [{ii}]: {prj_item}")

# let user to see env variables for a while before build start
time.sleep(1)

if args.project == "all":
    for ii, prj_item in enumerate(project_list):
        print(f"[{ii}]: {prj_item}")
        prj_builder = project_manager.get_rock_project_builder(project_list[ii])
        if prj_builder is None:
            print("Error, failed to init project builder")
            sys.exit(1)
        else:
            do_therock(prj_builder)
else:
    prj_builder = project_manager.get_rock_project_builder(args.project)
    if prj_builder is None:
        print("Error, failed to init project builder")
        sys.exit(1)
    else:
        do_therock(prj_builder)
