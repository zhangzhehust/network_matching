#!/usr/bin/python

import os
import subprocess
import datetime
import classad

def check_data_locality(ad):
  if "MATCH_EXP_JOB_GLIDEIN_CMSSite" in ad.keys():
    if "DESIRED_CMSDataLocations" in ad.keys():
      if ad["MATCH_EXP_JOB_GLIDEIN_CMSSite"] in ad["DESIRED_CMSDataLocations"]:
        ad["ComputeDataOnsite"] = True
      else:
        ad["ComputeDataOnsite"] = False
  

# determine current date & time
now = datetime.datetime.now()
timestamp_str = str(now)
timestamp = timestamp_str.split(" ")
timestamp_str = timestamp[0].replace("-","") + "_" + \
                timestamp[1].split(".")[0].replace(":","")

collector = "vocms099.cern.ch"
raw_log = "/home/bockelman/zzhang/ELK_stack/cms_production_log_backup/condor_history_" + timestamp_str + ".log"
processed_log = "/var/log/cms_production/p_condor_history_" + timestamp_str + ".log"
checkpoint_path = "/home/bockelman/zzhang/ELK_stack/cms_production_job_ID_history.txt"

condor_history_log = open(raw_log, "a+")
condor_status_command = "condor_status -pool " + collector + " -schedd -wide"
p = subprocess.Popen(condor_status_command, stdout=subprocess.PIPE, shell=True)
(output, err) = p.communicate()

p_status = p.wait()

lines = output.split('\n')
line_num = len(lines)

# The first 2 lines and the last 5 lines are not actual schedd output ignore;
schedd_list = []
for line in lines[2:line_num-5]:
  words = line.split(' ')

  # process schedd that waits for ever...
  ignore_list = []
  ignore_list.append("crab3-1@submit-5.t2.ucsd.edu")
  ignore_list.append("crab3-3@submit-4.t2.ucsd.edu")
  ignore_list.append("submit-6.t2.ucsd.edu")
  ignore_list.append("crab3-7@vocms0114.cern.ch")
  ignore_list.append("crab3-2@vocms0109.cern.ch")
  ignore_list.append("vocms0117.cern.ch")
  ignore_list.append("crab3-5@vocms059.cern.ch")
  ignore_list.append("crab3-4@vocms066.cern.ch")
  ignore_list.append("crab3test-2@vocms095.cern.ch")
  ignore_list.append("crab3test-3@vocms096.cern.ch")
  # ignore two schedds that return Error opening history file
  ignore_list.append("vocms005.cern.ch")
  ignore_list.append("vocms053.cern.ch")
  if words[0] not in ignore_list:
    print words[0]
    schedd_list.append(words[0])


# open the job_ID_history.txt file for the ClusterID.ProcessID we processed
# in the very last cron job
job_ID_history = open(checkpoint_path, "r")
lines = job_ID_history.readlines()
schedd_ID_dict = {}
if lines:
  # remove the '\n' character at each line
  for i in range(len(lines)):
    lines[i] = lines[i][:-1]
  schedd_ID_dict = dict(line.split(" ") for line in lines)
# print out the dictionary for schedd : most_recent_processed_job_ID mapping
print schedd_ID_dict
job_ID_history.close()

# some pre-recorded error message that is used for checking
error_msg = "Unable to send history command to remote schedd;"

for schedd in schedd_list:
  # First, let's only check the first condor job history entry 
  condor_history_command = "condor_history -pool " + collector + \
                            "  -name " + schedd + " -match 1"
  # debug
  print condor_history_command
  p = subprocess.Popen(condor_history_command, \
                       stdout=subprocess.PIPE, shell=True)
  (output, err) = p.communicate()
  p_status = p.wait()
  lines = output.split('\n')
  # cases to be considered
  # 1. Some of the schedds do not have condor history enabled or permitted
  if lines[1] == '':
    pass # do nothing
  else:
    # get Cluster ID and Process ID for most recent condor job history entry
    attributes = lines[1].split(' ')
    k = 0
    # make sure we find the ClusterID.ProcID attribute
    while(attributes[k] == ''):
      k = k + 1
    #print "updated ClusterID and ProcID is: " + attributes[0]
    updated_ClusterID = attributes[k].split('.')[0]
    updated_ProcessID = attributes[k].split('.')[1]

    # now get the whole list of condor job classad entries and read until the 
    # old Cluster ID and Process ID (with option -l)
    condor_history_command = "condor_history -pool " + collector + \
                              " -name " + schedd + " -l"
    #print condor_history_command
    p = subprocess.Popen(condor_history_command, \
                         stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()
    lines = output.split('\n')

    if schedd_ID_dict and schedd_ID_dict.has_key(schedd): 
      # there is old Cluster ID and Process ID, read until it
      old_ClusterID = schedd_ID_dict[schedd].split('.')[0]
      old_ProcessID = schedd_ID_dict[schedd].split('.')[1]

      j = 0
      output = ""
      ClusterID_flag = False
      ProcessID_flag = False
      while(j < len(lines)):
        if(lines[j] != ''):
          #output = output + lines[j] + '\n'
          if "=" in lines[j]:
            key = lines[j].split(" = ", 1)[0]
            value = lines[j].split(" = ", 1)[1]
            if value.startswith("\"") and not value.endswith("\""):
              value = value + "\""
              output = output + lines[j] + "\"" + "\n"
            else:
              output = output + lines[j] + "\n"

            if key == "ClusterId" and value == old_ClusterID:
              ClusterID_flag = True
            if key == "ProcId" and value == old_ProcessID:
              ProcessID_flag = True
        else:
          output = output + '\n'
          if ClusterID_flag == True and ProcessID_flag == True:
            # This means we reached the condor job history entry point already 
            # processed last time, we don't write this block to file and break 
            # from the while loop
            break
          else:
            # We have collected one block of key value pairs for one job, write
            # the output to file
            condor_history_log.write(output)
            output = ""

          # update the flags
          ClusterID_flag = False
          ProcessID_flag = False

        j = j + 1

      # update the most recent processed ClusterID and ProcID for this schedd
      if not (old_ClusterID == updated_ClusterID and \
                                          old_ProcessID == updated_ProcessID):
        schedd_ID_dict[schedd] = updated_ClusterID + '.' + \
                                          updated_ProcessID


    else: # no old info, read the whole output list. This is a one-time thing
      j = 0
      output = ""
      while(j < len(lines)):
        if(lines[j] != ''):
          output = output + lines[j] + '\n'
        else:
          output = output + '\n'
          condor_history_log.write(output)
          output = ""
        j = j + 1

      # update the most recent processed ClusterID and ProcID for this schedd
      schedd_ID_dict[schedd] = updated_ClusterID + '.' + \
                                        updated_ProcessID

# When we get out the "for" loop for all the schedds, update the job_ID_history
# dictionary file
print schedd_ID_dict
output = ""
for key, value in schedd_ID_dict.iteritems():
  output = output + key + ' ' + value + '\n'
job_ID_history = open(checkpoint_path, "w")
job_ID_history.write(output)

# close all the opening files
job_ID_history.close()
condor_history_log.close()

# parse the generated condor history log file and evaluate attributes
# write to new log files
input = open(raw_log, "r")
output = open(processed_log, "a+")

global_job_id_set = set()
while True:
  try:
    ad = classad.parseNext(input)
    for k in ad:
      if ad.eval(k) is classad.Value.Undefined:
        del ad[k]
      else:
        ad[k] = ad.eval(k)
    if "GlobalJobId" in ad.keys():
      if ad["GlobalJobId"] in global_job_id_set:
        pass
      else:
        global_job_id_set.add(ad["GlobalJobId"])
        check_data_locality(ad)
        output.write(ad.printOld()+"\n")
    else:
      check_data_locality(ad)
      output.write(ad.printOld()+"\n")
  except StopIteration:
    break
input.close()
output.close()

# delete the raw history log after the processed log is generated
os.remove(raw_log)
