#!/usr/bin/python

import ConfigParser
import os
import re
import glob
import shutil
import sys
import argparse


class bcolors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''


SEASON_AND_EPISODE_GUESSER = [
    ('Season %(season)s/S%(season)sE%(episode)s.ts', re.compile('.*(?P<season>[0-9]+)\. Staffel, Folge (?P<episode>[0-9]+):')),    # 1. Staffel, Folge 3:
    ('Season %(season)s/S%(season)sE%(episode)s.ts', re.compile('.*(?P<season>[0-9]+)\. Staffel! (?P<episode>[0-9]+)\. Folge:')),  # 6. Staffel! 8. Folge:
    ('Folge %(episode)s.ts', re.compile('Folge (?P<episode>[0-9]+):')),
]

RE_TS_CHECK = re.compile('Errors: ([0-9]+)')


def touch(path):
    with open(path, 'a'):
        os.utime(path, None)


def shellquote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def read_check_ts_file(file_name):
    try:
        check_file_content = open(file_name).read()
        errors = RE_TS_CHECK.match(check_file_content)
        if not errors:
            raise Exception()
        error_count = int(errors.group(1))
        return error_count
    except:
        return -1 


class VdrInfoFile(object):
    def __init__(self, file_name):
        info_file = open(file_name)
        self.info_list = {}
        self.dest_path = None
        self.dest_file_name = None
        for line in info_file:
            id, text = line.split(' ', 1)
            self.info_list[id] = text.strip()

    @property
    def description(self):
        if self.info_list.has_key('D'):
           return self.info_list['D']
        return ''

    @property
    def title(self):
        if self.info_list.has_key('S'):
            return self.info_list['S']
        return ''

    def guess_dest_path(self, tv_show_config):
        if tv_show_config.dest_file_name:
             if tv_show_config.dest_file_name.lower() == 'title':
                 self.dest_path = ''
                 self.dest_file_name = '%s.ts' % self.title
                 return True
        for dest_dir, regex in SEASON_AND_EPISODE_GUESSER:
             m = regex.match(self.description)
             if m:
                 path_with_file_name = dest_dir % m.groupdict()
                 self.dest_path, self.dest_file_name = os.path.split(path_with_file_name)
                 return True
        return False 


class TvShowConfig(object):
    def __init__(self, source_path, dest_path, delete_duplicates=False, dest_file_name=None):
        self.source_path = source_path
        self.dest_path = dest_path
        self.delete_duplicates = delete_duplicates
        self.dest_file_name = dest_file_name

    def __repr__(self):
        return "<TvShowConfig source='%s' dest='%s'>" % (self.source_path, self.dest_path)


class TvShowConfigList(list):
    pass


class Organizer(object):
    def __init__(self):
        self.tv_show_config_list = TvShowConfigList()
        self.default_path = ''

    def read_config(self, file_name):
        config = ConfigParser.RawConfigParser()
        config.read(file_name)
         
        self.default_path = config.get('Options', 'default-path')
        self.delete_duplicates = config.getboolean('Options', 'delete-duplicates')
        self.vdr_recording_path = config.get('Options', 'vdr-recording-path')
        
        section_list = config.sections()
        for section_name in section_list:
            if section_name.lower() == 'options':
                continue
            # TODO: logger.critical and exit(1)
            path_vdr = config.get(section_name, 'vdr-path')
            try:
                path_dest = config.get(section_name, 'dest-path')
            except ConfigParser.NoOptionError:
                path_dest = path_vdr

            try:
                delete_duplicates = config.getboolean(section_name, 'delete-duplicates')
            except ConfigParser.NoOptionError:
                delete_duplicates = None

            try:
                dest_file_name = config.get(section_name, 'dest-file-name')
            except ConfigParser.NoOptionError:
                dest_file_name = None

            tv_show_config = TvShowConfig(path_vdr, path_dest, delete_duplicates=delete_duplicates, dest_file_name=dest_file_name)
            #print tv_show_config
            self.tv_show_config_list.append(tv_show_config)


def list_directory(path, prefix='    '):
    content = sorted(os.listdir(path))
    for c in content:
        print '%s%s' % (prefix, c)
        full_path = os.path.join(path,c)
        if os.path.isdir(full_path):
            list_directory(full_path, prefix=prefix+'    ')


parser = argparse.ArgumentParser(description='Organize TV Shows recorded from vdr.')

parser.add_argument('--dry', dest='dry', action='store_true', help='Dry run (do not harm)')
parser.add_argument('--error-limit', dest='error_limit', action='store', type=int, default=0, help='How many errors may a recording have')
parser.add_argument('--keep-duplicates', dest='keep_duplicates', action='store_true', help='Do not delete duplicates')
parser.add_argument('--show', dest='show', action='store', help='Only process specific show')
parser.add_argument('--rec', dest='rec', action='store', type=int, help='Only process specific recording (requires --show)')
parser.add_argument('--move-to', dest='move_to', action='store', help='Moves a specific recording (requires --show, --rec)')
parser.add_argument('--delete', dest='delete', action='store_true', help='Deletes a specific recording (requires --show, --rec)')
parser.add_argument('--list', dest='list', action='store_true', help='Lists already sorted recordings (requires --show)')

args = parser.parse_args()

if (
    (args.list and not args.show) or
    (args.rec and not args.show) or 
    (args.move_to and not args.rec) or 
    (args.delete and not args.rec) or 
    (args.move_to and args.delete) or
    (args.move_to and args.list) or
    (args.delete and args.list)
    ):
    parser.print_help()
    sys.exit()

organizer = Organizer()
organizer.read_config('/etc/vdr-organizer.ini')

for tv_show_config in organizer.tv_show_config_list:
    if args.show and tv_show_config.dest_path != args.show:
        continue

    full_dest_path = os.path.join(organizer.default_path, tv_show_config.dest_path)
    print bcolors.HEADER + full_dest_path + bcolors.ENDC
    
    if args.list:
        list_directory(full_dest_path, prefix='    ')
        continue

    full_source_path = os.path.join(organizer.vdr_recording_path, tv_show_config.source_path)
    if not os.path.exists(full_source_path):
        #print "    [-] Source path '%s' not found." % full_source_path
        continue

    recording_index = 0
    recording_list = os.listdir(full_source_path)
    for rec in sorted(recording_list):
        recording_index += 1

        if args.rec and args.rec != recording_index:
            continue
        
        print "    %s%s%s [%d]" % (bcolors.BLUE, rec, bcolors.ENDC, recording_index)

        current_rec_path = os.path.join(full_source_path, rec)
        current_info_file = os.path.join(current_rec_path, 'info')
        if not os.path.exists(current_info_file):
            print "        [-] Ignoring directory '%s'. Does not have info file." % rec
            continue

        if not args.move_to:
            current_info = VdrInfoFile(current_info_file)
            has_dest_path = current_info.guess_dest_path(tv_show_config) 
       
            if has_dest_path: 
                current_dest_path = os.path.join(full_dest_path, current_info.dest_path)
                current_dest_file_name = os.path.join(current_dest_path, current_info.dest_file_name)
                print "        => %s" % (current_dest_file_name)
            else:
                print "        [-] Could not guess title."
                print "            Title: %s" % current_info.title
                print "            Description: %s" % current_info.description[:100]
        else:
            has_dest_path = True
            temp_dest_path, temp_dest_file_name = os.path.split(args.move_to)
            current_dest_path = os.path.join(full_dest_path, temp_dest_path)
            current_dest_file_name = os.path.join(current_dest_path, temp_dest_file_name)
            args.keep_duplicates = True
        
        # .ts files in source directory
        ts_file_list = glob.glob(os.path.join(current_rec_path, '*.ts'))
        temp_name_list, temp_size_list = [], []
        full_size = 0
        for ts_file in sorted(ts_file_list):
            temp_name_list.append(os.path.basename(ts_file))
            size = os.path.getsize(ts_file)
            full_size += size
            temp_size_list.append('{0:,} MiB'.format(size/1024/1024))
        print "        %s  [%s]" % (', '.join(temp_name_list), '; '.join(temp_size_list))

        if len(ts_file_list) == 0:
            print "        [-] No .ts file found"
        elif len(ts_file_list) > 1:
            print "        [-] Only need 1 .ts file. Got %d." % len(ts_file_list)
        
        # ts_check error control
        error_count = read_check_ts_file(os.path.join(current_rec_path, 'check.result'))
        if error_count < 0:
            print "        [+] Creating check.result..."
            command = 'vdr-checkts %s > %s' % (shellquote(current_rec_path), shellquote(os.path.join(current_rec_path, 'check.result')))
            os.system(command)
            error_count = read_check_ts_file(os.path.join(current_rec_path, 'check.result'))
            if error_count < 0:
                print "        [-] Could not create check.result."
                print "        [-] Command: '%s'" % command
                continue    

        if error_count > 0:
            print "        [-] Recording has %d errors." % error_count

        if full_size == 0:
            print "        [-] Recording is empty."
            print "        [+] Removing empty recording."
            if (not args.dry):
                shutil.rmtree(current_rec_path)
            continue

        if has_dest_path and os.path.exists(current_dest_file_name):
            if (args.keep_duplicates):
                print "        [-] Removing of duplicates overwritten from command line."
                continue
            if (organizer.delete_duplicates == False):
                print "        [-] File already exists."
                continue
            print "        [+] Removing duplicate."
            if (not args.dry):
                shutil.rmtree(current_rec_path)
            continue

        if (len(ts_file_list) != 1) or (error_count > args.error_limit) or (not has_dest_path) or (full_size == 0):
            continue

        if not os.path.exists(current_dest_path):
            if (not args.dry):
                os.makedirs(current_dest_path)
        
        ts_file = ts_file_list[0] 
        
        print "        [+] Copying file to '%s'..." % current_dest_file_name
        if (not args.dry):
            shutil.copyfile(ts_file, current_dest_file_name)
        print "        [+] Removing recording.."
        if (not args.dry):
            shutil.rmtree(current_rec_path)

touch(os.path.join(organizer.vdr_recording_path, '.update'))

