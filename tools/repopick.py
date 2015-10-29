#!/usr/bin/env python
#
<<<<<<< HEAD
# Copyright (C) 2013-14 The CyanogenMod Project
=======
# Copyright (C) 2013-15 The CyanogenMod Project
>>>>>>> 7fc9ab74b3528db4ff41e49cacf2ed0a157389d9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#
# Run repopick.py -h for a description of this utility.
#

from __future__ import print_function

import sys
import json
import os
import subprocess
import re
import argparse
import textwrap

try:
  # For python3
  import urllib.error
  import urllib.request
except ImportError:
  # For python2
  import imp
  import urllib2
  urllib = imp.new_module('urllib')
  urllib.error = urllib2
  urllib.request = urllib2

# Parse the command line
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=textwrap.dedent('''\
    repopick.py is a utility to simplify the process of cherry picking
    patches from CyanogenMod's Gerrit instance.

    Given a list of change numbers, repopick will cd into the project path
    and cherry pick the latest patch available.

    With the --start-branch argument, the user can specify that a branch
    should be created before cherry picking. This is useful for
    cherry-picking many patches into a common branch which can be easily
    abandoned later (good for testing other's changes.)

    The --abandon-first argument, when used in conjuction with the
    --start-branch option, will cause repopick to abandon the specified
    branch in all repos first before performing any cherry picks.'''))
parser.add_argument('change_number', nargs='*', help='change number to cherry pick.  Use {change number}/{patchset number} to get a specific revision.')
parser.add_argument('-i', '--ignore-missing', action='store_true', help='do not error out if a patch applies to a missing directory')
parser.add_argument('-s', '--start-branch', nargs=1, help='start the specified branch before cherry picking')
parser.add_argument('-a', '--abandon-first', action='store_true', help='before cherry picking, abandon the branch specified in --start-branch')
parser.add_argument('-b', '--auto-branch', action='store_true', help='shortcut to "--start-branch auto --abandon-first --ignore-missing"')
parser.add_argument('-q', '--quiet', action='store_true', help='print as little as possible')
parser.add_argument('-v', '--verbose', action='store_true', help='print extra information to aid in debug')
parser.add_argument('-f', '--force', action='store_true', help='force cherry pick even if commit has been merged')
parser.add_argument('-p', '--pull', action='store_true', help='execute pull instead of cherry-pick')
parser.add_argument('-t', '--topic', help='pick all commits from a specified topic')
parser.add_argument('-Q', '--query', help='pick all commits using the specified query')
args = parser.parse_args()
if args.start_branch == None and args.abandon_first:
    parser.error('if --abandon-first is set, you must also give the branch name with --start-branch')
if args.auto_branch:
    args.abandon_first = True
    args.ignore_missing = True
    if not args.start_branch:
        args.start_branch = ['auto']
if args.quiet and args.verbose:
    parser.error('--quiet and --verbose cannot be specified together')
if len(args.change_number) > 0:
    if args.topic or args.query:
        parser.error('cannot specify a topic (or query) and change number(s) together')
if args.topic and args.query:
    parser.error('cannot specify a topic and a query together')
if len(args.change_number) == 0 and not args.topic and not args.query:
    parser.error('must specify at least one commit id or a topic or a query')

# Helper function to determine whether a path is an executable file
def is_exe(fpath):
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

# Implementation of Unix 'which' in Python
#
# From: http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def which(program):
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

# Simple wrapper for os.system() that:
#   - exits on error if !can_fail
#   - prints out the command if --verbose
#   - suppresses all output if --quiet
def execute_cmd(cmd, can_fail=False):
    if args.verbose:
        print('Executing: %s' % cmd)
    if args.quiet:
        cmd = cmd.replace(' && ', ' &> /dev/null && ')
        cmd = cmd + " &> /dev/null"
    if os.system(cmd):
        if not args.verbose:
            print('\nCommand that failed:\n%s' % cmd)
        if not can_fail:
             sys.exit(1)

# Verifies whether pathA is a subdirectory (or the same) as pathB
def is_pathA_subdir_of_pathB(pathA, pathB):
    pathA = os.path.realpath(pathA) + '/'
    pathB = os.path.realpath(pathB) + '/'
    return(pathB == pathA[:len(pathB)])

# Find the necessary bins - repo
repo_bin = which('repo')
if repo_bin == None:
    repo_bin = os.path.join(os.environ["HOME"], 'repo')
    if not is_exe(repo_bin):
        sys.stderr.write('ERROR: Could not find the repo program in either $PATH or $HOME/bin\n')
        sys.exit(1)

# Find the necessary bins - git
git_bin = which('git')
if not is_exe(git_bin):
    sys.stderr.write('ERROR: Could not find the git program in $PATH\n')
    sys.exit(1)

# Change current directory to the top of the tree
if 'ANDROID_BUILD_TOP' in os.environ:
    top = os.environ['ANDROID_BUILD_TOP']
    if not is_pathA_subdir_of_pathB(os.getcwd(), top):
        sys.stderr.write('ERROR: You must run this tool from within $ANDROID_BUILD_TOP!\n')
        sys.exit(1)
    os.chdir(os.environ['ANDROID_BUILD_TOP'])

# Sanity check that we are being run from the top level of the tree
if not os.path.isdir('.repo'):
    sys.stderr.write('ERROR: No .repo directory found. Please run this from the top of your tree.\n')
    sys.exit(1)

# If --abandon-first is given, abandon the branch before starting
if args.abandon_first:
    # Determine if the branch already exists; skip the abandon if it does not
    plist = subprocess.Popen([repo_bin,"info"], stdout=subprocess.PIPE)
    needs_abandon = False
    while(True):
        pline = plist.stdout.readline().rstrip()
        if not pline:
            break
        matchObj = re.match(r'Local Branches.*\[(.*)\]', pline.decode())
        if matchObj:
            local_branches = re.split('\s*,\s*', matchObj.group(1))
            if any(args.start_branch[0] in s for s in local_branches):
                needs_abandon = True

    if needs_abandon:
        # Perform the abandon only if the branch already exists
        if not args.quiet:
            print('Abandoning branch: %s' % args.start_branch[0])
        cmd = '%s abandon %s' % (repo_bin, args.start_branch[0])
        execute_cmd(cmd)
        if not args.quiet:
            print('')

# Get the list of projects that repo knows about
#   - convert the project name to a project path
project_name_to_path = {}
plist = subprocess.Popen([repo_bin,"list"], stdout=subprocess.PIPE)
project_path = None
while(True):
    pline = plist.stdout.readline().rstrip()
    if not pline:
        break
    ppaths = re.split('\s*:\s*', pline.decode())
    project_name_to_path[ppaths[1]] = ppaths[0]

# Get all commits for a specified query
def fetch_query(query):
    url = 'http://review.cyanogenmod.org/changes/?q=%s' % query
    if args.verbose:
        print('Fetching all commits using query: %s\n' % query)
    f = urllib.request.urlopen(url)
    d = f.read().decode("utf-8")
    if args.verbose:
        print('Result from request:\n' + d)

    # Clean up the result
    d = d.split(')]}\'\n')[1]
    matchObj = re.match(r'\[\s*\]', d)
    if matchObj:
        sys.stderr.write('ERROR: Query %s was not found on the server\n' % query)
        sys.exit(1)
    d = re.sub(r'\[(.*)\]', r'\1', d)
    if args.verbose:
        print('Result from request:\n' + d)

    data = json.loads(d)
    changelist = []
    for c in xrange(0, len(data)):
        changelist.append(data[c]['_number'])

    # Reverse the array as we want to pick the lowest one first
    args.change_number = reversed(changelist)

if args.topic:
    fetch_query("topic:{0}".format(args.topic))

if args.query:
    fetch_query(args.query)

# Check for range of commits and rebuild array
changelist = []
for change in args.change_number:
    c=str(change)
    if '-' in c:
        templist = c.split('-')
        for i in range(int(templist[0]), int(templist[1]) + 1):
            changelist.append(str(i))
    else:
        changelist.append(c)

args.change_number = changelist

# Iterate through the requested change numbers
for changeps in args.change_number:

    if '/' in changeps:
        change = changeps.split('/')[0]
        patchset = changeps.split('/')[1]
    else:
        change = changeps
        patchset = ''

    if not args.quiet:
        if len(patchset) == 0:
            print('Applying change number %s ...' % change)
        else:
            print('Applying change number {change}/{patchset} ...'.format(change=change, patchset=patchset))

    if len(patchset) == 0:
        query_revision = 'CURRENT_REVISION'
    else:
        query_revision = 'ALL_REVISIONS'

    # Fetch information about the change from Gerrit's REST API
    #
    # gerrit returns two lines, a magic string and then valid JSON:
    #   )]}'
    #   [ ... valid JSON ... ]
    url = 'http://review.cyanogenmod.org/changes/?q={change}&o={query_revision}&o=CURRENT_COMMIT&pp=0'.format(change=change, query_revision=query_revision)
    if args.verbose:
        print('Fetching from: %s\n' % url)
    try:
        f = urllib.request.urlopen(url)
    except urllib.error.URLError:
        sys.stderr.write('ERROR: Server reported an error, or cannot be reached\n')
        sys.exit(1)
    d = f.read().decode("utf-8")
    if args.verbose:
        print('Result from request:\n' + d)

    # Clean up the result
    d = d.split('\n')[1]
    matchObj = re.match(r'\[\s*\]', d)
    if matchObj:
        sys.stderr.write('ERROR: Change number %s was not found on the server\n' % change)
        sys.exit(1)
    d = re.sub(r'\[(.*)\]', r'\1', d)

    # Parse the JSON
    try:
        data = json.loads(d)
    except ValueError:
        sys.stderr.write('ERROR: The response from the server could not be parsed properly\n')
        if not args.verbose:
            sys.stderr.write('The malformed response was: %s\n' % d)
        sys.exit(1)

    # Extract information from the JSON response
    date_fluff       = '.000000000'
    project_name     = data['project']
    project_branch   = data['branch']
    change_number    = data['_number']
    status           = data['status']
    patchsetfound    = False

    if len(patchset) > 0:
        try:
            for revision in data['revisions']:
                if (int(data['revisions'][revision]['_number']) == int(patchset)) and not patchsetfound:
                    target_revision = data['revisions'][revision]
                    if args.verbose:
                       print('Using found patch set {patchset} ...'.format(patchset=patchset))
                    patchsetfound = True
                    break
            if not patchsetfound:
                print('ERROR: The patch set could not be found, using CURRENT_REVISION instead.')
        except:
            print('ERROR: The patch set could not be found, using CURRENT_REVISION instead.')
            patchsetfound = False

    if not patchsetfound:
        target_revision = data['revisions'][data['current_revision']]

    current_revision = data['revisions'][data['current_revision']]

    patch_number     = target_revision['_number']
    fetch_url        = target_revision['fetch']['anonymous http']['url']
    fetch_ref        = target_revision['fetch']['anonymous http']['ref']
    author_name      = current_revision['commit']['author']['name']
    author_email     = current_revision['commit']['author']['email']
    author_date      = current_revision['commit']['author']['date'].replace(date_fluff, '')
    committer_name   = current_revision['commit']['committer']['name']
    committer_email  = current_revision['commit']['committer']['email']
    committer_date   = current_revision['commit']['committer']['date'].replace(date_fluff, '')
    subject          = current_revision['commit']['subject']

    # Check if commit has already been merged and exit if it has, unless -f is specified
    if status == "MERGED":
        if args.force:
            print("!! Force-picking a merged commit !!\n")
        else:
            print("Commit already merged. Skipping the cherry pick.\nUse -f to force this pick.")
            continue;

    # Convert the project name to a project path
    #   - check that the project path exists
    if project_name in project_name_to_path:
        project_path = project_name_to_path[project_name];

        if project_path.startswith('hardware/qcom/'):
            split_path = project_path.split('/')
            # split_path[2] might be display or it might be display-caf, trim the -caf
            split_path[2] = split_path[2].split('-')[0]

            # Need to treat hardware/qcom/{audio,display,media} specially
            if split_path[2] == 'audio' or split_path[2] == 'display' or split_path[2] == 'media':
                split_branch = project_branch.split('-')

                # display is extra special
                if split_path[2] == 'display' and len(split_path) == 3:
                    project_path = '/'.join(split_path)
                else:
                    project_path = '/'.join(split_path[:-1])

                if len(split_branch) == 4 and split_branch[0] == 'cm' and split_branch[2] == 'caf':
                    project_path += '-caf/msm' + split_branch[3]
                # audio and media are different from display
                elif split_path[2] == 'audio' or split_path[2] == 'media':
                    project_path += '/default'
    elif args.ignore_missing:
        print('WARNING: Skipping %d since there is no project directory for: %s\n' % (change_number, project_name))
        continue;
    else:
        sys.stderr.write('ERROR: For %d, could not determine the project path for project %s\n' % (change_number, project_name))
        sys.exit(1)

    # If --start-branch is given, create the branch (more than once per path is okay; repo ignores gracefully)
    if args.start_branch:
        cmd = '%s start %s %s' % (repo_bin, args.start_branch[0], project_path)
        execute_cmd(cmd)

    # Print out some useful info
    if not args.quiet:
        print('--> Subject:       "%s"' % subject)
        print('--> Project path:  %s' % project_path)
        print('--> Change number: %d (Patch Set %d)' % (change_number, patch_number))
        print('--> Author:        %s <%s> %s' % (author_name, author_email, author_date))
        print('--> Committer:     %s <%s> %s' % (committer_name, committer_email, committer_date))

    # Try fetching from GitHub first
    if args.verbose:
       print('Trying to fetch the change from GitHub')
    if args.pull:
      cmd = 'cd %s && git pull --no-edit github %s' % (project_path, fetch_ref)
    else:
      cmd = 'cd %s && git fetch github %s' % (project_path, fetch_ref)
    execute_cmd(cmd, True)
    # Check if it worked
    FETCH_HEAD = '%s/.git/FETCH_HEAD' % project_path
    if os.stat(FETCH_HEAD).st_size == 0:
        # That didn't work, fetch from Gerrit instead
        if args.verbose:
          print('Fetching from GitHub didn\'t work, trying to fetch the change from Gerrit')
        if args.pull:
          cmd = 'cd %s && git pull --no-edit %s %s' % (project_path, fetch_url, fetch_ref)
        else:
          cmd = 'cd %s && git fetch %s %s' % (project_path, fetch_url, fetch_ref)
        execute_cmd(cmd)
    # Perform the cherry-pick
    cmd = 'cd %s && git cherry-pick FETCH_HEAD' % (project_path)
    if not args.pull:
      execute_cmd(cmd)
    if not args.quiet:
        print('')

from xml.etree import ElementTree

try:
    # For python3
    import urllib.error
    import urllib.request
except ImportError:
    # For python2
    import imp
    import urllib2
    urllib = imp.new_module('urllib')
    urllib.error = urllib2
    urllib.request = urllib2


# Verifies whether pathA is a subdirectory (or the same) as pathB
def is_subdir(a, b):
    a = os.path.realpath(a) + '/'
    b = os.path.realpath(b) + '/'
    return b == a[:len(b)]


def fetch_query_via_ssh(remote_url, query):
    """Given a remote_url and a query, return the list of changes that fit it
       This function is slightly messy - the ssh api does not return data in the same structure as the HTTP REST API
       We have to get the data, then transform it to match what we're expecting from the HTTP RESET API"""
    if remote_url.count(':') == 2:
        (uri, userhost, port) = remote_url.split(':')
        userhost = userhost[2:]
    elif remote_url.count(':') == 1:
        (uri, userhost) = remote_url.split(':')
        userhost = userhost[2:]
        port = 29418
    else:
        raise Exception('Malformed URI: Expecting ssh://[user@]host[:port]')


    out = subprocess.check_output(['ssh', '-x', '-p{0}'.format(port), userhost, 'gerrit', 'query', '--format=JSON --patch-sets --current-patch-set', query])

    reviews = []
    for line in out.split('\n'):
        try:
            data = json.loads(line)
            # make our data look like the http rest api data
            review = {
                'branch': data['branch'],
                'change_id': data['id'],
                'current_revision': data['currentPatchSet']['revision'],
                'number': int(data['number']),
                'revisions': {patch_set['revision']: {
                    'number': int(patch_set['number']),
                    'fetch': {
                        'ssh': {
                            'ref': patch_set['ref'],
                            'url': u'ssh://{0}:{1}/{2}'.format(userhost, port, data['project'])
                        }
                    }
                } for patch_set in data['patchSets']},
                'subject': data['subject'],
                'project': data['project'],
                'status': data['status']
            }
            reviews.append(review)
        except:
            pass
    args.quiet or print('Found {0} reviews'.format(len(reviews)))
    return reviews


def fetch_query_via_http(remote_url, query):

    """Given a query, fetch the change numbers via http"""
    url = '{0}/changes/?q={1}&o=CURRENT_REVISION&o=ALL_REVISIONS'.format(remote_url, query)
    data = urllib.request.urlopen(url).read().decode('utf-8')
    reviews = json.loads(data[5:])

    for review in reviews:
        review[u'number'] = review.pop('_number')

    return reviews


def fetch_query(remote_url, query):
    """Wrapper for fetch_query_via_proto functions"""
    if remote_url[0:3] == 'ssh':
        return fetch_query_via_ssh(remote_url, query)
    elif remote_url[0:4] == 'http':
        return fetch_query_via_http(remote_url, query.replace(' ', '+'))
    else:
        raise Exception('Gerrit URL should be in the form http[s]://hostname/ or ssh://[user@]host[:port]')

if __name__ == '__main__':
    # Default to CyanogenMod Gerrit
    default_gerrit = 'http://review.cyanogenmod.org'

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=textwrap.dedent('''\
        repopick.py is a utility to simplify the process of cherry picking
        patches from CyanogenMod's Gerrit instance (or any gerrit instance of your choosing)

        Given a list of change numbers, repopick will cd into the project path
        and cherry pick the latest patch available.

        With the --start-branch argument, the user can specify that a branch
        should be created before cherry picking. This is useful for
        cherry-picking many patches into a common branch which can be easily
        abandoned later (good for testing other's changes.)

        The --abandon-first argument, when used in conjunction with the
        --start-branch option, will cause repopick to abandon the specified
        branch in all repos first before performing any cherry picks.'''))
    parser.add_argument('change_number', nargs='*', help='change number to cherry pick.  Use {change number}/{patchset number} to get a specific revision.')
    parser.add_argument('-i', '--ignore-missing', action='store_true', help='do not error out if a patch applies to a missing directory')
    parser.add_argument('-s', '--start-branch', nargs=1, help='start the specified branch before cherry picking')
    parser.add_argument('-a', '--abandon-first', action='store_true', help='before cherry picking, abandon the branch specified in --start-branch')
    parser.add_argument('-b', '--auto-branch', action='store_true', help='shortcut to "--start-branch auto --abandon-first --ignore-missing"')
    parser.add_argument('-q', '--quiet', action='store_true', help='print as little as possible')
    parser.add_argument('-v', '--verbose', action='store_true', help='print extra information to aid in debug')
    parser.add_argument('-f', '--force', action='store_true', help='force cherry pick even if change is closed')
    parser.add_argument('-p', '--pull', action='store_true', help='execute pull instead of cherry-pick')
    parser.add_argument('-P', '--path', help='use the specified path for the change')
    parser.add_argument('-t', '--topic', help='pick all commits from a specified topic')
    parser.add_argument('-Q', '--query', help='pick all commits using the specified query')
    parser.add_argument('-g', '--gerrit', default=default_gerrit, help='Gerrit Instance to use. Form proto://[user@]host[:port]')
    args = parser.parse_args()
    if not args.start_branch and args.abandon_first:
        parser.error('if --abandon-first is set, you must also give the branch name with --start-branch')
    if args.auto_branch:
        args.abandon_first = True
        args.ignore_missing = True
        if not args.start_branch:
            args.start_branch = ['auto']
    if args.quiet and args.verbose:
        parser.error('--quiet and --verbose cannot be specified together')

    if (1 << bool(args.change_number) << bool(args.topic) << bool(args.query)) != 2:
        parser.error('One (and only one) of change_number, topic, and query are allowed')

    # Change current directory to the top of the tree
    if 'ANDROID_BUILD_TOP' in os.environ:
        top = os.environ['ANDROID_BUILD_TOP']

        if not is_subdir(os.getcwd(), top):
            sys.stderr.write('ERROR: You must run this tool from within $ANDROID_BUILD_TOP!\n')
            sys.exit(1)
        os.chdir(os.environ['ANDROID_BUILD_TOP'])

    # Sanity check that we are being run from the top level of the tree
    if not os.path.isdir('.repo'):
        sys.stderr.write('ERROR: No .repo directory found. Please run this from the top of your tree.\n')
        sys.exit(1)

    # If --abandon-first is given, abandon the branch before starting
    if args.abandon_first:
        # Determine if the branch already exists; skip the abandon if it does not
        plist = subprocess.check_output(['repo', 'info'])
        needs_abandon = False
        for pline in plist:
            matchObj = re.match(r'Local Branches.*\[(.*)\]', pline)
            if matchObj:
                local_branches = re.split('\s*,\s*', matchObj.group(1))
                if any(args.start_branch[0] in s for s in local_branches):
                    needs_abandon = True

        if needs_abandon:
            # Perform the abandon only if the branch already exists
            if not args.quiet:
                print('Abandoning branch: %s' % args.start_branch[0])
            subprocess.check_output(['repo', 'abandon', args.start_branch[0]])
            if not args.quiet:
                print('')

    # Get the master manifest from repo
    #   - convert project name and revision to a path
    project_name_to_data = {}
    manifest = subprocess.check_output(['repo', 'manifest'])
    xml_root = ElementTree.fromstring(manifest)
    projects = xml_root.findall('project')
    default_revision = xml_root.findall('default')[0].get('revision').split('/')[-1]

    #dump project data into the a list of dicts with the following data:
    #{project: {path, revision}}

    for project in projects:
        name = project.get('name')
        path = project.get('path')
        revision = project.get('revision')
        if revision is None:
            revision = default_revision

        if not name in project_name_to_data:
            project_name_to_data[name] = {}
        project_name_to_data[name][revision] = path

    # get data on requested changes
    reviews = []
    change_numbers = []
    if args.topic:
        reviews = fetch_query(args.gerrit, 'topic:{0}'.format(args.topic))
        change_numbers = sorted([str(r['number']) for r in reviews])
    if args.query:
        reviews = fetch_query(args.gerrit, args.query)
        change_numbers = sorted([str(r['number']) for r in reviews])
    if args.change_number:
        reviews = fetch_query(args.gerrit, ' OR '.join('change:{0}'.format(x.split('/')[0]) for x in args.change_number))
        change_numbers = args.change_number

    # make list of things to actually merge
    mergables = []

    for change in change_numbers:
        patchset = None
        if '/' in change:
            (change, patchset) = change.split('/')
        change = int(change)

        review = [x for x in reviews if x['number'] == change][0]
        mergables.append({
            'subject': review['subject'],
            'project': review['project'],
            'branch': review['branch'],
            'change_number': review['number'],
            'status': review['status'],
            'fetch': None
        })
        mergables[-1]['fetch'] = review['revisions'][review['current_revision']]['fetch']
        mergables[-1]['id'] = change
        if patchset:
            try:
                mergables[-1]['fetch'] = [x['fetch'] for x in review['revisions'] if x['_number'] == patchset][0]
                mergables[-1]['id'] = '{0}/{1}'.format(change, patchset)
            except (IndexError, ValueError):
                args.quiet or print('ERROR: The patch set {0}/{1} could not be found, using CURRENT_REVISION instead.'.format(change, patchset))

    for item in mergables:
        args.quiet or print('Applying change number {0}...'.format(item['id']))
        # Check if change is open and exit if it's not, unless -f is specified
        if (item['status'] != 'OPEN' and item['status'] != 'NEW') and not args.query:
            if args.force:
                print('!! Force-picking a closed change !!\n')
            else:
                print('Change status is ' + item['status'] + '. Skipping the cherry pick.\nUse -f to force this pick.')
                continue

        # Convert the project name to a project path
        #   - check that the project path exists
        project_path = None

        if item['project'] in project_name_to_data and item['branch'] in project_name_to_data[item['project']]:
            project_path = project_name_to_data[item['project']][item['branch']]
        elif args.path:
            project_path = args.path
        elif args.ignore_missing:
            print('WARNING: Skipping {0} since there is no project directory for: {1}\n'.format(item['id'], item['project']))
            continue
        else:
            sys.stderr.write('ERROR: For {0}, could not determine the project path for project {1}\n'.format(item['id'], item['project']))
            sys.exit(1)

        # If --start-branch is given, create the branch (more than once per path is okay; repo ignores gracefully)
        if args.start_branch:
            subprocess.check_output(['repo', 'start', args.start_branch[0], project_path])

        # Print out some useful info
        if not args.quiet:
            print('--> Subject:       "{0}"'.format(item['subject']))
            print('--> Project path:  {0}'.format(project_path))
            print('--> Change number: {0} (Patch Set {0})'.format(item['id']))

        if 'anonymous http' in item['fetch']:
            method = 'anonymous http'
        else:
            method = 'ssh'

        # Try fetching from GitHub first if using default gerrit
        if args.gerrit == default_gerrit:
            if args.verbose:
                print('Trying to fetch the change from GitHub')

            if args.pull:
                cmd = ['git pull --no-edit github', item['fetch'][method]['ref']]
            else:
                cmd = ['git fetch github', item['fetch'][method]['ref']]
            if args.quiet:
                cmd.append('--quiet')
            else:
                print(cmd)
            result = subprocess.call([' '.join(cmd)], cwd=project_path, shell=True)
            if result != 0:
                print('ERROR: git command failed')
                sys.exit(result)
            FETCH_HEAD = '{0}/.git/FETCH_HEAD'.format(project_path)
        # Check if it worked
        if args.gerrit != default_gerrit or os.stat(FETCH_HEAD).st_size == 0:
            # If not using the default gerrit or github failed, fetch from gerrit.
            if args.verbose:
                if args.gerrit == default_gerrit:
                    print('Fetching from GitHub didn\'t work, trying to fetch the change from Gerrit')
                else:
                    print('Fetching from {0}'.format(args.gerrit))

            if args.pull:
                cmd = ['git pull --no-edit', item['fetch'][method]['url'], item['fetch'][method]['ref']]
            else:
                cmd = ['git fetch', item['fetch'][method]['url'], item['fetch'][method]['ref']]
            if args.quiet:
                cmd.append('--quiet')
            else:
                print(cmd)
            result = subprocess.call([' '.join(cmd)], cwd=project_path, shell=True)
            if result != 0:
                print('ERROR: git command failed')
                sys.exit(result)
        # Perform the cherry-pick
        if not args.pull:
            cmd = ['git cherry-pick FETCH_HEAD']
            if args.quiet:
                cmd_out = open(os.devnull, 'wb')
            else:
                cmd_out = None
            result = subprocess.call(cmd, cwd=project_path, shell=True, stdout=cmd_out, stderr=cmd_out)
            if result != 0:
                print('ERROR: git command failed')
                sys.exit(result)
        if not args.quiet:
            print('')
