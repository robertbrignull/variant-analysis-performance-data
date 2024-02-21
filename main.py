#!/usr/bin/env python3

import datetime
import os
import re
import sys
import json

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

known_codeql_commands = [
    "database unbundle",
    "database run-queries",
    "database interpret-results",
    "bqrs info",
    "resolve queries",
    "resolve metadata",
    "resolve database"
]

def extract_codeql_command(l):
    for c in known_codeql_commands:
        if f"codeql/codeql {c}" in l or f"Running using CodeQL CLI: {c}" in l:
            return c
    raise Exception(f"Unable to extract codeql command from {l}")

def get_timing_info(log_file):
    num_repos = 0
    setup_time_s = 0
    repo_time_s = 0
    download_time_s = 0
    codeql_command_times_s = {}
    for c in known_codeql_commands:
        codeql_command_times_s[c] = 0

    starting_job = None
    starting_repo = None
    current_repo = None
    starting_download = None
    starting_command = None
    current_command = None
    job_time = None
    repo_times = []

    with open(log_file) as f:
        lines = f.readlines()

        for line in lines:
            l = line[29:]
            if l == "##[debug]Starting: Set up job\n":
                starting_job = extract_timestamp(line)

            elif l.startswith("Getting database for "):
                t = extract_timestamp(line)

                if current_repo is not None and starting_repo is not None:
                    repo_time_s += (t - starting_repo).total_seconds()
                    repo_times.append((current_repo, (t - starting_repo).total_seconds()))
                current_repo = l[len("Getting database for "):].strip()
                starting_repo = t

                if setup_time_s == 0:
                    setup_time_s = (t - starting_job).total_seconds()

                if current_command is not None and starting_command is not None:
                    codeql_command_times_s[current_command] += (t - starting_command).total_seconds()
                    current_command = None
                    starting_command = None

                starting_download = t
                num_repos += 1
            
            elif l.startswith("[command]/opt/hostedtoolcache/CodeQL/") or l.startswith("##[debug]Running using CodeQL CLI:"):
                t = extract_timestamp(line)

                if starting_download is not None:
                    download_time_s += (t - starting_download).total_seconds()
                    starting_download = None
                
                if current_command is not None and starting_command is not None:
                    codeql_command_times_s[current_command] += (t - starting_command).total_seconds()
                    current_command = None
                    starting_command = None
            
                current_command = extract_codeql_command(l)
                starting_command = t

            elif l == "##[debug]Finishing: Run query\n":
                t = extract_timestamp(line)

                if current_command is not None and starting_command is not None:
                    codeql_command_times_s[current_command] += (t - starting_command).total_seconds()
                    current_command = None
                    starting_command = None

                repo_time_s += (t - starting_repo).total_seconds()
                repo_times.append((current_repo, (t - starting_repo).total_seconds()))
                job_time = (t - starting_job).total_seconds()
    
    if num_repos == 0:
        raise Exception(f"Unable to find any repos in {log_file}")
    if repo_time_s == 0:
        raise Exception(f"Unable to find any repo time in {log_file}")

    return num_repos, setup_time_s, repo_time_s, download_time_s, codeql_command_times_s, job_time, repo_times

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
    codeql_command_times_s = {}
    for c in known_codeql_commands:
        codeql_command_times_s[c] = 0
    repo_times = []
    job_time_s = 0
    job_times = []

    for log_file in log_files:
        n, s, r, d, cs, jt, rt = get_timing_info(log_file)
        num_repos += n
        setup_time_s += s
        repo_time_s += r
        download_time_s += d
        for c in known_codeql_commands:
            codeql_command_times_s[c] += cs[c]
        job_time_s += jt
        job_times.append(jt)
        repo_times += rt
            
    longest_command = max([len(c) for c in known_codeql_commands]) + len('CodeQL command: ') + 1
    
    print(f"Number of repos: {num_repos}")
    print(f"Total time: {str(round(job_time_s, 2)) + 's'}")
    print(f"Setup time: {(str(round(setup_time_s, 2)) + 's').ljust(12)}, {(str(round(setup_time_s / num_repos, 2)) + 's per repo').ljust(20)}")
    print(f"Repo time:  {(str(round(repo_time_s, 2)) + 's').ljust(12)}, {(str(round(repo_time_s / num_repos, 2)) + 's per repo').ljust(20)}")
    print(f"    {'Download time'.ljust(longest_command)}: {(str(round(download_time_s, 2)) + 's').ljust(12)}, {(str(round(download_time_s / num_repos, 2)) + 's per repo').ljust(20)}, {round(100.0 * download_time_s / repo_time_s, 2)}% of total repo time")
    for c in known_codeql_commands:
        print(f"    {('CodeQL command: ' + c).ljust(longest_command)}: {(str(round(codeql_command_times_s[c], 2)) + 's').ljust(12)}, {(str(round(codeql_command_times_s[c] / num_repos, 2)) + 's per repo').ljust(20)}, {round(100.0 * codeql_command_times_s[c] / repo_time_s, 2)}% of total repo time")

    # Stats of how long each repo took
    # print()
    # print("Breakdown per repo:")
    # repo_times.sort(key=lambda x: x[1])
    # for repo in repo_times:
    #     print(f"{repo[0].ljust(60)} \t {str(round(repo[1], 2))}")

    # Stats of how long each job took
    # print()
    # print("Breakdown per job:")
    # job_times.sort()
    # for job in job_times:
    #     print(f"{str(round(job, 2))}")

    # Just dump all repo data
    # print(json.dumps([r[1] for r in repo_times]))

if __name__ == "__main__":
    main()
