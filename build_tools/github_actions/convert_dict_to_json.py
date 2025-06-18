#!/usr/bin/env python3
"""
convert_dict_to_json.py

Uploads convert dict from GITHUB_OUTPUT to JSON before uploading to S3 bucket using the AWS CLI.
"""

import argparse
import sys
import shutil
import json
import subprocess


def covert_to_JSON(input_string: str):
  
    # Convert the string to a Python dictionary
    python_object = json.loads(input_string)
    return {python_object}    

def main():
    parser = argparse.ArgumentParser(description="Convert dict to json")
    parser.add_argument(
        "--input_string", type=str, required=True, help="input string to be converted to JSON"
    )
    args = parser.parse_args()

    output_json = covert_to_JSON(args.input_string)

    with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
        print(f'my_output_variable={output_json}', file=fh)


if __name__ == "__main__":
    main()
