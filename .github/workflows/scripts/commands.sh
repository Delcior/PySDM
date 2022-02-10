#!/usr/bin/env bash
set -e
if [[ "$(docker container inspect -f '{{.State.Running}}' gpurunner)" == "false" ]]; then
    docker start gpurunner
else
    exit 1
fi