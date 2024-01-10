#!/usr/bin/env python3

import datetime
import os
import re
import sys

# To download log files:
# > gh api repos/{repo_name}/actions/runs/{run_id}/logs > logs.zip
# > mkdir -p logs/{repo_name}/{run_id}
# > unzip logs.zip -d logs/{repo_name}/{run_id}

def logs_dir_path(repo_name, run_id):
    return f"logs/{repo_name}/{run_id}"

def get_log_file_names(logs_dir):
    log_file_regex = "\d+_run \(.*\.txt"
    log_files = []

    for filename in os.listdir(logs_dir):
        if re.match(log_file_regex, filename):
            log_files.append(f"{logs_dir}/{filename}")
    
    return log_files

def extract_timestamp(s):
    return datetime.datetime.fromisoformat(s[:26])

def get_timing_info(log_file):
    num_repos = 0
    setup_time_s = 0
    repo_time_s = 0
    download_time_s = 0
    query_time_s = 0

    starting_job = None
    starting_repo = None
    ending_repo = None
    job_ended = None

    eval_regex = "\[1/1 eval ([\d\.]+)s\] Evaluation done; writing results to.*"

    with open(log_file) as f:
        lines = f.readlines()

        for line in lines:
            l = line[29:]
            if l == "##[debug]Starting: Set up job\n":
                starting_job = extract_timestamp(line)

            elif l.startswith("Getting database for"):
                t = extract_timestamp(line)

                if starting_job is not None:
                    setup_time_s += (t - starting_job).total_seconds()
                    starting_job = None

                if starting_repo is not None:
                    raise Exception("Unable to find end of repo")

                starting_repo = t
            
            elif l == "Running query\n":
                if starting_repo is None:
                    raise Exception("Unable to find start of repo")
                
                download_time_s += (extract_timestamp(line) - starting_repo).total_seconds()
            
            elif re.match(eval_regex, l):
                query_time_s += float(re.match(eval_regex, l).group(1))
            
            elif l.startswith("[command]/opt/hostedtoolcache/CodeQL/2.15.5/x64/codeql/codeql bqrs interpret"):
                if starting_repo is None:
                    raise Exception("Unable to find start of repo")
                
                num_repos += 1
                t = extract_timestamp(line)
                repo_time_s += (t - starting_repo).total_seconds()
                starting_repo = None
                ending_repo = t

            elif l == "##[debug]Finishing: Complete job\n":
                job_ended = extract_timestamp(line)

                if ending_repo is None:
                    raise Exception("Unable to find end of repo")
                setup_time_s += (job_ended - ending_repo).total_seconds()

    
    if job_ended is None:
        raise Exception("Unable to find end of job")

    return num_repos, setup_time_s, repo_time_s, download_time_s, query_time_s

def main():
    if len(sys.argv) != 3:
        raise Exception("Expected args: repo_name run_id")

    repo_name = sys.argv[1]
    run_id = sys.argv[2]

    logs_dir = logs_dir_path(repo_name, run_id)
    if not os.path.isdir(logs_dir):
        raise Exception(f"Unable to find logs directory for {repo_name} {run_id}")

    log_files = get_log_file_names(logs_dir)

    num_repos = 0
    setup_time_s = 0
    repo_time_s = 0
    download_time_s = 0
    query_time_s = 0
    for log_file in log_files:
        n, s, r, d, q = get_timing_info(log_file)
        num_repos += n
        setup_time_s += s
        repo_time_s += r
        download_time_s += d
        query_time_s += q
    
    print(f"Number of repos: {num_repos}")
    print(f"Setup time: {setup_time_s}s, {setup_time_s / num_repos}s per repo")
    print(f"Repo time: {repo_time_s}s, {repo_time_s / num_repos}s per repo")
    print(f"    Download time: {download_time_s}s, {download_time_s / num_repos}s per repo")
    print(f"    Query time: {query_time_s}s, {query_time_s / num_repos}s per repo")

if __name__ == "__main__":
    main()
