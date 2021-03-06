#!/bin/sh
#
# Copyright 2015 The Cluster-Insight Authors. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Setup Cluster-Insight in a given project running on Google Cloud Platform
# (GCP).
# You should run this script only once per project.
# It will set up *all* instances (VMs) that belong to this project.
# If you run this script more than once, it will do nothing (idempotent).
#
# If you wish to set up only a subset of the instances (VMs) in a given
# project, you should should run node-setup.sh explictly on the appropriate
# instances. See the comment at the beginning of the node-setup.sh script.
#
# The script will print "SCRIPT ALL DONE" if it configured all instances
# successfully. This includes the case that nothing was done.
#
# The script will print "SCRIPT FAILED" if it failed to configure any node.
#
# You should run this script from your workstation after setting up your GCP
# project.
#
# Usage:
#  ./project_setup PROJECT_ID

MINION_SCRIPT_NAME="./node-setup.sh"
MASTER_SCRIPT_NAME="./master-setup.sh"
FIREWALL_RULE_NAME="cluster-insight-collector"

if [ $# -ne 1 ]; then
  echo "SCRIPT FAILED"
  echo "usage: $0 PROJECT_ID"
  exit 1
fi

readonly PROJECT_ID="$1"

if [[ !((-r "${MINION_SCRIPT_NAME}") && (-r "${MASTER_SCRIPT_NAME}")) ]]; then
  echo "SCRIPT FAILED"
  echo "cannot read script ${MINION_SCRIPT_NAME} or ${MASTER_SCRIPT_NAME}"
  exit 1
fi

# The 'nodes_and_zones' array will contain pairs of (node, zone) strings.
# The node name will appear in the even elements of the array, and the
# corresponding zone name will appear in the following odd element.
declare -a nodes_and_zones
names_count=0
for name in $(gcloud compute --project="${PROJECT_ID}" instances list |
              fgrep RUNNING | awk '{print $1, $2}'); do
  nodes_and_zones[${names_count}]="${name}"
  names_count=$((names_count+1))
done

if [[ ${names_count} == 0 ]]; then
  echo "SCRIPT FAILED"
  echo "No instances found in project ${PROJECT_ID}"
  exit 1
fi

minion_ok_count=0
failure_count=0
master_instance_name=""
master_zone_name=""

i=0
while [[ ${i} -lt ${names_count} ]]; do
  instance_name="${nodes_and_zones[${i}]}"
  zone_name="${nodes_and_zones[$((i+1))]}"
  if [[ "${instance_name}" =~ "-master" ]]; then
    master_instance_name="${instance_name}"
    master_zone_name="${zone_name}"
    i=$((i+2))
    continue
  fi
  echo "setup: project=${PROJECT_ID} zone=${zone_name} instance=${instance_name}"
  output="$(cat ${MINION_SCRIPT_NAME} | gcloud compute ssh --project=${PROJECT_ID} --zone=${zone_name} ${instance_name})"
  if [[ "${output}" =~ "ALL DONE" ]]; then
    minion_ok_count=$((minion_ok_count+1))
    echo "ALL DONE"
  else
    echo "FAILED"
    failure_count=$((failure_count+1))
    echo "${output}"
  fi
  i=$((i+2))
done 

echo "minion_ok_count=${minion_ok_count}"
echo "failure_count=${failure_count}"

if [[ ${failure_count} -gt 0 ]]; then
  echo "SCRIPT FAILED"
  echo "failed to install on ${failure_count} minion nodes"
  exit 1
fi

if [[ ${minion_ok_count} -le 0 ]]; then
  echo "SCRIPT FAILED"
  echo "no minion nodes found"
  exit 1
fi

if [[ ("${master_instance_name}" == "") || ("${master_zone_name}" == "") ]];then
  echo "SCRIPT FAILED"
  echo "did not find a master node"
  exit 1
fi

echo "setup: project=${PROJECT_ID} zone=${master_zone_name} instance=${master_instance_name}"
output="$(sed 's/NUM_MINIONS/'${minion_ok_count}'/' < ${MASTER_SCRIPT_NAME} | gcloud compute ssh --project=${PROJECT_ID} --zone=${master_zone_name} ${master_instance_name})"
if [[ "${output}" =~ "ALL DONE" ]]; then
  echo "master ALL DONE"
else
  echo "${output}"
  echo "SCRIPT FAILED"
  exit 1
fi

firewall_rules_list="$(gcloud compute firewall-rules list --project=${PROJECT_ID} | fgrep ${FIREWALL_RULE_NAME})"
if [[ "${firewall_rules_list}" == "" ]]; then
  echo "setup firewall rule"
  gcloud compute firewall-rules create --project=${PROJECT_ID} ${FIREWALL_RULE_NAME} --allow tcp:5555 --network "default" --source-ranges "0.0.0.0/0" --target-tags ${master_instance_name}
  if [[ $? -ne 0 ]]; then
    echo "FAILED to create firewall rule"
    exit 1
  else
    echo "created firewall rule successfully"
  fi
else
  echo "firewall rule exists"
fi

echo "checking Cluster-Insight master health"
master_instance_IP_address="$(gcloud compute --project="${PROJECT_ID}" instances list | fgrep ${master_instance_name} | awk '{print $5}')"
if [[ "${master_instance_IP_address}" == "" ]]; then
  echo "FAILED to find master instance ${master_instance_name} IP address"
  exit 1
fi

health=$(curl http://${master_instance_IP_address}:5555/healthz 2> /dev/null)
if [[ "${health}" =~ "OK" ]]; then
  echo "master is alive"
else
  echo "FAILED to get master health response"
  echo 1
fi

echo "SCRIPT ALL DONE"
exit 0
