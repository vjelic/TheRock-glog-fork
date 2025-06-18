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


def write_to_JSON(input_dict: str):
    # Convert the string to a Python dictionary
  try:
      with open("job_status_dir/logs/job_status.json", "w") as file:
          json.dump(input_dict, file, indent=4)
      print("Dictionary successfully written to job_status.json")
  except IOError as e:
      print(f"Error writing to file: {e}")
  ##job_status_dir/logs/job_status.json

def main():
    parser = argparse.ArgumentParser(description="Write dict to file")
    parser.add_argument(
        "--input_dict", type=str, required=True, help="input dict to be converted to JSON"
    )
    args = parser.parse_args()

    covert_to_JSON(args.input_dict)
    


if __name__ == "__main__":
    main()
