#!/bin/bash
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
# 
#   http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

set -e

PID=$$

function usage()
{
  echo "This tool is for migrating primary replicas out of specified node."
  echo
  echo "USAGE1: $0 <cluster-meta-list> <migrate-node> <app-name> <run|test>"
  echo "USAGE2: $0 <shell-config-path> <migrate-node> <app-name> <run|test> -f"
  echo "app-name = * means migrate all apps"
}

if [ $# -ne 4 -a $# -ne 5 ]
then
  usage
  exit 1
fi

pwd="$( cd "$( dirname "$0"  )" && pwd )"
shell_dir="$( cd $pwd/.. && pwd )"
cd $shell_dir

if [ $# -eq 4 ]; then
  cluster=$1
elif [ "$5" == "-f" ]; then
  config=$1
else
  usage
  echo "ERROR: invalid option: $5"
  exit 1
fi
node=$2
app_name=$3
type=$4

if [ "$type" != "run" -a "$type" != "test" ]
then
  usage
  echo "ERROR: invalid type: $type"
  echo "USAGE: $0 <cluster-meta-list> <migrate-node> <app-name> <run|test>"
  exit 1
fi

echo "UID=$UID"
echo "PID=$PID"
echo

if [ "$cluster" != "" ]; then
  echo "set_meta_level steady" | ./run.sh shell --cluster $cluster &>/tmp/$UID.$PID.pegasus.set_meta_level
  echo ls | ./run.sh shell --cluster $cluster &>/tmp/$UID.$PID.pegasus.ls
else
  echo "set_meta_level steady" | ./run.sh shell --config $config &>/tmp/$UID.$PID.pegasus.set_meta_level
  echo ls | ./run.sh shell --config $config &>/tmp/$UID.$PID.pegasus.ls
fi

while read app_line
do
  status=`echo $app_line | awk '{print $2}'`
  if [ "$status" = "AVAILABLE" ]
  then
    gid=`echo $app_line | awk '{print $1}'`
    app=`echo $app_line | awk '{print $3}'`
    if [ "$app_name" != "*" -a "$app_name" != "$app" ]
    then
      continue
    fi

    if [ "$cluster" != "" ]; then
      echo "app $app -d" | ./run.sh shell --cluster $cluster &>/tmp/$UID.$PID.pegasus.app.$app
    else
      echo "app $app -d" | ./run.sh shell --config $config &>/tmp/$UID.$PID.pegasus.app.$app
    fi

    while read line
    do
      pri=`echo $line | awk '{print $4}'`
      if [ "$pri" = "$node" ]
      then
        pid=`echo $line | awk '{print $1}'`
        to=`echo $line | awk '{print $5}' | grep -o '\[.*\]' | grep -o '[0-9.:,]*' | cut -d, -f$((RANDOM%2+1))`
        echo "balance --gpid ${gid}.${pid} --type move_pri -f $node -t $to"
      fi
    done </tmp/$UID.$PID.pegasus.app.$app >/tmp/$UID.$PID.pegasus.cmd.$app

    if [ "$type" = "run" ]
    then
      if [ "$cluster" != "" ]; then
        cat /tmp/$UID.$PID.pegasus.cmd.$app | ./run.sh shell --cluster $cluster 2>/dev/null
      else
        cat /tmp/$UID.$PID.pegasus.cmd.$app | ./run.sh shell --config $config 2>/dev/null
      fi
      echo
      echo
    else
      cat /tmp/$UID.$PID.pegasus.cmd.$app
    fi
  fi
done </tmp/$UID.$PID.pegasus.ls

rm -f /tmp/$UID.$PID.pegasus.* &>/dev/null
